"""Unit tests for R5 extraction-confidence and readiness guard."""

import pytest

from dosimeter.domain.rules import RuleOutcome
from dosimeter.rules.r5_confidence import (
    DEFAULT_CONFIDENCE_FLOOR,
    ExtractedFieldConfidence,
    R5Inputs,
    evaluate_r5,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def make_field(
    field_name: str,
    confidence: float,
) -> ExtractedFieldConfidence:
    """Create an extracted field with a confidence score."""

    return ExtractedFieldConfidence(
        field_name=field_name,
        confidence=confidence,
    )


# ---------------------------------------------------------------------------
# Normal confidence
# ---------------------------------------------------------------------------
def test_r5_passes_when_all_fields_above_floor() -> None:
    inputs = R5Inputs(
        fields=(
            make_field("annual_tede", 0.95),
            make_field("annual_lens", 0.88),
            make_field("annual_shallow", 0.76),
        ),
    )

    result = evaluate_r5(inputs)

    assert result.outcome == RuleOutcome.PASS
    assert result.failing_conditions == ()


# ---------------------------------------------------------------------------
# Required 0.60 boundary
# ---------------------------------------------------------------------------
def test_r5_exactly_at_confidence_floor_passes() -> None:
    """Exactly 0.60 is NOT below the configured confidence floor."""

    inputs = R5Inputs(
        fields=(
            make_field(
                "annual_tede",
                0.60,
            ),
        ),
    )

    result = evaluate_r5(inputs)

    assert result.outcome == RuleOutcome.PASS
    assert result.failing_conditions == ()


def test_r5_just_below_confidence_floor_requires_human() -> None:
    """0.5999 is below the 0.60 confidence floor."""

    inputs = R5Inputs(
        fields=(
            make_field(
                "annual_tede",
                0.5999,
            ),
        ),
    )

    result = evaluate_r5(inputs)

    assert result.outcome == RuleOutcome.HUMAN_DETERMINATION

    assert result.failing_conditions == ("annual_tede",)


def test_r5_just_above_confidence_floor_passes() -> None:
    inputs = R5Inputs(
        fields=(
            make_field(
                "annual_tede",
                0.6001,
            ),
        ),
    )

    result = evaluate_r5(inputs)

    assert result.outcome == RuleOutcome.PASS


# ---------------------------------------------------------------------------
# Parametrized confidence tests
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("confidence", "expected"),
    [
        (1.0, RuleOutcome.PASS),
        (0.90, RuleOutcome.PASS),
        (0.61, RuleOutcome.PASS),
        (0.6001, RuleOutcome.PASS),
        (0.60, RuleOutcome.PASS),
        (0.5999, RuleOutcome.HUMAN_DETERMINATION),
        (0.59, RuleOutcome.HUMAN_DETERMINATION),
        (0.20, RuleOutcome.HUMAN_DETERMINATION),
        (0.0, RuleOutcome.HUMAN_DETERMINATION),
    ],
)
def test_r5_confidence_boundary(
    confidence: float,
    expected: RuleOutcome,
) -> None:
    inputs = R5Inputs(
        fields=(
            make_field(
                "annual_tede",
                confidence,
            ),
        ),
    )

    result = evaluate_r5(inputs)

    assert result.outcome == expected


# ---------------------------------------------------------------------------
# Multiple fields
# ---------------------------------------------------------------------------
def test_r5_names_every_low_confidence_field() -> None:
    inputs = R5Inputs(
        fields=(
            make_field("annual_tede", 0.91),
            make_field("annual_lens", 0.43),
            make_field("annual_shallow", 0.57),
            make_field("loss_of_control", 0.82),
        ),
    )

    result = evaluate_r5(inputs)

    assert result.outcome == RuleOutcome.HUMAN_DETERMINATION

    assert result.failing_conditions == (
        "annual_lens",
        "annual_shallow",
    )


def test_r5_one_low_confidence_field_requires_human() -> None:
    inputs = R5Inputs(
        fields=(
            make_field("annual_tede", 0.99),
            make_field("annual_lens", 0.99),
            make_field("annual_shallow", 0.59),
        ),
    )

    result = evaluate_r5(inputs)

    assert result.outcome == RuleOutcome.HUMAN_DETERMINATION

    assert result.failing_conditions == ("annual_shallow",)


# ---------------------------------------------------------------------------
# Configurable floor
# ---------------------------------------------------------------------------
def test_r5_uses_default_confidence_floor() -> None:
    assert DEFAULT_CONFIDENCE_FLOOR == 0.60


def test_r5_accepts_configured_confidence_floor() -> None:
    inputs = R5Inputs(
        fields=(make_field("annual_tede", 0.74),),
    )

    result = evaluate_r5(
        inputs,
        confidence_floor=0.75,
    )

    assert result.outcome == RuleOutcome.HUMAN_DETERMINATION
    assert result.failing_conditions == ("annual_tede",)


def test_r5_exactly_at_custom_floor_passes() -> None:
    inputs = R5Inputs(
        fields=(make_field("annual_tede", 0.75),),
    )

    result = evaluate_r5(
        inputs,
        confidence_floor=0.75,
    )

    assert result.outcome == RuleOutcome.PASS


# ---------------------------------------------------------------------------
# Appendix C
# ---------------------------------------------------------------------------
def test_r5_appendix_c_path_returns_insufficient_data() -> None:
    inputs = R5Inputs(
        fields=(
            make_field("radionuclide", 0.99),
            make_field("activity", 0.99),
        ),
        requires_appendix_c=True,
    )

    result = evaluate_r5(inputs)

    assert result.outcome == RuleOutcome.INSUFFICIENT_DATA

    assert result.missing_fields == ("Appendix C to Part 20",)


def test_r5_appendix_c_source_is_20_2201() -> None:
    inputs = R5Inputs(
        fields=(),
        requires_appendix_c=True,
    )

    result = evaluate_r5(inputs)

    citations = {source.citation for source in result.sources}

    assert "10 CFR 20.2201" in citations


def test_r5_appendix_c_takes_precedence_over_confidence() -> None:
    """Missing regulatory data cannot be fixed by extraction confidence."""

    inputs = R5Inputs(
        fields=(make_field("radionuclide", 0.20),),
        requires_appendix_c=True,
    )

    result = evaluate_r5(inputs)

    assert result.outcome == RuleOutcome.INSUFFICIENT_DATA

    assert result.missing_fields == ("Appendix C to Part 20",)


# ---------------------------------------------------------------------------
# Confidence validation
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "confidence",
    [
        -0.01,
        1.01,
        -1.0,
        2.0,
    ],
)
def test_r5_rejects_invalid_confidence(
    confidence: float,
) -> None:
    with pytest.raises(ValueError):
        ExtractedFieldConfidence(
            field_name="annual_tede",
            confidence=confidence,
        )


# ---------------------------------------------------------------------------
# Result metadata
# ---------------------------------------------------------------------------
def test_r5_result_records_confidence_floor() -> None:
    inputs = R5Inputs(
        fields=(make_field("annual_tede", 0.90),),
    )

    result = evaluate_r5(inputs)

    assert result.threshold["confidence_floor"] == 0.60


def test_r5_records_inputs_used() -> None:
    inputs = R5Inputs(
        fields=(make_field("annual_tede", 0.90),),
    )

    result = evaluate_r5(inputs)

    assert result.inputs_used == inputs.model_dump()
