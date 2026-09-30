"""Tests for guardrail signals reaching graph eligibility."""

from dosimeter.graph.nodes.eligibility import (
    eligibility_node,
    signals_from_state,
)
from dosimeter.guardrails.events import (
    GuardrailRemedy,
    create_guardrail_event,
)
from dosimeter.harness.escalation import Trigger


def prompt_attack_event():
    return create_guardrail_event(
        correlation_id="test-correlation-id",
        trigger="prompt_attack_filter_fired",
        remedy=GuardrailRemedy.BLOCK_AND_ESCALATE,
        source="artifact:P3/crew-note.txt",
        detail="Bedrock Prompt Attack filter intervened.",
    )


def test_prompt_attack_event_becomes_escalation_signal():
    state = {
        "reviewer_verdicts": [],
        "reviewer_iterations": 0,
        "guardrail_events": [prompt_attack_event()],
    }

    signals = signals_from_state(state)

    assert signals.prompt_attack_fired is True


def test_non_prompt_guardrail_event_does_not_set_prompt_attack():
    event = create_guardrail_event(
        correlation_id="test-correlation-id",
        trigger="pii_detected",
        remedy=GuardrailRemedy.REDACT,
        source="artifact:P3/report.pdf",
        detail="PII was detected and redacted.",
    )

    state = {
        "reviewer_verdicts": [],
        "reviewer_iterations": 0,
        "guardrail_events": [event],
    }

    signals = signals_from_state(state)

    assert signals.prompt_attack_fired is False


def test_prompt_attack_causes_escalated_outcome():
    state = {
        "reviewer_verdicts": [],
        "reviewer_iterations": 0,
        "guardrail_events": [prompt_attack_event()],
    }

    result = eligibility_node(state)

    assert result["outcome"] == "escalated"
    assert result["escalation"].escalates is True
    assert Trigger.PROMPT_ATTACK_FIRED.value in result["escalation"].names()
