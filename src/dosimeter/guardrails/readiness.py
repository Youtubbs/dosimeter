"""Readiness gate for officer requests and exposure assessments."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

STRICT = ConfigDict(strict=True, frozen=True, extra="forbid")


class RequestKind(StrEnum):
    """Classification labels required by the readiness gate."""

    POLICY_QUESTION = "policy_question"
    ASSESS = "assess"
    ACTION = "action"
    OUT_OF_SCOPE = "out_of_scope"


class ReadinessInput(BaseModel):
    """Deterministic facts available after request classification."""

    model_config = STRICT

    request_kind: RequestKind
    normalized_record_present: bool
    missing_required_fields: tuple[str, ...] = ()
    low_confidence_fields: tuple[str, ...] = ()


class ReadinessDecision(BaseModel):
    """Final deterministic decision produced by the readiness gate."""

    model_config = STRICT

    request_kind: RequestKind
    may_dispatch_workers: bool
    may_answer_from_retrieval: bool
    refused: bool
    human_determination_required: bool
    reasons: tuple[str, ...] = ()


def evaluate_readiness(inputs: ReadinessInput) -> ReadinessDecision:
    """
    Apply deterministic readiness checks after classification.

    The deterministic check may stop an assessment but must never convert
    another request kind into an assessment.
    """

    if inputs.request_kind == RequestKind.ACTION:
        return ReadinessDecision(
            request_kind=inputs.request_kind,
            may_dispatch_workers=False,
            may_answer_from_retrieval=False,
            refused=True,
            human_determination_required=False,
            reasons=(
                "Action requests are refused; this system does not notify or take regulatory action.",
            ),
        )

    if inputs.request_kind == RequestKind.OUT_OF_SCOPE:
        return ReadinessDecision(
            request_kind=inputs.request_kind,
            may_dispatch_workers=False,
            may_answer_from_retrieval=False,
            refused=True,
            human_determination_required=False,
            reasons=(
                "The request is outside the system scope and requires escalation.",
            ),
        )

    if inputs.request_kind == RequestKind.POLICY_QUESTION:
        return ReadinessDecision(
            request_kind=inputs.request_kind,
            may_dispatch_workers=False,
            may_answer_from_retrieval=True,
            refused=False,
            human_determination_required=False,
        )

    reasons: list[str] = []

    if not inputs.normalized_record_present:
        reasons.append("No normalized exposure record is available.")

    if inputs.missing_required_fields:
        reasons.append(
            "Required fields are missing: "
            + ", ".join(inputs.missing_required_fields)
            + "."
        )

    if inputs.low_confidence_fields:
        reasons.append(
            "Fields below the confidence floor require human determination: "
            + ", ".join(inputs.low_confidence_fields)
            + "."
        )

    if reasons:
        return ReadinessDecision(
            request_kind=inputs.request_kind,
            may_dispatch_workers=False,
            may_answer_from_retrieval=False,
            refused=False,
            human_determination_required=True,
            reasons=tuple(reasons),
        )

    return ReadinessDecision(
        request_kind=inputs.request_kind,
        may_dispatch_workers=True,
        may_answer_from_retrieval=False,
        refused=False,
        human_determination_required=False,
    )
