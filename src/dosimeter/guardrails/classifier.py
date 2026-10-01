"""Bedrock-backed request classification for the readiness gate."""

import time

from pydantic import BaseModel, ConfigDict

from dosimeter.guardrails.bedrock import (
    BedrockGuardrailOutcome,
    apply_guardrail,
)
from dosimeter.guardrails.readiness import RequestKind
from dosimeter.harness.budgets import SessionLedger
from dosimeter.harness.run_record import RunRecorder
from dosimeter.models.bedrock import FAST_ROLE, check_budget, get_chat_model, record_usage
from dosimeter.redaction import redact

READINESS_AGENT = "readiness_gate"


CLASSIFIER_SYSTEM_PROMPT = """
Classify the officer's request into exactly one category:

policy_question:
The officer is asking for regulatory or policy information. This may be
answered from retrieval and must not dispatch assessment workers.

assess:
The officer is asking the system to assess or evaluate an exposure record.

action:
The officer is asking the system to perform an external or regulatory action,
such as notifying someone, submitting a report, approving something, or
changing an official record. The system must refuse these requests.

out_of_scope:
The request is unrelated to the dosimeter radiation-exposure reporting system.

Return only one of these exact values:
policy_question
assess
action
out_of_scope
""".strip()


class ClassificationResult(BaseModel):
    """Validated readiness-gate classification."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    request_kind: RequestKind


def classify_request(
    text: str,
    *,
    ledger: SessionLedger | None = None,
    recorder: RunRecorder | None = None,
) -> ClassificationResult:
    """Guard and classify an officer request."""

    guardrail_result = apply_guardrail(
        text,
        source="officer_input",
    )

    if guardrail_result.outcome == BedrockGuardrailOutcome.INTERVENED:
        return ClassificationResult(
            request_kind=RequestKind.OUT_OF_SCOPE,
        )

    check_budget(ledger, READINESS_AGENT)

    # one label is all this call may return
    model = get_chat_model(
        temperature=0.0,
        max_tokens=20,
    )

    started = time.perf_counter()
    response = model.invoke(
        [
            ("system", CLASSIFIER_SYSTEM_PROMPT),
            ("user", redact(text)),
        ]
    )

    usage = getattr(response, "usage_metadata", None) or {}
    record_usage(
        ledger=ledger,
        recorder=recorder,
        agent=READINESS_AGENT,
        role=FAST_ROLE,
        input_tokens=usage.get("input_tokens", 0),
        output_tokens=usage.get("output_tokens", 0),
        started=started,
    )

    raw_label = _response_text(response.content)

    try:
        request_kind = RequestKind(raw_label.strip().lower())
    except ValueError:
        request_kind = RequestKind.OUT_OF_SCOPE

    return ClassificationResult(request_kind=request_kind)


def _response_text(content: object) -> str:
    """Extract text from a LangChain Bedrock response."""

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts: list[str] = []

        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)

        return "\n".join(parts)

    return ""
