"""Tests for deterministic escalation evaluation."""

from dosimeter.harness.escalation import (
    Trigger,
    TriggerSignals,
    evaluate,
)


def test_no_signals_do_not_escalate():
    result = evaluate(TriggerSignals())

    assert result.escalates is False
    assert result.fired == []
    assert set(result.evaluated) == set(Trigger)


def test_prompt_attack_escalates():
    result = evaluate(
        TriggerSignals(
            prompt_attack_fired=True,
        )
    )

    assert result.escalates is True
    assert Trigger.PROMPT_ATTACK_FIRED.value in result.names()


def test_low_confidence_escalates():
    result = evaluate(
        TriggerSignals(
            fields_below_floor=["annual_tede"],
        )
    )

    assert result.escalates is True
    assert Trigger.FIELD_BELOW_FLOOR.value in result.names()
    assert result.fired[0].detail == "annual_tede"


def test_insufficient_data_escalates():
    result = evaluate(
        TriggerSignals(
            insufficient_data_rules=["R3"],
        )
    )

    assert Trigger.INSUFFICIENT_DATA.value in result.names()


def test_notification_required_escalates():
    result = evaluate(
        TriggerSignals(
            notification_required_rules=["R1", "R2"],
        )
    )

    assert Trigger.NOTIFICATION_REQUIRED.value in result.names()


def test_valid_planned_special_exposure_escalates():
    result = evaluate(
        TriggerSignals(
            planned_special_exposure_valid=True,
        )
    )

    assert Trigger.PLANNED_SPECIAL_EXPOSURE_VALID.value in result.names()


def test_multiple_signals_all_fire():
    result = evaluate(
        TriggerSignals(
            fields_below_floor=["lens_dose"],
            insufficient_data_rules=["R3"],
            prompt_attack_fired=True,
            notification_required_rules=["R1"],
            planned_special_exposure_valid=True,
        )
    )

    assert result.escalates is True

    assert set(result.names()) == {
        Trigger.FIELD_BELOW_FLOOR.value,
        Trigger.INSUFFICIENT_DATA.value,
        Trigger.PROMPT_ATTACK_FIRED.value,
        Trigger.NOTIFICATION_REQUIRED.value,
        Trigger.PLANNED_SPECIAL_EXPOSURE_VALID.value,
    }


def test_unresolved_citation_escalates():
    result = evaluate(
        TriggerSignals(
            unresolved_citations=["20.2203(a)"],
        )
    )

    assert Trigger.CITATION_FAILED.value in result.names()


def test_near_boundary_escalates():
    result = evaluate(
        TriggerSignals(
            near_boundary_rules=["R1"],
        )
    )

    assert Trigger.NEAR_BOUNDARY.value in result.names()


def test_annual_limit_escalates():
    result = evaluate(
        TriggerSignals(
            doses_at_or_above_annual_limit=["TEDE"],
        )
    )

    assert Trigger.AT_OR_ABOVE_ANNUAL_LIMIT.value in result.names()


def test_photo_contradiction_escalates():
    result = evaluate(
        TriggerSignals(
            photo_contradicts_narrative=True,
        )
    )

    assert Trigger.PHOTO_CONTRADICTS_NARRATIVE.value in result.names()
