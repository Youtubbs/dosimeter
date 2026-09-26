"""
The submit pipeline: validate, store, crack, redact, persist, report.

It is deterministic and synchronous. A packet that contains one unreadable file
still produces a record; the file appears in the report as a failure with a
reason code.
"""

import logging
import re
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from dosimeter.config.settings import Settings
from dosimeter.ingestion.artifact_store import (
    S3ObjectStore,
    SkippedArtifact,
    SkipReason,
    StoredArtifact,
    SubmissionRequest,
    store_packet,
)
from dosimeter.errors import ExtractionError
from dosimeter.redaction import IdentityVault, redact_value
from dosimeter.repository import Session, queries
from dosimeter.repository.models import ExtractedField, Exposure

Cracker = Callable[[str, str], list[dict]]
Normalizer = Callable[[list[dict], str], dict]

logger = logging.getLogger(__name__)

_PACKET_ID = re.compile(r"(\d{3,})\s*$")
_DATE = re.compile(r"Date[^:]*:\s*(\d{2})/(\d{2})/(\d{4})")
_WORKER_ID = re.compile(r"Worker ID\s*:\s*([A-Za-z0-9-]+)")
_DISTRICT = re.compile(r"District\s*:?\s*([A-Za-z0-9 ]+)")


class LowConfidenceField(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    field_key: str
    confidence: float
    artifact: str


class IngestionReport(BaseModel):
    """What the command prints and what is stored alongside the record."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    exposure_id: str
    artifacts_processed: int = 0
    artifacts_skipped: int = 0
    fields_extracted: int = 0
    low_confidence_fields: list[LowConfidenceField] = Field(default_factory=list)
    failures: list[SkippedArtifact] = Field(default_factory=list)

    def render(self) -> str:
        lines = [
            self.exposure_id,
            f"artifacts processed: {self.artifacts_processed}",
            f"artifacts skipped:   {self.artifacts_skipped}",
            f"fields extracted:    {self.fields_extracted}",
        ]

        if self.low_confidence_fields:
            lines.append("fields below the confidence floor:")
            lines.extend(
                f"  {item.field_key} ({item.confidence:.2f}) from {item.artifact}"
                for item in self.low_confidence_fields
            )
        else:
            lines.append("fields below the confidence floor: none")

        if self.failures:
            lines.append("failures:")
            lines.extend(
                f"  {item.file_name}: {item.reason_code.value}"
                + (f" - {item.detail}" if item.detail else "")
                for item in self.failures
            )
        else:
            lines.append("failures: none")

        return "\n".join(lines)


def exposure_id_for(packet_dir: Path, today: date | None = None) -> str:
    """EXP-2026-0412 from a directory named exp-0412 and the packet's own date."""

    match = _PACKET_ID.search(packet_dir.name)
    if match is None:
        raise ExtractionError("packet directory name has no number", packet_dir=packet_dir.name)

    year = _packet_year(packet_dir) or (today or date.today()).year
    return f"EXP-{year}-{match.group(1)}"


def _packet_year(packet_dir: Path) -> int | None:
    for path in sorted(packet_dir.glob("*.txt")):
        found = _DATE.search(path.read_text(encoding="utf-8", errors="ignore"))
        if found is not None:
            return int(found.group(3))
    return None


def _packet_text(packet_dir: Path) -> str:
    parts = [
        path.read_text(encoding="utf-8", errors="ignore")
        for path in sorted(packet_dir.glob("*.txt"))
    ]
    return "\n".join(parts)


def packet_subject(packet_dir: Path) -> tuple[str, str, date | None]:
    """Worker id, district and date, read from the packet notes."""

    text = _packet_text(packet_dir)

    worker = _WORKER_ID.search(text)
    district = _DISTRICT.search(text)
    when = _DATE.search(text)

    occurred_on = None
    if when is not None:
        occurred_on = date(int(when.group(3)), int(when.group(1)), int(when.group(2)))

    return (
        worker.group(1) if worker else "unknown",
        district.group(1).strip() if district else "unassigned",
        occurred_on,
    )


def _confidence(raw: object) -> float | None:
    if raw is None:
        return None
    value = float(raw)
    return value / 100 if value > 1 else value


def _default_cracker(s3_key: str, bucket: str) -> list[dict]:
    from dosimeter.ingestion.textract import extract_artifact

    return extract_artifact(s3_key=s3_key, bucket_name=bucket)


def _default_normalizer(blocks: list[dict], source_artifact: str) -> dict:
    from dosimeter.ingestion.normalize import normalize

    return normalize(blocks=blocks, source_artifact=source_artifact)


def submit_packet(
    session: Session,
    packet_dir: Path,
    settings: Settings,
    store: S3ObjectStore,
    cracker: Cracker | None = None,
    normalizer: Normalizer | None = None,
    vault: IdentityVault | None = None,
) -> IngestionReport:
    """Run one packet through the pipeline and return its report."""

    crack = cracker or _default_cracker
    normalize_blocks = normalizer or _default_normalizer

    exposure_id = exposure_id_for(packet_dir)
    worker_id, district, occurred_on = packet_subject(packet_dir)

    request = SubmissionRequest(
        packet_dir=packet_dir,
        exposure_id=exposure_id,
        bucket=settings.packet_bucket,
        worker_id=worker_id,
        district=district,
    )

    queries.insert_exposure(
        session,
        Exposure(
            id=exposure_id,
            worker_id=worker_id,
            district=district,
            occurred_on=occurred_on,
            status="submitted",
        ),
    )

    stored, failures = store_packet(session, request, store, settings.bounds)
    queries.delete_extracted_fields(session, exposure_id)

    fields: list[ExtractedField] = []
    low_confidence: list[LowConfidenceField] = []
    identities = []

    for artifact in stored:
        cracked = _crack_one(artifact, crack, failures)
        if cracked is None:
            continue

        normalized = normalize_blocks(cracked, artifact.key)
        redaction = redact_value(normalized)
        identities.extend(redaction.removed)

        artifact_fields = redaction.value.get("fields", [])
        if not artifact_fields:
            failures.append(
                SkippedArtifact(
                    file_name=artifact.file_name,
                    reason_code=SkipReason.NO_FIELDS_FOUND,
                    detail="the artifact produced no form fields",
                )
            )
            continue

        for item in artifact_fields:
            confidence = _confidence(item.get("confidence"))
            fields.append(
                ExtractedField(
                    exposure_id=exposure_id,
                    artifact_id=artifact.artifact_id,
                    field_key=str(item.get("field", "")).strip() or "unnamed_field",
                    value=item.get("value"),
                    unit=item.get("unit"),
                    confidence=confidence,
                    page=item.get("page"),
                )
            )
            if confidence is not None and confidence < settings.confidence_floor:
                low_confidence.append(
                    LowConfidenceField(
                        field_key=str(item.get("field", "")).strip() or "unnamed_field",
                        confidence=confidence,
                        artifact=artifact.file_name,
                    )
                )

    queries.insert_extracted_fields(session, fields)

    if identities and vault is not None:
        vault.store(exposure_id, identities)

    report = IngestionReport(
        exposure_id=exposure_id,
        artifacts_processed=len(stored),
        artifacts_skipped=len(failures),
        fields_extracted=len(fields),
        low_confidence_fields=low_confidence,
        failures=failures,
    )

    queries.save_ingestion_report(
        session,
        exposure_id=exposure_id,
        artifacts_processed=report.artifacts_processed,
        artifacts_skipped=report.artifacts_skipped,
        fields_extracted=report.fields_extracted,
        low_confidence_fields=[item.model_dump() for item in report.low_confidence_fields],
        failures=[
            {
                "file_name": item.file_name,
                "reason_code": item.reason_code.value,
                "detail": item.detail,
            }
            for item in report.failures
        ],
    )
    session.commit()

    logger.info(
        "submit.completed",
        extra={
            "exposure_id": exposure_id,
            "artifacts_processed": report.artifacts_processed,
            "fields_extracted": report.fields_extracted,
            "failures": report.artifacts_skipped,
            "submitted_at": datetime.now().isoformat(timespec="seconds"),
        },
    )
    return report


def _crack_one(
    artifact: StoredArtifact,
    crack: Cracker,
    failures: list[SkippedArtifact],
) -> list[dict] | None:
    """Crack one artifact, or record why it could not be."""

    if artifact.kind == "photo":
        return None

    try:
        blocks = crack(artifact.key, artifact.bucket)
    except Exception as error:  # one bad artifact never stops a submit
        failures.append(
            SkippedArtifact(
                file_name=artifact.file_name,
                reason_code=SkipReason.EXTRACTION_FAILED,
                detail=str(error),
            )
        )
        return None

    if not blocks:
        failures.append(
            SkippedArtifact(
                file_name=artifact.file_name,
                reason_code=SkipReason.EXTRACTION_FAILED,
                detail="the document could not be read",
            )
        )
        return None

    return blocks
