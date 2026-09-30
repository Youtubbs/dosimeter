"""Tests for structured guardrail events."""

from dosimeter.guardrails.events import (
    GuardrailRemedy,
    create_guardrail_event,
)


def test_guardrail_event_contains_required_fields():
    event = create_guardrail_event(
        correlation_id="corr-123",
        trigger="prompt_attack_filter_fired",
        remedy=GuardrailRemedy.BLOCK_AND_ESCALATE,
        source="artifact:P3/crew-note.txt",
        detail="Prompt attack detected.",
    )

    assert event.correlation_id == "corr-123"
    assert event.trigger == "prompt_attack_filter_fired"
    assert event.remedy == GuardrailRemedy.BLOCK_AND_ESCALATE
    assert event.source == "artifact:P3/crew-note.txt"
    assert event.detail == "Prompt attack detected."


def test_guardrail_event_generates_correlation_id():
    event = create_guardrail_event(
        trigger="pii_detected",
        remedy=GuardrailRemedy.REDACT,
        source="officer_input",
        detail="PII detected.",
    )

    assert event.correlation_id
