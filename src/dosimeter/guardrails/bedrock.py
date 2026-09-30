"""Amazon Bedrock Guardrails integration.

This module applies the configured Guardrail to text before the
text can continue through the Dosimeter workflow.
"""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from dosimeter.aws.aws import get_client
from dosimeter.config.settings import get_settings


class BedrockGuardrailOutcome(StrEnum):
    ALLOWED = "allowed"
    INTERVENED = "intervened"


class BedrockGuardrailResult(BaseModel):
    """Result of applying the Bedrock Guardrail to one piece of text."""

    model_config = ConfigDict(
        strict=True,
        frozen=True,
        extra="forbid",
    )

    outcome: BedrockGuardrailOutcome
    text: str
    source: str = Field(min_length=1)
    prompt_attack_fired: bool = False
    action: str | None = None


def apply_guardrail(
    text: str,
    *,
    source: str,
) -> BedrockGuardrailResult:
    """Apply the configured Bedrock Guardrail to one text value."""

    if not text.strip():
        return BedrockGuardrailResult(
            outcome=BedrockGuardrailOutcome.ALLOWED,
            text=text,
            source=source,
        )

    settings = get_settings()

    client = get_client("bedrock-runtime")

    response: dict[str, Any] = client.apply_guardrail(
        guardrailIdentifier=settings.guardrail_id,
        guardrailVersion=settings.guardrail_version,
        source="INPUT",
        content=[
            {
                "text": {
                    "text": text,
                }
            }
        ],
    )

    action = response.get("action", "NONE")

    if action == "GUARDRAIL_INTERVENED":
        return BedrockGuardrailResult(
            outcome=BedrockGuardrailOutcome.INTERVENED,
            text=text,
            source=source,
            prompt_attack_fired=_prompt_attack_detected(response),
            action=action,
        )

    return BedrockGuardrailResult(
        outcome=BedrockGuardrailOutcome.ALLOWED,
        text=text,
        source=source,
        prompt_attack_fired=False,
        action=action,
    )


def _prompt_attack_detected(response: dict[str, Any]) -> bool:
    """Return True when the Guardrail assessment identifies a prompt attack."""

    for assessment in response.get("assessments", []):
        content_policy = assessment.get("contentPolicy", {})

        for filter_result in content_policy.get("filters", []):
            filter_type = str(filter_result.get("type", "")).upper()
            action = str(filter_result.get("action", "")).upper()

            if filter_type == "PROMPT_ATTACK" and action in {
                "BLOCKED",
                "GUARDRAIL_INTERVENED",
            }:
                return True

    return False
