"""R4 — Planned Special Exposure validation under 10 CFR 20.1206."""

from pydantic import BaseModel, ConfigDict, Field

from dosimeter.domain.rules import RuleOutcome, RuleResult, RuleSource


class PSEConditions(BaseModel):
    """Evidence required to validate a planned special exposure."""

    model_config = ConfigDict(
        strict=True,
        frozen=True,
        extra="forbid",
    )

    # § 20.1206(a)
    exceptional_situation: bool | None = None
    alternatives_unavailable_or_impractical: bool | None = None

    # § 20.1206(b)
    licensee_written_authorization: bool | None = None
    employer_written_authorization: bool | None = None
    authorization_before_exposure: bool | None = None

    # § 20.1206(c)
    worker_informed_of_purpose: bool | None = None
    worker_informed_of_estimated_dose_and_risks: bool | None = None
    worker_instructed_in_alara_measures: bool | None = None

    # § 20.1206(d)
    prior_lifetime_doses_ascertained: bool | None = None

    # § 20.1206(e)
    annual_pse_limit_satisfied: bool | None = None
    lifetime_pse_limit_satisfied: bool | None = None

    # § 20.1206(f)
    required_records_maintained: bool | None = None
    report_under_20_2204_submitted: bool | None = None

    # § 20.1206(g)
    best_dose_estimate_recorded: bool | None = None
    worker_informed_of_dose_in_writing: bool | None = None
    worker_informed_within_30_days: bool | None = None


R4_SOURCE = RuleSource(
    citation="10 CFR 20.1206(a)-(g)",
    section="Planned special exposures",
    status="in_force",
)

R4_REPORT_SOURCE = RuleSource(
    citation="10 CFR 20.2204",
    section="Reports of planned special exposures",
    status="in_force",
)


def evaluate_r4(conditions: PSEConditions) -> RuleResult:
    """Determine whether a planned special exposure satisfies § 20.1206."""

    values = conditions.model_dump()

    # ---------------------------------------------------------------
    # Missing evidence
    # ---------------------------------------------------------------
    missing_fields = tuple(
        name for name, value in values.items() if value is None
    )

    if missing_fields:
        return RuleResult(
            rule_id="R4",
            outcome=RuleOutcome.INSUFFICIENT_DATA,
            sources=(R4_SOURCE, R4_REPORT_SOURCE),
            inputs_used=values,
            threshold=None,
            explanation=(
                "The planned special exposure cannot be validated because "
                "evidence required by 10 CFR 20.1206 is missing."
            ),
            missing_fields=missing_fields,
        )

    # ---------------------------------------------------------------
    # § 20.1206(a)
    # Exceptional situation and alternatives unavailable/impractical.
    # ---------------------------------------------------------------
    condition_a = (
        conditions.exceptional_situation is True
        and conditions.alternatives_unavailable_or_impractical is True
    )

    # ---------------------------------------------------------------
    # § 20.1206(b)
    # Required written authorization must exist BEFORE exposure.
    # ---------------------------------------------------------------
    condition_b = (
        conditions.licensee_written_authorization is True
        and conditions.employer_written_authorization is True
        and conditions.authorization_before_exposure is True
    )

    # ---------------------------------------------------------------
    # § 20.1206(c)
    # Worker informed of purpose, dose/risk, and ALARA measures.
    # ---------------------------------------------------------------
    condition_c = (
        conditions.worker_informed_of_purpose is True
        and conditions.worker_informed_of_estimated_dose_and_risks is True
        and conditions.worker_instructed_in_alara_measures is True
    )

    # ---------------------------------------------------------------
    # § 20.1206(d)
    # Prior lifetime doses must be ascertained.
    # ---------------------------------------------------------------
    condition_d = conditions.prior_lifetime_doses_ascertained is True

    # ---------------------------------------------------------------
    # § 20.1206(e)
    # Both annual and lifetime PSE limits must be satisfied.
    # ---------------------------------------------------------------

    condition_e = (
        conditions.annual_pse_limit_satisfied is True
        and conditions.lifetime_pse_limit_satisfied is True
    )

    # ---------------------------------------------------------------
    # § 20.1206(f)
    # Required records and § 20.2204 report.
    # ---------------------------------------------------------------
    condition_f = (
        conditions.required_records_maintained is True
        and conditions.report_under_20_2204_submitted is True
    )

    # ---------------------------------------------------------------
    # § 20.1206(g)
    # Dose recorded and worker informed in writing within 30 days.
    # ---------------------------------------------------------------
    condition_g = (
        conditions.best_dose_estimate_recorded is True
        and conditions.worker_informed_of_dose_in_writing is True
        and conditions.worker_informed_within_30_days is True
    )

    condition_results = {
        "20.1206(a)": condition_a,
        "20.1206(b)": condition_b,
        "20.1206(c)": condition_c,
        "20.1206(d)": condition_d,
        "20.1206(e)": condition_e,
        "20.1206(f)": condition_f,
        "20.1206(g)": condition_g,
    }

    failing_conditions = tuple(
        condition
        for condition, passed in condition_results.items()
        if not passed
    )

    # ---------------------------------------------------------------
    # Any failed condition makes the PSE invalid.
    # ---------------------------------------------------------------
    if failing_conditions:
        return RuleResult(
            rule_id="R4",
            outcome=RuleOutcome.INVALID,
            sources=(R4_SOURCE, R4_REPORT_SOURCE),
            inputs_used=values,
            threshold={
                "required_conditions": tuple(condition_results),
            },
            explanation=(
                "The planned special exposure is invalid because one or "
                "more conditions required by 10 CFR 20.1206 were not met."
            ),
            failing_conditions=failing_conditions,
        )

    # ---------------------------------------------------------------
    # All seven conditions passed.
    # ---------------------------------------------------------------
    return RuleResult(
        rule_id="R4",
        outcome=RuleOutcome.VALID,
        sources=(R4_SOURCE, R4_REPORT_SOURCE),
        inputs_used=values,
        threshold={
            "required_conditions": tuple(condition_results),
        },
        explanation=(
            "The planned special exposure satisfies all seven conditions "
            "in 10 CFR 20.1206(a)-(g). The applicable planned-special-"
            "exposure reporting path is 10 CFR 20.2204."
        ),
    )
