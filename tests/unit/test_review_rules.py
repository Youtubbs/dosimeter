"""Edit-then-approve changes wording, never a determination."""

from dosimeter.harness.review import (
    idempotency_key_for,
    validate_edit,
)

DOSSIER = {
    "exposure_id": "EXP-2026-0414",
    "outcome": "written_report_required",
    "rule_outcomes": {"R3": "not_required", "R4": "valid"},
    "doses": {"tede_rem": 8.5},
    "narrative": "The exposure was authorised in advance.",
    "sources": [
        {
            "doc_id": "CFR-20-LIMITS",
            "chunk_id": "CFR-20-LIMITS#0012",
            "status": "in_force",
            "title": "20.1206",
        }
    ],
}


def edited(**changes) -> dict:
    payload = {key: (dict(value) if isinstance(value, dict) else value) for key, value in DOSSIER.items()}
    payload["sources"] = [dict(item) for item in DOSSIER["sources"]]
    payload.update(changes)
    return payload


def test_changing_the_wording_is_allowed() -> None:
    assert validate_edit(DOSSIER, edited(narrative="The exposure was authorised beforehand.")) is None



def test_repointing_a_citation_within_the_same_source_is_allowed() -> None:
    payload = edited()
    payload["sources"][0]["chunk_id"] = "CFR-20-LIMITS#0013"

    assert validate_edit(DOSSIER, payload) is None


def test_changing_a_rule_outcome_is_refused() -> None:
    rejection = validate_edit(DOSSIER, edited(rule_outcomes={"R3": "required", "R4": "valid"}))

    assert rejection is not None
    assert rejection.reason_code == "determination_changed"
    assert rejection.field_path == "rule_outcomes"




def test_repointing_a_citation_at_a_different_document_is_refused() -> None:
    payload = edited()
    payload["sources"][0]["doc_id"] = "FR-DOSE"
    payload["sources"][0]["chunk_id"] = "FR-DOSE#0001"

    rejection = validate_edit(DOSSIER, payload)

    assert rejection is not None
    assert rejection.reason_code == "cited_document_changed"





def test_the_idempotency_key_is_stable_for_one_approval() -> None:
    first = idempotency_key_for("EXP-2026-0414", 7, DOSSIER)
    second = idempotency_key_for("EXP-2026-0414", 7, dict(reversed(list(DOSSIER.items()))))

    assert first == second
    assert first != idempotency_key_for("EXP-2026-0414", 8, DOSSIER)
    assert first != idempotency_key_for("EXP-2026-0411", 7, DOSSIER)


