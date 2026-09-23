"""A planted name never reaches the record, the log or the model request."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from dosimeter.logging_config import JsonFormatter
from dosimeter.redaction import (
    REDACTED,
    IdentityVault,
    is_redacted_field,
    redact_for_log,
    redact_for_model,
    redact_text,
    redact_value,
)

PLANTED_NAME = "Marguerite Ostrander"

CREW_NOTE = f"""Exposure ID: exp-0411
Worker ID: WKR-1047
Worker Name: {PLANTED_NAME}
Crew Chief: Desmond Ayotte
Date: 03/12/2026

The camera stayed in its normal position and the source never left the device.
"""

NORMALIZED = {
    "exposure_id": "exp-0411",
    "source_artifact": "exp-0411/exposure-report.pdf",
    "fields": [
        {"field": "Worker Name", "value": PLANTED_NAME, "confidence": 0.99},
        {"field": "Worker ID", "value": "WKR-1047", "confidence": 0.99},
        {"field": "Total Effective Dose Equivalent", "value": "6.2", "unit": "rem"},
    ],
    "crew_note": CREW_NOTE,
}


def test_field_names_are_matched_however_they_are_written() -> None:
    assert is_redacted_field("Worker Name")
    assert is_redacted_field("worker_name")
    assert is_redacted_field("  WORKER NAME:  ".replace(":", ""))
    assert is_redacted_field("Date of Birth")
    assert not is_redacted_field("Worker ID")
    assert not is_redacted_field("Total Effective Dose Equivalent")


def test_extra_field_names_can_be_added_by_the_caller() -> None:
    assert not is_redacted_field("Contractor")
    assert is_redacted_field("Contractor", extra_fields=["contractor"])


def test_name_is_gone_from_the_normalized_record() -> None:
    result = redact_value(NORMALIZED)

    assert PLANTED_NAME not in json.dumps(result.value)
    assert "Desmond Ayotte" not in json.dumps(result.value)
    assert result.value["fields"][0]["value"] == REDACTED
    assert result.value["fields"][1]["value"] == "WKR-1047"


def test_removed_spans_name_their_field_and_position() -> None:
    result = redact_text(CREW_NOTE)

    fields = {span.field_name for span in result.removed}
    assert fields == {"Worker Name", "Crew Chief"}

    span = next(item for item in result.removed if item.field_name == "Worker Name")
    assert CREW_NOTE[span.start : span.end] == PLANTED_NAME


def test_name_is_gone_from_the_model_request_payload() -> None:
    payload = {
        "modelId": "reasoning-model-id",
        "messages": [{"role": "user", "content": [{"text": CREW_NOTE}]}],
    }

    assert PLANTED_NAME not in json.dumps(redact_for_model(payload))


def test_name_is_gone_from_the_log_line() -> None:
    record = logging.LogRecord(
        name="dosimeter.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="packet.submitted",
        args=(),
        exc_info=None,
    )
    record.crew_note = CREW_NOTE
    record.worker_name = PLANTED_NAME

    line = JsonFormatter().format(record)

    assert PLANTED_NAME not in line
    assert "packet.submitted" in line


def test_worker_dose_history_is_never_logged() -> None:
    payload = {
        "worker_id": "WKR-1047",
        "lifetime_dose": 6.0,
        "dose_history": [{"quantity": "tede_year_to_date", "value": 1.2}],
    }

    logged = json.dumps(redact_for_log(payload))

    assert "6.0" not in logged
    assert "1.2" not in logged
    assert "WKR-1047" in logged


def test_identity_record_is_stored_on_its_own(tmp_path: Path) -> None:
    vault = IdentityVault(tmp_path / "identities")
    result = redact_text(CREW_NOTE)

    path = vault.store("exp-0411", result.removed)
    stored = vault.load("exp-0411")

    assert path.parent == tmp_path / "identities"
    assert {item["field_name"] for item in stored} == {"Worker Name", "Crew Chief"}
    assert stored[0]["value"] == PLANTED_NAME
    assert vault.load("exp-9999") == []
