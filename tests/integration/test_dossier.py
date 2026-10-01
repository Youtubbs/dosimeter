"""The dossier and its sources, rendered cold from what an assess turn stored."""

import pytest
from sqlalchemy.orm import Session

from dosimeter.errors import GateError
from dosimeter.harness.dossier import DISCLOSURE, SYNTHETIC_NOTICE, render_dossier, render_sources
from dosimeter.harness.run_record import RunRecorder
from dosimeter.repository import queries, seeds

EXPOSURE = "EXP-2026-0412"
# a real chunk in kb/, so the source text is read from the corpus files
CHUNK_2202 = "69f017321152cda2dd736f0c21de48a6b908d4524387df1db86bc2f7b7fb0b29"

PSE_EVIDENCE = {
    field: True
    for field in [
        "exceptional_situation",
        "alternatives_unavailable_or_impractical",
        "licensee_written_authorization",
        "employer_written_authorization",
        "authorization_before_exposure",
        "worker_informed_of_purpose",
        "worker_informed_of_estimated_dose_and_risks",
        "worker_instructed_in_alara_measures",
        "prior_lifetime_doses_ascertained",
        "annual_pse_limit_satisfied",
        "lifetime_pse_limit_satisfied",
        "required_records_maintained",
        "report_under_20_2204_submitted",
        "best_dose_estimate_recorded",
        "worker_informed_of_dose_in_writing",
        "worker_informed_within_30_days",
    ]
}

PAYLOAD = {
    "exposure_id": EXPOSURE,
    "outcome": "escalated",
    "workers": ["notification", "written_report"],
    "proposals": {
        "notification": {
            "worker": "notification",
            "kind": "notification",
            "payload": {
                "notification_required": True,
                "clock": "immediate",
                "explanation": "310 rad meets 250 rad.",
            },
            "citations": [CHUNK_2202, "10 CFR 20.2101"],
        },
        "written_report": {
            "worker": "written_report",
            "kind": "written_report",
            "payload": {
                "report_required": True,
                "reporting_path": "20.2204",
                "explanation": "R4 is valid.",
            },
            "citations": [CHUNK_2202, "10 CFR 99.1"],
        },
    },
    "rule_invocations": [
        {
            "tool": "evaluate_rule",
            "result": {
                "rule_id": "R1",
                "result": {
                    "rule_id": "R1",
                    "outcome": "required",
                    "inputs_used": {
                        "shallow": {"value": 310, "unit": "rad", "site": "extremity"},
                        "lens": None,
                    },
                    "threshold": {"shallow": {"value": 250.0, "unit": "rad"}},
                },
            },
        },
        {
            "tool": "evaluate_rule",
            "result": {
                "rule_id": "R4",
                "result": {"rule_id": "R4", "outcome": "valid", "inputs_used": PSE_EVIDENCE},
            },
        },
    ],
    "sources": [
        {
            "found": True,
            "sources": [
                {
                    "chunk_id": CHUNK_2202,
                    "doc_id": "CFR-20-REPORTS",
                    "title": "CFR-20-REPORTS",
                    "section_path": "§ 20.2202",
                    "page": 2,
                    "status": "in_force",
                    "text": "stored text",
                },
                {
                    "chunk_id": "fr-dose-1",
                    "doc_id": "FR-DOSE",
                    "title": "FR-DOSE",
                    "section_path": "§ 20.2101",
                    "page": 15,
                    "status": "proposed",
                    "text": "proposed text",
                },
            ],
        }
    ],
    "escalation_signals": ["notification_required"],
}


@pytest.fixture
def stored(db: Session) -> Session:
    seeds.apply_seeds(db)
    officer = queries.officer_by_code(db, "OFF-101")
    recorder = RunRecorder(
        session=db, exposure_id=EXPOSURE, officer_id=officer.id, command="assess"
    )
    recorder.start()
    queries.save_dossier(db, EXPOSURE, recorder.run_id, PAYLOAD)
    queries.save_ingestion_report(
        db,
        EXPOSURE,
        artifacts_processed=4,
        artifacts_skipped=1,
        fields_extracted=63,
        low_confidence_fields=[],
        failures=[
            {
                "file_name": "crew-note.txt",
                "reason_code": "extraction_failed",
                "detail": "could not be read",
            }
        ],
    )
    db.commit()
    return db


def test_the_dossier_cites_by_number_and_carries_the_disclosures(stored: Session) -> None:
    rendered = render_dossier(stored, EXPOSURE)

    assert DISCLOSURE in rendered
    assert SYNTHETIC_NOTICE in rendered
    assert "notification required, clock: immediate" in rendered
    # a chunk cited by both workers keeps one number
    assert "310 rad meets 250 rad. [1] [2]" in rendered
    assert "R4 is valid. [1] [3]" in rendered
    assert "[2] FR-DOSE FR-DOSE, § 20.2101, page 15 - PROPOSED, NOT IN FORCE" in rendered
    assert "[3] 10 CFR 99.1 - unresolved" in rendered
    assert "R1: required on shallow 310 rad (extremity)" in rendered
    assert "lens None" not in rendered
    assert "crew-note.txt: extraction_failed" in rendered


def test_a_valid_r4_lists_all_seven_conditions_and_names_the_substitute_report(
    stored: Session,
) -> None:
    rendered = render_dossier(stored, EXPOSURE)

    for letter in "abcdefg":
        assert f"  ({letter}) " in rendered
    assert "not shown" not in rendered
    assert "20.2204 report to the NRC Regional Office" in rendered


def test_the_dossier_states_outcomes_never_orders(stored: Session) -> None:
    assert "you must" not in render_dossier(stored, EXPOSURE).lower()


def test_sources_lists_every_status_and_prints_the_corpus_text_behind_a_ref(
    stored: Session,
) -> None:
    listing = render_sources(stored, EXPOSURE)
    one = render_sources(stored, EXPOSURE, 1)

    assert listing.count(" - ") == 3
    assert "PROPOSED, NOT IN FORCE" in listing
    assert f"chunk id  {CHUNK_2202}" in one
    # read from the corpus files, not the copy the turn stored
    assert "Immediate notification" in one
    assert "stored text" not in one


def test_an_invalid_ref_or_a_missing_dossier_is_a_readable_error(stored: Session) -> None:
    with pytest.raises(GateError, match="no source \\[9\\]; this dossier cites 3"):
        render_sources(stored, EXPOSURE, 9)

    with pytest.raises(GateError, match="run assess first"):
        render_dossier(stored, "EXP-2026-0413")
