"""Tests for the Written Report Worker."""

from dosimeter.domain.rules import (
    RuleOutcome,
    RuleResult,
    RuleSource,
)
from dosimeter.workers.models import ReportingPath
from dosimeter.workers.written_report import (
    build_written_report_proposal,
)


SOURCE_R3 = RuleSource(
    citation="10 CFR 20.2203",
    section="Reports of exposures and radiation levels",
    status="in_force",
)

SOURCE_R4 = RuleSource(
    citation="10 CFR 20.1206",
    section="Planned special exposures",
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


def test_r3_required_proposes_section_20_2203_report() -> None:
    r3 = make_result(
        "R3",
        RuleOutcome.REQUIRED,
        SOURCE_R3,
    )

    r4 = make_result(
        "R4",
        RuleOutcome.INVALID,
        SOURCE_R4,
    )

    result = build_written_report_proposal(
        r3_result=r3,
        r4_result=r4,
    )

    assert result.report_required is True
    assert result.reporting_path == ReportingPath.SECTION_20_2203


def test_valid_pse_uses_section_20_2204_path() -> None:
    r3 = make_result(
        "R3",
        RuleOutcome.NOT_REQUIRED,
        SOURCE_R3,
    )

    r4 = make_result(
        "R4",
        RuleOutcome.VALID,
        SOURCE_R4,
    )

    result = build_written_report_proposal(
        r3_result=r3,
        r4_result=r4,
    )

    assert result.report_required is True
    assert result.reporting_path == ReportingPath.SECTION_20_2204


def test_valid_pse_path_takes_priority_over_r3() -> None:
    r3 = make_result(
        "R3",
        RuleOutcome.REQUIRED,
        SOURCE_R3,
    )

    r4 = make_result(
        "R4",
        RuleOutcome.VALID,
        SOURCE_R4,
    )

    result = build_written_report_proposal(
        r3_result=r3,
        r4_result=r4,
    )

    assert result.report_required is True
    assert result.reporting_path == ReportingPath.SECTION_20_2204


def test_no_report_when_neither_path_applies() -> None:
    r3 = make_result(
        "R3",
        RuleOutcome.NOT_REQUIRED,
        SOURCE_R3,
    )

    r4 = make_result(
        "R4",
        RuleOutcome.INVALID,
        SOURCE_R4,
    )

    result = build_written_report_proposal(
        r3_result=r3,
        r4_result=r4,
    )

    assert result.report_required is False
    assert result.reporting_path == ReportingPath.NONE


def test_insufficient_r3_data_is_preserved() -> None:
    r3 = make_result(
        "R3",
        RuleOutcome.INSUFFICIENT_DATA,
        SOURCE_R3,
        missing_fields=("annual_tede",),
    )

    r4 = make_result(
        "R4",
        RuleOutcome.INVALID,
        SOURCE_R4,
    )

    result = build_written_report_proposal(
        r3_result=r3,
        r4_result=r4,
    )

    assert result.report_required is False
    assert result.reporting_path == ReportingPath.NONE
    assert "annual_tede" in result.missing_fields


def test_insufficient_r4_data_is_preserved() -> None:
    r3 = make_result(
        "R3",
        RuleOutcome.NOT_REQUIRED,
        SOURCE_R3,
    )

    r4 = make_result(
        "R4",
        RuleOutcome.INSUFFICIENT_DATA,
        SOURCE_R4,
        missing_fields=("written_authorization",),
    )

    result = build_written_report_proposal(
        r3_result=r3,
        r4_result=r4,
    )

    assert result.report_required is False
    assert result.reporting_path == ReportingPath.NONE
    assert "written_authorization" in result.missing_fields


def test_written_report_proposal_contains_rule_results() -> None:
    r3 = make_result(
        "R3",
        RuleOutcome.REQUIRED,
        SOURCE_R3,
    )

    r4 = make_result(
        "R4",
        RuleOutcome.INVALID,
        SOURCE_R4,
    )

    result = build_written_report_proposal(
        r3_result=r3,
        r4_result=r4,
    )

    assert result.rule_results == (r3, r4)


def test_written_report_proposal_preserves_citations() -> None:
    r3 = make_result(
        "R3",
        RuleOutcome.REQUIRED,
        SOURCE_R3,
    )

    r4 = make_result(
        "R4",
        RuleOutcome.INVALID,
        SOURCE_R4,
    )

    result = build_written_report_proposal(
        r3_result=r3,
        r4_result=r4,
    )

    assert "10 CFR 20.2203" in result.citations
    assert "10 CFR 20.1206" in result.citations
