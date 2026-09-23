"""Unit tests for R4 planned-special-exposure validation."""

from dosimeter.domain.rules import RuleOutcome
from dosimeter.rules.r4_planned_special_exposure import (
    PSEConditions,
    evaluate_r4,
)


def make_valid_pse(**overrides: bool | None) -> PSEConditions:
    """Create a PSE where every §20.1206(a)-(g) condition is satisfied."""

    values: dict[str, bool | None] = {
        # §20.1206(a)
        "exceptional_situation": True,
        "alternatives_unavailable_or_impractical": True,

        # §20.1206(b)
        "licensee_written_authorization": True,
        "employer_written_authorization": True,
        "authorization_before_exposure": True,

        # §20.1206(c)
        "worker_informed_of_purpose": True,
        "worker_informed_of_estimated_dose_and_risks": True,
        "worker_instructed_in_alara_measures": True,

        # §20.1206(d)
        "prior_lifetime_doses_ascertained": True,

        # §20.1206(e)
        "annual_pse_limit_satisfied": True,
        "lifetime_pse_limit_satisfied": True,

        # §20.1206(f)
        "required_records_maintained": True,
        "report_under_20_2204_submitted": True,

        # §20.1206(g)
        "best_dose_estimate_recorded": True,
        "worker_informed_of_dose_in_writing": True,
        "worker_informed_within_30_days": True,
    }

    values.update(overrides)

    return PSEConditions(**values)


# ---------------------------------------------------------------------------
# Fully valid PSE
# ---------------------------------------------------------------------------
def test_r4_valid_when_all_conditions_pass() -> None:
    result = evaluate_r4(make_valid_pse())

    assert result.outcome == RuleOutcome.VALID
    assert result.failing_conditions == ()


# ---------------------------------------------------------------------------
# §20.1206(a)
# ---------------------------------------------------------------------------
def test_r4_invalid_when_exceptional_situation_missing() -> None:
    result = evaluate_r4(
        make_valid_pse(
            exceptional_situation=False,
        )
    )

    assert result.outcome == RuleOutcome.INVALID
    assert result.failing_conditions == ("20.1206(a)",)


def test_r4_invalid_when_alternatives_are_available() -> None:
    result = evaluate_r4(
        make_valid_pse(
            alternatives_unavailable_or_impractical=False,
        )
    )

    assert result.outcome == RuleOutcome.INVALID
    assert result.failing_conditions == ("20.1206(a)",)


# ---------------------------------------------------------------------------
# §20.1206(b)
# ---------------------------------------------------------------------------
def test_r4_invalid_without_licensee_written_authorization() -> None:
    result = evaluate_r4(
        make_valid_pse(
            licensee_written_authorization=False,
        )
    )

    assert result.outcome == RuleOutcome.INVALID
    assert result.failing_conditions == ("20.1206(b)",)


def test_r4_invalid_without_employer_written_authorization() -> None:
    result = evaluate_r4(
        make_valid_pse(
            employer_written_authorization=False,
        )
    )

    assert result.outcome == RuleOutcome.INVALID
    assert result.failing_conditions == ("20.1206(b)",)


def test_r4_invalid_when_authorization_occurs_after_exposure() -> None:
    result = evaluate_r4(
        make_valid_pse(
            authorization_before_exposure=False,
        )
    )

    assert result.outcome == RuleOutcome.INVALID
    assert result.failing_conditions == ("20.1206(b)",)


# ---------------------------------------------------------------------------
# §20.1206(c)
# ---------------------------------------------------------------------------
def test_r4_invalid_when_worker_not_informed_of_purpose() -> None:
    result = evaluate_r4(
        make_valid_pse(
            worker_informed_of_purpose=False,
        )
    )

    assert result.outcome == RuleOutcome.INVALID
    assert result.failing_conditions == ("20.1206(c)",)


def test_r4_invalid_when_worker_not_informed_of_dose_and_risks() -> None:
    result = evaluate_r4(
        make_valid_pse(
            worker_informed_of_estimated_dose_and_risks=False,
        )
    )

    assert result.outcome == RuleOutcome.INVALID
    assert result.failing_conditions == ("20.1206(c)",)


def test_r4_invalid_without_alara_instruction() -> None:
    result = evaluate_r4(
        make_valid_pse(
            worker_instructed_in_alara_measures=False,
        )
    )

    assert result.outcome == RuleOutcome.INVALID
    assert result.failing_conditions == ("20.1206(c)",)


# ---------------------------------------------------------------------------
# §20.1206(d)
# ---------------------------------------------------------------------------
def test_r4_invalid_when_prior_lifetime_doses_not_ascertained() -> None:
    result = evaluate_r4(
        make_valid_pse(
            prior_lifetime_doses_ascertained=False,
        )
    )

    assert result.outcome == RuleOutcome.INVALID
    assert result.failing_conditions == ("20.1206(d)",)


# ---------------------------------------------------------------------------
# §20.1206(e)
# ---------------------------------------------------------------------------
def test_r4_invalid_when_annual_pse_limit_not_satisfied() -> None:
    result = evaluate_r4(
        make_valid_pse(
            annual_pse_limit_satisfied=False,
        )
    )

    assert result.outcome == RuleOutcome.INVALID
    assert result.failing_conditions == ("20.1206(e)",)


