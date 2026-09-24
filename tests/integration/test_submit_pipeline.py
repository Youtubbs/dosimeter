"""Submit against a real database: idempotent, skip-and-log, report stored."""

from __future__ import annotations

import hashlib
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from dosimeter.config.settings import Settings
from dosimeter.ingestion.artifact_store import SkipReason
from dosimeter.ingestion.submit import submit_packet
from dosimeter.redaction import IdentityVault
from dosimeter.repository import orm, queries
from tests.integration.helpers import FakeObjectStore

CREW_NOTE = """Exposure ID: exp-0414
Worker ID: WKR-1047
Worker Name: Marguerite Ostrander
District: District 4
Date: 08/21/2026

The entry was authorised and a supervisor was present throughout.
"""


MALFORMED = b"this is not a pdf at all"
MALFORMED_HASH = hashlib.sha256(MALFORMED).hexdigest()


def make_packet(root: Path) -> Path:
    packet = root / "exp-0414"
    packet.mkdir()
    (packet / "crew-note.txt").write_text(CREW_NOTE, encoding="utf-8")
    (packet / "exposure-report.pdf").write_bytes(b"%PDF-1.7 exposure report")
    (packet / "photo-01.jpg").write_bytes(b"\xff\xd8\xff photo")
    (packet / "malformed.pdf").write_bytes(MALFORMED)
    (packet / "notes.docx").write_bytes(b"unsupported")
    return packet


def fake_cracker(s3_key: str, bucket: str) -> list[dict]:
    """Everything cracks except the malformed artifact, which comes back empty."""

    if MALFORMED_HASH in s3_key:
        return []
    return [{"key": s3_key}]


def fake_normalizer(blocks: list[dict], source_artifact: str) -> dict:
    return {
        "source_artifact": source_artifact,
        "fields": [
            {
                "field": "Total Effective Dose Equivalent",
                "value": "8.5",
                "unit": "rem",
                "confidence": 99.0,
                "page": 1,
            },
            {
                "field": "Worker Name",
                "value": "Marguerite Ostrander",
                "confidence": 98.0,
                "page": 1,
            },
            {
                "field": "Shallow Dose Equivalent",
                "value": "14",
                "unit": "rem",
                "confidence": 41.0,
                "page": 1,
            },
        ],
    }


def run_submit(session: Session, packet: Path, store: FakeObjectStore, vault=None):
    settings = Settings(
        _env_file=None,
        bedrock_model_id="text-model-id",
        bedrock_embed_model_id="embedding-model-id",
        knowledge_base_id="kb",
        guardrail_id="gr",
        corpus_bucket="corpus",
        packet_bucket="packets",
    )
    return submit_packet(
        session=session,
        packet_dir=packet,
        settings=settings,
        store=store,
        cracker=fake_cracker,
        normalizer=fake_normalizer,
        vault=vault,
    )


def test_submit_persists_the_exposure_its_artifacts_and_its_fields(
    db: Session,
    tmp_path: Path,
) -> None:
    report = run_submit(db, make_packet(tmp_path), FakeObjectStore())

    assert report.exposure_id == "EXP-2026-0414"
    assert report.render().splitlines()[0] == "EXP-2026-0414"

    exposure = queries.get_exposure(db, "EXP-2026-0414")
    assert exposure.district == "District 4"
    assert exposure.worker_id == "WKR-1047"
    assert exposure.status == "submitted"
    assert len(queries.list_artifacts(db, "EXP-2026-0414")) == 4


def test_every_field_row_names_the_artifact_it_came_from(db: Session, tmp_path: Path) -> None:
    run_submit(db, make_packet(tmp_path), FakeObjectStore())

    hashes = queries.artifact_hashes_by_id(db, "EXP-2026-0414")
    fields = queries.list_extracted_fields(db, "EXP-2026-0414")

    assert fields
    assert all(hashes.get(field.artifact_id) for field in fields)


def test_the_malformed_artifact_is_a_failure_and_the_run_still_finishes(
    db: Session,
    tmp_path: Path,
) -> None:
    report = run_submit(db, make_packet(tmp_path), FakeObjectStore())

    reasons = {item.file_name: item.reason_code for item in report.failures}

    assert reasons["malformed.pdf"] == SkipReason.EXTRACTION_FAILED
    assert reasons["notes.docx"] == SkipReason.UNSUPPORTED_TYPE
    assert report.artifacts_processed == 4
    assert report.fields_extracted > 0


def test_a_field_below_the_floor_is_named_in_the_report(db: Session, tmp_path: Path) -> None:
    report = run_submit(db, make_packet(tmp_path), FakeObjectStore())

    below = {item.field_key for item in report.low_confidence_fields}

    assert "Shallow Dose Equivalent" in below
    assert "Total Effective Dose Equivalent" not in below


def test_the_report_is_stored_beside_the_record(db: Session, tmp_path: Path) -> None:
    report = run_submit(db, make_packet(tmp_path), FakeObjectStore())

    stored = queries.latest_ingestion_report(db, "EXP-2026-0414")

    assert stored is not None
    assert stored.fields_extracted == report.fields_extracted
    assert stored.artifacts_processed == report.artifacts_processed
    assert [item["reason_code"] for item in stored.failures]


def test_a_second_run_writes_no_second_object_and_no_second_row(
    db: Session,
    tmp_path: Path,
) -> None:
    packet = make_packet(tmp_path)
    store = FakeObjectStore()

    first = run_submit(db, packet, store)
    puts_after_first = store.puts
    fields_after_first = db.scalar(select(func.count()).select_from(orm.ExtractedFieldRow))

    second = run_submit(db, packet, store)

    assert second.exposure_id == first.exposure_id
    assert store.puts == puts_after_first
    assert len(store.objects) == 4
    assert db.scalar(select(func.count()).select_from(orm.ArtifactRow)) == 4
    assert db.scalar(select(func.count()).select_from(orm.ExtractedFieldRow)) == fields_after_first
    assert db.scalar(select(func.count()).select_from(orm.ExposureRow)) == 1


def test_no_worker_name_reaches_the_record_and_the_name_goes_to_the_vault(
    db: Session,
    tmp_path: Path,
) -> None:
    vault = IdentityVault(tmp_path / "identities")

    run_submit(db, make_packet(tmp_path), FakeObjectStore(), vault=vault)

    values = [field.value for field in queries.list_extracted_fields(db, "EXP-2026-0414")]
    stored = vault.load("EXP-2026-0414")

    assert "Marguerite Ostrander" not in values
    assert "[redacted]" in values
    assert any(item["value"] == "Marguerite Ostrander" for item in stored)
