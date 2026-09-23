"""R3 — written-report determination under 10 CFR 20.2203."""

from enum import Enum

from pydantic import BaseModel, ConfigDict

from dosimeter.domain.dose import (
    EmbryoFetusDoseEquivalent,
    LensDoseEquivalent,
    ShallowDoseEquivalent,
    TotalEffectiveDoseEquivalent,
    UnrestrictedAreaDose,
)
from dosimeter.domain.rules import RuleOutcome, RuleResult, RuleSource


# ---------------------------------------------------------------------------
# Exposure population
# ---------------------------------------------------------------------------
class ExposurePopulation(str, Enum):
    """Population used to select the applicable Part 20 dose limit."""

    ADULT_WORKER = "adult_worker"
    MINOR = "minor"
    DECLARED_PREGNANT_WORKER = "declared_pregnant_worker"
    MEMBER_OF_PUBLIC = "member_of_public"


# ---------------------------------------------------------------------------
# R3 inputs
# ---------------------------------------------------------------------------
class R3Inputs(BaseModel):
    """Inputs needed to evaluate the 10 CFR 20.2203 reporting rule."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    r1_required: bool
    r2_required: bool

    population: ExposurePopulation

    annual_tede: TotalEffectiveDoseEquivalent | None = None
    annual_lens: LensDoseEquivalent | None = None
    annual_shallow: ShallowDoseEquivalent | None = None

    embryo_fetus_dose: EmbryoFetusDoseEquivalent | None = None

    unrestricted_area_dose: UnrestrictedAreaDose | None = None

    planned_special_exposure_valid: bool = False


# ---------------------------------------------------------------------------
# Regulatory sources
# ---------------------------------------------------------------------------
R3_SOURCE = RuleSource(
    citation="10 CFR 20.2203(a)",
    section="Reports of exposures, radiation levels, and concentrations",
    status="in_force",
)

ADULT_LIMIT_SOURCE = RuleSource(
    citation="10 CFR 20.1201",
    section="Occupational dose limits for adults",
    status="in_force",
)

MINOR_LIMIT_SOURCE = RuleSource(
    citation="10 CFR 20.1207",
    section="Occupational dose limits for minors",
    status="in_force",
)

PREGNANCY_LIMIT_SOURCE = RuleSource(
    citation="10 CFR 20.1208",
    section="Dose equivalent to an embryo/fetus",
    status="in_force",
)

PUBLIC_LIMIT_SOURCE = RuleSource(
    citation="10 CFR 20.1301",
    section="Dose limits for individual members of the public",
    status="in_force",
)

PSE_SOURCE = RuleSource(
    citation="10 CFR 20.1206",
    section="Planned special exposures",
    status="in_force",
)

PSE_REPORT_SOURCE = RuleSource(
    citation="10 CFR 20.2204",
    section="Reports of planned special exposures",
    status="in_force",
)


# ---------------------------------------------------------------------------
# Regulatory limits
# ---------------------------------------------------------------------------
ADULT_TEDE_LIMIT_REM = 5.0
ADULT_LENS_LIMIT_REM = 15.0
ADULT_SHALLOW_LIMIT_REM = 50.0

MINOR_MULTIPLIER = 0.10

EMBRYO_FETUS_LIMIT_REM = 0.5

PUBLIC_ANNUAL_LIMIT_REM = 0.1

UNRESTRICTED_AREA_MULTIPLIER = 10.0


# ---------------------------------------------------------------------------
# R3
# ---------------------------------------------------------------------------
def evaluate_r3(inputs: R3Inputs) -> RuleResult:
    """Determine whether a written report is required under 10 CFR 20.2203."""

    inputs_used = inputs.model_dump()

    # ------------------------------------------------------------------
    # Branch 1:
    # Notification was required under R1 or R2.
    # ------------------------------------------------------------------

    if inputs.r1_required or inputs.r2_required:
        triggered_conditions: list[str] = []

        if inputs.r1_required:
            triggered_conditions.append("r1_notification_required")

        if inputs.r2_required:
            triggered_conditions.append("r2_notification_required")

        return RuleResult(
            rule_id="R3",
            outcome=RuleOutcome.REQUIRED,
            sources=(R3_SOURCE,),
            inputs_used=inputs_used,
            threshold={
                "notification_required": True,
            },
            explanation=(
                "A written report is required because a notification "
                "was required under the applicable notification rule."
            ),
            failing_conditions=tuple(triggered_conditions),
        )

    # ------------------------------------------------------------------
    # Planned Special Exposure exception.
    #
    # A valid PSE follows the 10 CFR 20.2204 reporting path rather than
    # being treated as an ordinary 10 CFR 20.1201 dose-limit exceedance.
    # ------------------------------------------------------------------

    if inputs.planned_special_exposure_valid:
        return RuleResult(
            rule_id="R3",
            outcome=RuleOutcome.NOT_REQUIRED,
            sources=(
                R3_SOURCE,
                PSE_SOURCE,
                PSE_REPORT_SOURCE,
            ),
            inputs_used=inputs_used,
            threshold={
                "planned_special_exposure_valid": True,
            },
            explanation=(
                "A 10 CFR 20.2203 report is not required on the ordinary "
                "dose-limit path because the exposure is a valid planned "
                "special exposure under 10 CFR 20.1206. The planned "
                "special exposure uses the 10 CFR 20.2204 reporting path."
            ),
        )

    # ------------------------------------------------------------------
    # Branch 2:
    # Applicable annual dose limits.
    # ------------------------------------------------------------------

    triggered_conditions = []

    # ------------------------------------------------------------------
    # Adult worker
    # ------------------------------------------------------------------

    if inputs.population == ExposurePopulation.ADULT_WORKER:
        missing_fields: list[str] = []

        if inputs.annual_tede is None:
            missing_fields.append("annual_tede")

        if inputs.annual_lens is None:
            missing_fields.append("annual_lens")

        if inputs.annual_shallow is None:
            missing_fields.append("annual_shallow")

        if missing_fields:
            return RuleResult(
                rule_id="R3",
                outcome=RuleOutcome.INSUFFICIENT_DATA,
                sources=(R3_SOURCE, ADULT_LIMIT_SOURCE),
                inputs_used=inputs_used,
                threshold={
                    "annual_tede_rem": ADULT_TEDE_LIMIT_REM,
                    "annual_lens_rem": ADULT_LENS_LIMIT_REM,
                    "annual_shallow_rem": ADULT_SHALLOW_LIMIT_REM,
                },
                explanation=(
                    "The written-report determination cannot be completed "
                    "because required annual dose information is missing."
                ),
                missing_fields=tuple(missing_fields),
            )

        if inputs.annual_tede.value > ADULT_TEDE_LIMIT_REM:
            triggered_conditions.append("annual_tede")

        if inputs.annual_lens.value > ADULT_LENS_LIMIT_REM:
            triggered_conditions.append("annual_lens")

        if inputs.annual_shallow.value > ADULT_SHALLOW_LIMIT_REM:
            triggered_conditions.append("annual_shallow")

        applicable_source = ADULT_LIMIT_SOURCE

        thresholds = {
            "annual_tede_rem": ADULT_TEDE_LIMIT_REM,
            "annual_lens_rem": ADULT_LENS_LIMIT_REM,
            "annual_shallow_rem": ADULT_SHALLOW_LIMIT_REM,
        }

    # ------------------------------------------------------------------
    # Minor
    # ------------------------------------------------------------------

    elif inputs.population == ExposurePopulation.MINOR:
        missing_fields = []

        if inputs.annual_tede is None:
            missing_fields.append("annual_tede")

        if inputs.annual_lens is None:
            missing_fields.append("annual_lens")

        if inputs.annual_shallow is None:
            missing_fields.append("annual_shallow")

        minor_tede_limit = ADULT_TEDE_LIMIT_REM * MINOR_MULTIPLIER
        minor_lens_limit = ADULT_LENS_LIMIT_REM * MINOR_MULTIPLIER
        minor_shallow_limit = ADULT_SHALLOW_LIMIT_REM * MINOR_MULTIPLIER

        thresholds = {
            "annual_tede_rem": minor_tede_limit,
            "annual_lens_rem": minor_lens_limit,
            "annual_shallow_rem": minor_shallow_limit,
        }

        if missing_fields:
            return RuleResult(
                rule_id="R3",
                outcome=RuleOutcome.INSUFFICIENT_DATA,
                sources=(R3_SOURCE, MINOR_LIMIT_SOURCE),
                inputs_used=inputs_used,
                threshold=thresholds,
                explanation=(
                    "The written-report determination cannot be completed "
                    "because required annual dose information is missing."
                ),
                missing_fields=tuple(missing_fields),
            )

        if inputs.annual_tede.value > minor_tede_limit:
            triggered_conditions.append("annual_tede")

        if inputs.annual_lens.value > minor_lens_limit:
            triggered_conditions.append("annual_lens")

        if inputs.annual_shallow.value > minor_shallow_limit:
            triggered_conditions.append("annual_shallow")

        applicable_source = MINOR_LIMIT_SOURCE

    # ------------------------------------------------------------------
    # Declared pregnant worker
    # ------------------------------------------------------------------

    elif inputs.population == ExposurePopulation.DECLARED_PREGNANT_WORKER:
        thresholds = {
            "embryo_fetus_rem": EMBRYO_FETUS_LIMIT_REM,
        }

        if inputs.embryo_fetus_dose is None:
            return RuleResult(
                rule_id="R3",
                outcome=RuleOutcome.INSUFFICIENT_DATA,
                sources=(R3_SOURCE, PREGNANCY_LIMIT_SOURCE),
                inputs_used=inputs_used,
                threshold=thresholds,
                explanation=(
                    "The written-report determination cannot be completed "
                    "because the required embryo/fetus dose information "
                    "is missing."
                ),
                missing_fields=("embryo_fetus_dose",),
            )

        if inputs.embryo_fetus_dose.value > EMBRYO_FETUS_LIMIT_REM:
            triggered_conditions.append("embryo_fetus_dose")

        applicable_source = PREGNANCY_LIMIT_SOURCE

    # ------------------------------------------------------------------
    # Member of public
    # ------------------------------------------------------------------

    else:
        thresholds = {
            "public_annual_rem": PUBLIC_ANNUAL_LIMIT_REM,
        }

        if inputs.annual_tede is None:
            return RuleResult(
                rule_id="R3",
                outcome=RuleOutcome.INSUFFICIENT_DATA,
                sources=(R3_SOURCE, PUBLIC_LIMIT_SOURCE),
                inputs_used=inputs_used,
                threshold=thresholds,
                explanation=(
                    "The written-report determination cannot be completed "
                    "because the required annual public-dose information "
                    "is missing."
                ),
                missing_fields=("annual_tede",),
            )

        if inputs.annual_tede.value > PUBLIC_ANNUAL_LIMIT_REM:
            triggered_conditions.append("annual_public_dose")

        applicable_source = PUBLIC_LIMIT_SOURCE

    # ------------------------------------------------------------------
    # Branch 3:
    # Unrestricted-area radiation level greater than 10 times the
    # applicable public limit.
    # ------------------------------------------------------------------

    if inputs.unrestricted_area_dose is not None:
        unrestricted_limit = (
            PUBLIC_ANNUAL_LIMIT_REM * UNRESTRICTED_AREA_MULTIPLIER
        )

        thresholds["unrestricted_area_rem"] = unrestricted_limit

        if inputs.unrestricted_area_dose.value > unrestricted_limit:
            triggered_conditions.append("unrestricted_area_dose")

    # ------------------------------------------------------------------
    # Final result
    # ------------------------------------------------------------------

    if triggered_conditions:
        return RuleResult(
            rule_id="R3",
            outcome=RuleOutcome.REQUIRED,
            sources=(R3_SOURCE, applicable_source),
            inputs_used=inputs_used,
            threshold=thresholds,
            explanation=(
                "A written report is required because one or more "
                "applicable dose or radiation-level limits were exceeded."
            ),
            failing_conditions=tuple(triggered_conditions),
        )

    return RuleResult(
        rule_id="R3",
        outcome=RuleOutcome.NOT_REQUIRED,
        sources=(R3_SOURCE, applicable_source),
        inputs_used=inputs_used,
        threshold=thresholds,
        explanation=(
            "A written report is not required because no applicable "
            "notification, dose-limit, or radiation-level reporting "
            "condition was met."
        ),
    )
