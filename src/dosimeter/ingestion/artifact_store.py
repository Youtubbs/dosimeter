"""
Content-addressed artifact store. A packet is validated first, then every file
is hashed and written to a key derived from that hash, so submitting the same
packet twice writes nothing new and creates no second row.
"""

import hashlib
import logging
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from dosimeter.config.settings import Bounds
from dosimeter.errors import ExtractionError
from dosimeter.repository import Session, queries
from dosimeter.repository.models import Artifact

ALLOWED_SUFFIXES = (".pdf", ".jpg", ".jpeg", ".png", ".txt")

logger = logging.getLogger(__name__)


class SkipReason(StrEnum):
    """Why an artifact did not make it into the record."""

    UNSUPPORTED_TYPE = "unsupported_artifact_type"
    ARTIFACT_TOO_LARGE = "artifact_too_large"
    ARTIFACT_EMPTY = "artifact_empty"
    ARTIFACT_UNREADABLE = "artifact_unreadable"
    TOO_MANY_ARTIFACTS = "too_many_artifacts"
    EXTRACTION_FAILED = "extraction_failed"
    NO_FIELDS_FOUND = "no_fields_found"


class S3ObjectStore:
    """
    The two things the store needs from object storage. Tests pass a fake with
    the same two methods. The AWS client module is the only place a client is built.
    """

    def exists(self, bucket: str, key: str) -> bool:
        from dosimeter.aws.aws import get_client

        client = get_client("s3")
        try:
            client.head_object(Bucket=bucket, Key=key)
        except client.exceptions.ClientError:
            return False
        return True

    def put(self, bucket: str, key: str, content: bytes) -> None:
        from dosimeter.aws.aws import get_client

        get_client("s3").put_object(Bucket=bucket, Key=key, Body=content)


class SubmissionRequest(BaseModel):
    """A validated request to submit one packet directory."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    packet_dir: Path
    exposure_id: str = Field(min_length=1)
    bucket: str = Field(min_length=1)
    worker_id: str = Field(default="unknown", min_length=1)
    district: str = Field(default="unassigned", min_length=1)
    officer_code: str | None = None


class SkippedArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    file_name: str
    reason_code: SkipReason
    detail: str | None = None


class StoredArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    file_name: str
    kind: str
    content_sha256: str
    bucket: str
    key: str
    size_bytes: int
    uploaded: bool
    artifact_id: int | None = None


def content_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def content_key(digest: str, suffix: str) -> str:
    """Two levels of prefix keeps a flat bucket listing usable."""

    return f"artifacts/{digest[:2]}/{digest}{suffix.lower()}"


def artifact_kind(path: Path) -> str:
    name = path.name.lower()
    if "dosimetry" in name:
        return "dosimetry-report"
    if "crew" in name:
        return "crew-note"
    if path.suffix.lower() in (".jpg", ".jpeg", ".png"):
        return "photo"
    return "exposure-report"


def validate_packet(
    packet_dir: Path,
    bounds: Bounds,
) -> tuple[list[Path], list[SkippedArtifact]]:
    """Check types, sizes and counts before anything is read or uploaded."""

    if not packet_dir.is_dir():
        raise ExtractionError("packet directory does not exist", packet_dir=str(packet_dir))

    accepted: list[Path] = []
    skipped: list[SkippedArtifact] = []

    for path in sorted(item for item in packet_dir.rglob("*") if item.is_file()):
        if path.suffix.lower() not in ALLOWED_SUFFIXES:
            skipped.append(
                SkippedArtifact(
                    file_name=path.name,
                    reason_code=SkipReason.UNSUPPORTED_TYPE,
                    detail=f"{path.suffix or 'no extension'} is not one of "
                    f"{', '.join(ALLOWED_SUFFIXES)}",
                )
            )
            continue

        size = path.stat().st_size
        if size == 0:
            skipped.append(
                SkippedArtifact(file_name=path.name, reason_code=SkipReason.ARTIFACT_EMPTY)
            )
            continue
        if size > bounds.max_artifact_bytes:
            skipped.append(
                SkippedArtifact(
                    file_name=path.name,
                    reason_code=SkipReason.ARTIFACT_TOO_LARGE,
                    detail=f"{size} bytes exceeds {bounds.max_artifact_bytes}",
                )
            )
            continue

        if len(accepted) >= bounds.max_artifacts_per_packet:
            skipped.append(
                SkippedArtifact(
                    file_name=path.name,
                    reason_code=SkipReason.TOO_MANY_ARTIFACTS,
                    detail=f"more than {bounds.max_artifacts_per_packet} artifacts",
                )
            )
            continue

        accepted.append(path)

    return accepted, skipped


def store_artifact(
    session: Session,
    request: SubmissionRequest,
    path: Path,
    store: S3ObjectStore,
) -> StoredArtifact:
    """Hash, upload if the key is new, and record the row."""

    content = path.read_bytes()
    digest = content_hash(content)
    key = content_key(digest, path.suffix)

    uploaded = False
    if not store.exists(request.bucket, key):
        store.put(request.bucket, key, content)
        uploaded = True

    artifact_id = queries.insert_artifact(
        session,
        Artifact(
            exposure_id=request.exposure_id,
            kind=artifact_kind(path),
            content_sha256=digest,
            s3_bucket=request.bucket,
            s3_key=key,
            status="stored",
        ),
    )

    logger.info(
        "artifact.stored",
        extra={
            "exposure_id": request.exposure_id,
            "content_sha256": digest,
            "uploaded": uploaded,
        },
    )

    return StoredArtifact(
        file_name=path.name,
        kind=artifact_kind(path),
        content_sha256=digest,
        bucket=request.bucket,
        key=key,
        size_bytes=len(content),
        uploaded=uploaded,
        artifact_id=artifact_id,
    )


def store_packet(
    session: Session,
    request: SubmissionRequest,
    store: S3ObjectStore,
    bounds: Bounds,
) -> tuple[list[StoredArtifact], list[SkippedArtifact]]:
    """Validate the packet, then store every artifact that passed."""

    accepted, skipped = validate_packet(request.packet_dir, bounds)

    stored: list[StoredArtifact] = []
    for path in accepted:
        try:
            stored.append(store_artifact(session, request, path, store))
        except OSError as error:
            skipped.append(
                SkippedArtifact(
                    file_name=path.name,
                    reason_code=SkipReason.ARTIFACT_UNREADABLE,
                    detail=str(error),
                )
            )

    return stored, skipped
