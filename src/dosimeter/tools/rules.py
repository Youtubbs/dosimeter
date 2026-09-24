"""Tool adapter for the deterministic R1-R5 rules engine.

This module provides a single controlled entry point for worker-requested
rule evaluation. Regulatory thresholds remain exclusively inside the
deterministic rule implementations.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict
from dosimeter.graph.state import Subject
from dosimeter.tools.base import Tool

from dosimeter.domain.dose import (
    DoseUnit,
    IntakeMultipleOfALI,
    LensDoseEquivalent,
    ShallowDoseEquivalent,
    TotalEffectiveDoseEquivalent,
)
from dosimeter.domain.rules import RuleInvocation, RuleResult
from dosimeter.rules.r1_immediate import evaluate_r1
from dosimeter.rules.r2_twenty_four_hour import evaluate_r2
from dosimeter.rules.r3_written_report import R3Inputs, evaluate_r3
from dosimeter.rules.r4_planned_special_exposure import (
    PSEConditions,
    evaluate_r4,
)
from dosimeter.rules.r5_confidence import R5Inputs, evaluate_r5


RuleId = Literal["R1", "R2", "R3", "R4", "R5"]
EVALUATE_RULE = "evaluate_rule"


class EvaluateRuleRequest(BaseModel):
    """Validated request for a worker-initiated deterministic rule evaluation."""

    model_config = ConfigDict(
        strict=True,
        extra="forbid",
    )

    rule_id: RuleId
    inputs: dict[str, Any]


def _evaluate_r1(inputs: dict[str, Any]) -> RuleResult:
    """Validate and evaluate R1 inputs."""

    allowed = {"tede", "lens", "shallow", "intake"}
    _reject_unknown_inputs(inputs, allowed, "R1")

    return evaluate_r1(
        tede=_optional_model(
            inputs.get("tede"),
            TotalEffectiveDoseEquivalent,
        ),
        lens=_optional_model(
            inputs.get("lens"),
            LensDoseEquivalent,
        ),
        shallow=_optional_model(
            inputs.get("shallow"),
            ShallowDoseEquivalent,
        ),
        intake=_optional_model(
            inputs.get("intake"),
            IntakeMultipleOfALI,
        ),
    )


def _evaluate_r2(inputs: dict[str, Any]) -> RuleResult:
    """Validate and evaluate R2 inputs."""

    allowed = {
        "loss_of_control",
        "tede",
        "lens",
        "shallow",
        "intake",
    }
    _reject_unknown_inputs(inputs, allowed, "R2")

    loss_of_control = inputs.get("loss_of_control")

    if loss_of_control is not None and not isinstance(loss_of_control, bool):
        raise TypeError("R2 loss_of_control must be a bool or None.")

    return evaluate_r2(
        loss_of_control=loss_of_control,
        tede=_optional_model(
            inputs.get("tede"),
            TotalEffectiveDoseEquivalent,
        ),
        lens=_optional_model(
            inputs.get("lens"),
            LensDoseEquivalent,
        ),
        shallow=_optional_model(
            inputs.get("shallow"),
            ShallowDoseEquivalent,
        ),
        intake=_optional_model(
            inputs.get("intake"),
            IntakeMultipleOfALI,
        ),
    )


def _evaluate_r3(inputs: dict[str, Any]) -> RuleResult:
    """Validate and evaluate R3 inputs."""

    validated = R3Inputs.model_validate(inputs)
    return evaluate_r3(validated)


def _evaluate_r4(inputs: dict[str, Any]) -> RuleResult:
    """Validate and evaluate R4 inputs."""

    validated = PSEConditions.model_validate(inputs)
    return evaluate_r4(validated)


def _evaluate_r5(inputs: dict[str, Any]) -> RuleResult:
    """Validate and evaluate R5 inputs."""

    confidence_floor = inputs.get("confidence_floor")

    rule_inputs = {key: value for key, value in inputs.items() if key != "confidence_floor"}

    validated = R5Inputs.model_validate(rule_inputs)

    if confidence_floor is None:
        return evaluate_r5(validated)

    if not isinstance(confidence_floor, (int, float)):
        raise TypeError("R5 confidence_floor must be numeric.")

    return evaluate_r5(
        validated,
        confidence_floor=float(confidence_floor),
    )


def _optional_model(
    value: Any,
    model_type: type[BaseModel],
) -> Any:
    """Convert external tool input into a typed dose model."""

    if value is None:
        return None

    if isinstance(value, model_type):
        return value

    if not isinstance(value, dict):
        raise TypeError(f"Expected {model_type.__name__} or a mapping.")

    data = dict(value)

    if "unit" in data and isinstance(data["unit"], str):
        data["unit"] = DoseUnit(data["unit"])

    return model_type.model_validate(data)


def _reject_unknown_inputs(
    inputs: dict[str, Any],
    allowed: set[str],
    rule_id: str,
) -> None:
    """Reject fields that are not accepted by a deterministic rule."""

    unknown = set(inputs) - allowed

    if unknown:
        fields = ", ".join(sorted(unknown))
        raise ValueError(f"{rule_id} received unsupported input field(s): {fields}")


def evaluate_rule(
    request: EvaluateRuleRequest | dict[str, Any],
) -> RuleInvocation:
    """Evaluate one deterministic rule through the worker tool path.

    The returned RuleInvocation records that this evaluation originated
    through the model-callable tool path.

    No regulatory thresholds are implemented in this adapter.
    """

    if not isinstance(request, EvaluateRuleRequest):
        request = EvaluateRuleRequest.model_validate(request)

    evaluators = {
        "R1": _evaluate_r1,
        "R2": _evaluate_r2,
        "R3": _evaluate_r3,
        "R4": _evaluate_r4,
        "R5": _evaluate_r5,
    }

    result = evaluators[request.rule_id](request.inputs)

    return RuleInvocation(
        rule_id=request.rule_id,
        path="tool",
        inputs=request.inputs,
        result=result,
    )


def _handle_evaluate_rule(
    subject: Subject,
    arguments: EvaluateRuleRequest,
) -> BaseModel:
    """Run a deterministic rule evaluation through the tool path."""

    # The dispatcher owns the subject. Rule evaluation operates only on
    # the validated regulatory inputs supplied to this tool.
    del subject

    return evaluate_rule(arguments)


EVALUATE_RULE_TOOL = Tool(
    name=EVALUATE_RULE,
    description=(
        "Evaluate one deterministic regulatory rule (R1-R5) using "
        "validated inputs. Regulatory thresholds remain inside the "
        "rules engine; this tool does not invent or override thresholds."
    ),
    input_model=EvaluateRuleRequest,
    output_model=RuleInvocation,
    handler=_handle_evaluate_rule,
)


def rule_tools() -> list[Tool]:
    """Return deterministic rule tools for registration."""

    return [EVALUATE_RULE_TOOL]


__all__ = [
    "EVALUATE_RULE",
    "EVALUATE_RULE_TOOL",
    "EvaluateRuleRequest",
    "evaluate_rule",
    "rule_tools",
]
