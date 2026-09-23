"""R2 — 24-hour notification under 10 CFR 20.2202(b)."""

from dosimeter.domain.dose import (
    DoseUnit,
    IntakeMultipleOfALI,
    LensDoseEquivalent,
    LensThreshold,
    ShallowDoseEquivalent,
    ShallowThreshold,
    TEDEThreshold,
    TotalEffectiveDoseEquivalent,
)
from dosimeter.domain.rules import RuleOutcome, RuleResult, RuleSource


R2_TEDE_THRESHOLD = TEDEThreshold(
    value=5.0,
    unit=DoseUnit.REM,
)

R2_LENS_THRESHOLD = LensThreshold(
    value=15.0,
    unit=DoseUnit.REM,
)

R2_SHALLOW_THRESHOLD = ShallowThreshold(
    value=50.0,
    unit=DoseUnit.REM,
)

R2_INTAKE_THRESHOLD = 1.0


R2_SOURCE = RuleSource(
    citation="10 CFR 20.2202(b)",
    section="Twenty-four hour notification",
    status="in_force",
)


def evaluate_r2(
    *,
    loss_of_control: bool | None,
    tede: TotalEffectiveDoseEquivalent | None,
    lens: LensDoseEquivalent | None,
    shallow: ShallowDoseEquivalent | None,
    intake: IntakeMultipleOfALI | None,
) -> RuleResult:
    """Evaluate whether 24-hour notification is required."""

    values = {
        "loss_of_control": loss_of_control,
        "tede": tede,
        "lens": lens,
        "shallow": shallow,
        "intake": intake,
    }

    missing_fields = tuple(name for name, value in values.items() if value is None)

    if missing_fields:
        return RuleResult(
            rule_id="R2",
            outcome=RuleOutcome.INSUFFICIENT_DATA,
            sources=(R2_SOURCE,),
            inputs_used={name: value for name, value in values.items() if value is not None},
            threshold=None,
            explanation=(
                "The 24-hour notification determination cannot be "
                "completed because required inputs are missing."
            ),
            missing_fields=missing_fields,
        )

    assert loss_of_control is not None
    assert tede is not None
    assert lens is not None
    assert shallow is not None
    assert intake is not None

    invalid_units: list[str] = []

    if tede.unit != R2_TEDE_THRESHOLD.unit:
        invalid_units.append("tede")

    if lens.unit != R2_LENS_THRESHOLD.unit:
        invalid_units.append("lens")

    if shallow.unit != R2_SHALLOW_THRESHOLD.unit:
        invalid_units.append("shallow")

    thresholds = {
        "tede": R2_TEDE_THRESHOLD,
        "lens": R2_LENS_THRESHOLD,
        "shallow": R2_SHALLOW_THRESHOLD,
        "intake_multiple_of_ali": R2_INTAKE_THRESHOLD,
    }

    if invalid_units:
        return RuleResult(
            rule_id="R2",
            outcome=RuleOutcome.INSUFFICIENT_DATA,
            sources=(R2_SOURCE,),
            inputs_used=values,
            threshold=thresholds,
            explanation=(
                "The 24-hour notification determination cannot be "
                "completed because one or more dose quantities use "
                "incompatible units."
            ),
            missing_fields=tuple(f"{field}_compatible_unit" for field in invalid_units),
        )

    # R2 requires loss of control in addition to a threshold exceedance.
    if not loss_of_control:
        return RuleResult(
            rule_id="R2",
            outcome=RuleOutcome.NOT_REQUIRED,
            sources=(R2_SOURCE,),
            inputs_used=values,
            threshold=thresholds,
            explanation=(
                "Twenty-four hour notification is not required because "
                "the event did not involve loss of control."
            ),
        )

    triggered_conditions: list[str] = []

    # R2 uses strict > comparisons rather than >=.
    if tede.value > R2_TEDE_THRESHOLD.value:
        triggered_conditions.append("tede")

    if lens.value > R2_LENS_THRESHOLD.value:
        triggered_conditions.append("lens")

    if shallow.value > R2_SHALLOW_THRESHOLD.value:
        triggered_conditions.append("shallow")

    if intake.value > R2_INTAKE_THRESHOLD:
        triggered_conditions.append("intake")

    if triggered_conditions:
        return RuleResult(
            rule_id="R2",
            outcome=RuleOutcome.REQUIRED,
            sources=(R2_SOURCE,),
            inputs_used=values,
            threshold=thresholds,
            explanation=(
                "Twenty-four hour notification is required because the "
                "event involved loss of control and one or more applicable "
                "dose or intake thresholds were exceeded."
            ),
            failing_conditions=tuple(triggered_conditions),
        )

    return RuleResult(
        rule_id="R2",
        outcome=RuleOutcome.NOT_REQUIRED,
        sources=(R2_SOURCE,),
        inputs_used=values,
        threshold=thresholds,
        explanation=(
            "Twenty-four hour notification is not required because none "
            "of the applicable dose or intake thresholds were exceeded."
        ),
    )
