"""R1 — immediate notification under 10 CFR 20.2202(a)."""

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



# Regulatory thresholds


R1_TEDE_THRESHOLD = TEDEThreshold(
    value=25.0,
    unit=DoseUnit.REM,
)

R1_LENS_THRESHOLD = LensThreshold(
    value=75.0,
    unit=DoseUnit.REM,
)

R1_SHALLOW_THRESHOLD = ShallowThreshold(
    value=250.0,
    unit=DoseUnit.RAD,
)

R1_INTAKE_THRESHOLD = 5.0



# Regulatory source
# ---------------------------------------------------------------------------

R1_SOURCE = RuleSource(
    citation="10 CFR 20.2202(a)",
    section="Immediate notification",
    status="in_force",
)



# R1
# ---------------------------------------------------------------------------


def evaluate_r1(
    *,
    tede: TotalEffectiveDoseEquivalent | None,
    lens: LensDoseEquivalent | None,
    shallow: ShallowDoseEquivalent | None,
    intake: IntakeMultipleOfALI | None,
) -> RuleResult:
    """Evaluate whether immediate notification is required."""

    values = {
        "tede": tede,
        "lens": lens,
        "shallow": shallow,
        "intake": intake,
    }

    
    # Missing-data check
    # ------------------------------------------------------------------

    missing_fields = tuple(
        name for name, value in values.items() if value is None
    )

    if missing_fields:
        return RuleResult(
            rule_id="R1",
            outcome=RuleOutcome.INSUFFICIENT_DATA,
            sources=(R1_SOURCE,),
            inputs_used={
                name: value
                for name, value in values.items()
                if value is not None
            },
            threshold=None,
            explanation=(
                "Immediate-notification determination cannot be completed "
                "because required inputs are missing."
            ),
            missing_fields=missing_fields,
        )

    # After the missing-data check, all four values are present.
    assert tede is not None
    assert lens is not None
    assert shallow is not None
    assert intake is not None

    
    # Unit validation
    # ------------------------------------------------------------------

    invalid_units: list[str] = []

    if tede.unit != R1_TEDE_THRESHOLD.unit:
        invalid_units.append("tede")

    if lens.unit != R1_LENS_THRESHOLD.unit:
        invalid_units.append("lens")

    if shallow.unit != R1_SHALLOW_THRESHOLD.unit:
        invalid_units.append("shallow")

    if invalid_units:
        return RuleResult(
            rule_id="R1",
            outcome=RuleOutcome.INSUFFICIENT_DATA,
            sources=(R1_SOURCE,),
            inputs_used=values,
            threshold={
                "tede": R1_TEDE_THRESHOLD,
                "lens": R1_LENS_THRESHOLD,
                "shallow": R1_SHALLOW_THRESHOLD,
                "intake_multiple_of_ali": R1_INTAKE_THRESHOLD,
            },
            explanation=(
                "Immediate-notification determination cannot be completed "
                "because one or more dose quantities use units that cannot "
                "be compared directly with the regulatory thresholds."
            ),
            missing_fields=tuple(
                f"{field}_compatible_unit" for field in invalid_units
            ),
        )

    
    # Threshold comparisons
    #
    # R1 uses inclusive comparisons because the regulation uses
    # threshold values of the stated amount "or more."
    # ------------------------------------------------------------------

    triggered_conditions: list[str] = []

    if tede.value >= R1_TEDE_THRESHOLD.value:
        triggered_conditions.append("tede")

    if lens.value >= R1_LENS_THRESHOLD.value:
        triggered_conditions.append("lens")

    if shallow.value >= R1_SHALLOW_THRESHOLD.value:
        triggered_conditions.append("shallow")

    if intake.value >= R1_INTAKE_THRESHOLD:
        triggered_conditions.append("intake")

    thresholds = {
        "tede": R1_TEDE_THRESHOLD,
        "lens": R1_LENS_THRESHOLD,
        "shallow": R1_SHALLOW_THRESHOLD,
        "intake_multiple_of_ali": R1_INTAKE_THRESHOLD,
    }

    # ------------------------------------------------------------------
    # Immediate notification required
    # ------------------------------------------------------------------

    if triggered_conditions:
        return RuleResult(
            rule_id="R1",
            outcome=RuleOutcome.REQUIRED,
            sources=(R1_SOURCE,),
            inputs_used=values,
            threshold=thresholds,
            explanation=(
                "Immediate notification is required because one or more "
                "dose or intake values met or exceeded an R1 threshold."
            ),
            failing_conditions=tuple(triggered_conditions),
        )

    
    # Immediate notification not required
    # ------------------------------------------------------------------

    return RuleResult(
        rule_id="R1",
        outcome=RuleOutcome.NOT_REQUIRED,
        sources=(R1_SOURCE,),
        inputs_used=values,
        threshold=thresholds,
        explanation=(
            "Immediate notification is not required because none of the "
            "dose or intake values met or exceeded an R1 threshold."
        ),
    )