def test_r4_invalid_when_lifetime_pse_limit_not_satisfied() -> None:
    result = evaluate_r4(
        make_valid_pse(
            lifetime_pse_limit_satisfied=False,
        )
    )

    assert result.outcome == RuleOutcome.INVALID
    assert result.failing_conditions == ("20.1206(e)",)


# ---------------------------------------------------------------------------
# §20.1206(f)
# ---------------------------------------------------------------------------
def test_r4_invalid_when_required_records_not_maintained() -> None:
    result = evaluate_r4(
        make_valid_pse(
            required_records_maintained=False,
        )
    )

    assert result.outcome == RuleOutcome.INVALID
    assert result.failing_conditions == ("20.1206(f)",)


def test_r4_invalid_when_2204_report_not_submitted() -> None:
    result = evaluate_r4(
        make_valid_pse(
            report_under_20_2204_submitted=False,
        )
    )

    assert result.outcome == RuleOutcome.INVALID
    assert result.failing_conditions == ("20.1206(f)",)


# ---------------------------------------------------------------------------
# §20.1206(g)
# ---------------------------------------------------------------------------
def test_r4_invalid_when_best_dose_estimate_not_recorded() -> None:
    result = evaluate_r4(
        make_valid_pse(
            best_dose_estimate_recorded=False,
        )
    )

    assert result.outcome == RuleOutcome.INVALID
    assert result.failing_conditions == ("20.1206(g)",)


def test_r4_invalid_when_worker_not_informed_in_writing() -> None:
    result = evaluate_r4(
        make_valid_pse(
            worker_informed_of_dose_in_writing=False,
        )
    )

    assert result.outcome == RuleOutcome.INVALID
    assert result.failing_conditions == ("20.1206(g)",)


def test_r4_invalid_when_worker_not_informed_within_30_days() -> None:
    result = evaluate_r4(
        make_valid_pse(
            worker_informed_within_30_days=False,
        )
    )

    assert result.outcome == RuleOutcome.INVALID
    assert result.failing_conditions == ("20.1206(g)",)


# ---------------------------------------------------------------------------
# Multiple failures
# ---------------------------------------------------------------------------
def test_r4_reports_every_failed_condition() -> None:
    result = evaluate_r4(
        make_valid_pse(
            authorization_before_exposure=False,
            prior_lifetime_doses_ascertained=False,
            required_records_maintained=False,
        )
    )

    assert result.outcome == RuleOutcome.INVALID

    assert result.failing_conditions == (
        "20.1206(b)",
        "20.1206(d)",
        "20.1206(f)",
    )


def test_r4_reports_all_seven_conditions_when_all_fail() -> None:
    conditions = PSEConditions(
        exceptional_situation=False,
        alternatives_unavailable_or_impractical=False,
        licensee_written_authorization=False,
        employer_written_authorization=False,
        authorization_before_exposure=False,
        worker_informed_of_purpose=False,
        worker_informed_of_estimated_dose_and_risks=False,
        worker_instructed_in_alara_measures=False,
        prior_lifetime_doses_ascertained=False,
        annual_pse_limit_satisfied=False,
        lifetime_pse_limit_satisfied=False,
        required_records_maintained=False,
        report_under_20_2204_submitted=False,
        best_dose_estimate_recorded=False,
        worker_informed_of_dose_in_writing=False,
        worker_informed_within_30_days=False,
    )

    result = evaluate_r4(conditions)

    assert result.outcome == RuleOutcome.INVALID

    assert result.failing_conditions == (
        "20.1206(a)",
        "20.1206(b)",
        "20.1206(c)",
        "20.1206(d)",
        "20.1206(e)",
        "20.1206(f)",
        "20.1206(g)",
    )


# ---------------------------------------------------------------------------
# Missing evidence
# ---------------------------------------------------------------------------
def test_r4_missing_evidence_returns_insufficient_data() -> None:
    result = evaluate_r4(
        make_valid_pse(
            authorization_before_exposure=None,
        )
    )

    assert result.outcome == RuleOutcome.INSUFFICIENT_DATA
    assert result.missing_fields == ("authorization_before_exposure",)


def test_r4_reports_multiple_missing_fields() -> None:
    result = evaluate_r4(
        make_valid_pse(
            authorization_before_exposure=None,
            prior_lifetime_doses_ascertained=None,
            worker_informed_within_30_days=None,
        )
    )

    assert result.outcome == RuleOutcome.INSUFFICIENT_DATA

    assert result.missing_fields == (
        "authorization_before_exposure",
        "prior_lifetime_doses_ascertained",
        "worker_informed_within_30_days",
    )


# ---------------------------------------------------------------------------
# Regulatory source
# ---------------------------------------------------------------------------
def test_r4_contains_pse_regulatory_source() -> None:
    result = evaluate_r4(make_valid_pse())

    citations = {source.citation for source in result.sources}

    assert "10 CFR 20.1206(a)-(g)" in citations
    assert "10 CFR 20.2204" in citations
