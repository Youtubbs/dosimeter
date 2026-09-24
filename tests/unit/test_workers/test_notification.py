"""Tests for the Notification Worker."""

from dosimeter.domain.rules import (
    RuleOutcome,
    RuleResult,
    RuleSource,
)
from dosimeter.workers.models import NotificationClock
from dosimeter.workers.notification import build_notification_proposal


SOURCE_R1 = RuleSource(
    citation="10 CFR 20.2202(a)",
    section="Immediate notification",
    status="in_force",
)

SOURCE_R2 = RuleSource(
    citation="10 CFR 20.2202(b)",
    section="Twenty-four hour notification",
    status="in_force",
)


def make_result(
    rule_id: str,
    outcome: RuleOutcome,
    source: RuleSource,
    *,
    missing_fields: tuple[str, ...] = (),
) -> RuleResult:
    """Create a deterministic rule result for worker tests."""

    return RuleResult(
        rule_id=rule_id,
        outcome=outcome,
        sources=(source,),
        inputs_used={},
        threshold={},
        explanation=f"{rule_id} test result.",
        missing_fields=missing_fields,
    )


def test_r1_required_proposes_immediate_notification() -> None:
    r1 = make_result(
        "R1",
        RuleOutcome.REQUIRED,
        SOURCE_R1,
    )

    r2 = make_result(
        "R2",
        RuleOutcome.NOT_REQUIRED,
        SOURCE_R2,
    )

    result = build_notification_proposal(
        r1_result=r1,
        r2_result=r2,
    )

    assert result.notification_required is True
    assert result.clock == NotificationClock.IMMEDIATE


def test_r2_required_proposes_twenty_four_hour_notification() -> None:
    r1 = make_result(
        "R1",
        RuleOutcome.NOT_REQUIRED,
        SOURCE_R1,
    )

    r2 = make_result(
        "R2",
        RuleOutcome.REQUIRED,
        SOURCE_R2,
    )

    result = build_notification_proposal(
        r1_result=r1,
        r2_result=r2,
    )

    assert result.notification_required is True
    assert result.clock == NotificationClock.TWENTY_FOUR_HOUR


def test_r1_takes_priority_when_both_rules_require_notification() -> None:
    r1 = make_result(
        "R1",
        RuleOutcome.REQUIRED,
        SOURCE_R1,
    )

    r2 = make_result(
        "R2",
        RuleOutcome.REQUIRED,
        SOURCE_R2,
    )

    result = build_notification_proposal(
        r1_result=r1,
        r2_result=r2,
    )

    assert result.notification_required is True
    assert result.clock == NotificationClock.IMMEDIATE


def test_no_notification_when_neither_rule_fires() -> None:
    r1 = make_result(
        "R1",
        RuleOutcome.NOT_REQUIRED,
        SOURCE_R1,
    )

    r2 = make_result(
        "R2",
        RuleOutcome.NOT_REQUIRED,
        SOURCE_R2,
    )

    result = build_notification_proposal(
        r1_result=r1,
        r2_result=r2,
    )

    assert result.notification_required is False
    assert result.clock == NotificationClock.NONE


def test_insufficient_data_is_preserved() -> None:
    r1 = make_result(
        "R1",
        RuleOutcome.INSUFFICIENT_DATA,
        SOURCE_R1,
        missing_fields=("annual_tede",),
    )

    r2 = make_result(
        "R2",
        RuleOutcome.NOT_REQUIRED,
        SOURCE_R2,
    )

    result = build_notification_proposal(
        r1_result=r1,
        r2_result=r2,
    )

    assert result.notification_required is False
    assert result.clock == NotificationClock.NONE
    assert "annual_tede" in result.missing_fields


def test_notification_proposal_contains_rule_results() -> None:
    r1 = make_result(
        "R1",
        RuleOutcome.REQUIRED,
        SOURCE_R1,
    )

    r2 = make_result(
        "R2",
        RuleOutcome.NOT_REQUIRED,
        SOURCE_R2,
    )

    result = build_notification_proposal(
        r1_result=r1,
        r2_result=r2,
    )

    assert result.rule_results == (r1, r2)


def test_notification_proposal_preserves_citations() -> None:
    r1 = make_result(
        "R1",
        RuleOutcome.REQUIRED,
        SOURCE_R1,
    )

    r2 = make_result(
        "R2",
        RuleOutcome.NOT_REQUIRED,
        SOURCE_R2,
    )

    result = build_notification_proposal(
        r1_result=r1,
        r2_result=r2,
    )

    assert "10 CFR 20.2202(a)" in result.citations
    assert "10 CFR 20.2202(b)" in result.citations
