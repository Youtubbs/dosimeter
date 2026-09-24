"""The parts of submit that need no database: ids, validation, the report."""

from __future__ import annotations

from pathlib import Path

import pytest

from dosimeter.config.settings import Bounds
from dosimeter.errors import ExtractionError
from dosimeter.ingestion.artifact_store import (
    ALLOWED_SUFFIXES,
    SkippedArtifact,
    SkipReason,
    artifact_kind,
    content_hash,
    content_key,
    validate_packet,
)
from dosimeter.ingestion.submit import IngestionReport, LowConfidenceField, exposure_id_for

CREW_NOTE = """Exposure ID: exp-0412
Worker ID: WKR-1047
District: District 2
Date: 06/18/2026

The source would not retract into the camera.
"""


def make_packet(root: Path, name: str = "exp-0412") -> Path:
    packet = root / name
    packet.mkdir()
    (packet / "crew-note.txt").write_text(CREW_NOTE, encoding="utf-8")
    (packet / "exposure-report.pdf").write_bytes(b"%PDF-1.7 exposure report")
    (packet / "photo-01.jpg").write_bytes(b"\xff\xd8\xff fake jpeg")
    return packet


def test_the_exposure_id_comes_from_the_directory_and_the_packet_date(tmp_path: Path) -> None:
    assert exposure_id_for(make_packet(tmp_path)) == "EXP-2026-0412"


def test_a_directory_with_no_number_is_refused(tmp_path: Path) -> None:
    (tmp_path / "packet").mkdir()

    with pytest.raises(ValueError):
        exposure_id_for(tmp_path / "packet")


def test_the_content_key_is_the_hash(tmp_path: Path) -> None:
    digest = content_hash(b"some bytes")

    assert content_key(digest, ".PDF") == f"artifacts/{digest[:2]}/{digest}.pdf"
    assert content_hash(b"some bytes") == digest


def test_artifacts_are_named_by_what_they_are() -> None:
    assert artifact_kind(Path("DOSIMETRY REPORT #2.pdf")) == "dosimetry-report"
    assert artifact_kind(Path("crew-note.txt")) == "crew-note"
    assert artifact_kind(Path("photo-01.jpg")) == "photo"
    assert artifact_kind(Path("Radiation Exposure Report.pdf")) == "exposure-report"


def test_validation_accepts_the_allowed_types(tmp_path: Path) -> None:
    packet = make_packet(tmp_path)

    accepted, skipped = validate_packet(packet, Bounds())

    assert sorted(path.name for path in accepted) == [
        "crew-note.txt",
        "exposure-report.pdf",
        "photo-01.jpg",
    ]
    assert skipped == []
    assert ".png" in ALLOWED_SUFFIXES


def test_validation_rejects_an_unsupported_type(tmp_path: Path) -> None:
    packet = make_packet(tmp_path)
    (packet / "notes.docx").write_bytes(b"not allowed")

    accepted, skipped = validate_packet(packet, Bounds())

    assert "notes.docx" not in [path.name for path in accepted]
    assert skipped[0].reason_code == SkipReason.UNSUPPORTED_TYPE


def test_validation_rejects_a_file_over_the_size_cap(tmp_path: Path) -> None:
    packet = make_packet(tmp_path)
    (packet / "huge.pdf").write_bytes(b"x" * 2048)

    accepted, skipped = validate_packet(packet, Bounds(max_artifact_bytes=1024))

    assert "huge.pdf" not in [path.name for path in accepted]
    assert skipped[0].reason_code == SkipReason.ARTIFACT_TOO_LARGE


def test_validation_rejects_an_empty_file(tmp_path: Path) -> None:
    packet = make_packet(tmp_path)
    (packet / "empty.pdf").write_bytes(b"")

    _, skipped = validate_packet(packet, Bounds())

    assert skipped[0].reason_code == SkipReason.ARTIFACT_EMPTY


def test_validation_caps_the_number_of_files(tmp_path: Path) -> None:
    packet = make_packet(tmp_path)

    accepted, skipped = validate_packet(packet, Bounds(max_artifacts_per_packet=2))

    assert len(accepted) == 2
    assert skipped[0].reason_code == SkipReason.TOO_MANY_ARTIFACTS


def test_a_missing_packet_directory_is_a_typed_error(tmp_path: Path) -> None:
    with pytest.raises(ExtractionError):
        validate_packet(tmp_path / "nothing-here", Bounds())


def test_the_report_prints_the_exposure_id_first() -> None:
    report = IngestionReport(
        exposure_id="EXP-2026-0412",
        artifacts_processed=3,
        artifacts_skipped=1,
        fields_extracted=11,
        low_confidence_fields=[
            LowConfidenceField(
                field_key="Total Effective Dose Equivalent",
                confidence=0.41,
                artifact="exposure-report.pdf",
            )
        ],
        failures=[
            SkippedArtifact(
                file_name="broken.pdf",
                reason_code=SkipReason.EXTRACTION_FAILED,
                detail="the document could not be read",
            )
        ],
    )

    rendered = report.render()

    assert rendered.splitlines()[0] == "EXP-2026-0412"
    assert "artifacts processed: 3" in rendered
    assert "Total Effective Dose Equivalent (0.41)" in rendered
    assert "broken.pdf: extraction_failed" in rendered


def test_a_clean_report_says_none_rather_than_leaving_it_blank() -> None:
    rendered = IngestionReport(exposure_id="EXP-2026-0411").render()

    assert "fields below the confidence floor: none" in rendered
    assert "failures: none" in rendered
