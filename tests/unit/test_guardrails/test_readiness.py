"""Tests for the deterministic readiness gate."""

from dosimeter.guardrails.readiness import (
    ReadinessInput,
    RequestKind,
    evaluate_readiness,
)


def test_ready_assessment_may_dispatch_workers() -> None:
    decision = evaluate_readiness(
        ReadinessInput(
            request_kind=RequestKind.ASSESS,
            normalized_record_present=True,
        )
    )

    assert decision.may_dispatch_workers is True
    assert decision.human_determination_required is False
    assert decision.refused is False


def test_low_confidence_assessment_stops_before_dispatch() -> None:
    decision = evaluate_readiness(
        ReadinessInput(
            request_kind=RequestKind.ASSESS,
            normalized_record_present=True,
            low_confidence_fields=("tede",),
        )
    )

    assert decision.may_dispatch_workers is False
    assert decision.human_determination_required is True
    assert "tede" in decision.reasons[0]


def test_missing_required_field_stops_assessment() -> None:
    decision = evaluate_readiness(
        ReadinessInput(
            request_kind=RequestKind.ASSESS,
            normalized_record_present=True,
            missing_required_fields=("lens",),
        )
    )

    assert decision.may_dispatch_workers is False
    assert decision.human_determination_required is True


def test_missing_normalized_record_stops_assessment() -> None:
    decision = evaluate_readiness(
        ReadinessInput(
            request_kind=RequestKind.ASSESS,
            normalized_record_present=False,
        )
    )

    assert decision.may_dispatch_workers is False
    assert decision.human_determination_required is True


def test_policy_question_uses_retrieval_without_worker_dispatch() -> None:
    decision = evaluate_readiness(
        ReadinessInput(
            request_kind=RequestKind.POLICY_QUESTION,
            normalized_record_present=False,
        )
    )

    assert decision.may_dispatch_workers is False
    assert decision.may_answer_from_retrieval is True
    assert decision.refused is False


def test_action_is_refused() -> None:
    decision = evaluate_readiness(
        ReadinessInput(
            request_kind=RequestKind.ACTION,
            normalized_record_present=True,
        )
    )

    assert decision.may_dispatch_workers is False
    assert decision.refused is True


def test_out_of_scope_is_refused() -> None:
    decision = evaluate_readiness(
        ReadinessInput(
            request_kind=RequestKind.OUT_OF_SCOPE,
            normalized_record_present=True,
        )
    )

    assert decision.may_dispatch_workers is False
    assert decision.refused is True


def test_deterministic_gate_never_promotes_policy_question_to_assess() -> None:
    decision = evaluate_readiness(
        ReadinessInput(
            request_kind=RequestKind.POLICY_QUESTION,
            normalized_record_present=True,
        )
    )

    assert decision.request_kind == RequestKind.POLICY_QUESTION
    assert decision.may_dispatch_workers is False
