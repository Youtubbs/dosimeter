"""
The groundedness judge.

A separate Converse call on the judge model, given one claim and the text of
the chunk it cited, returning a validated verdict. It is deliberately not the
reasoning model: a model grading its own work with a different prompt is not an
independent check.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from dosimeter.config.settings import Settings
from dosimeter.errors import ExternalServiceError
from dosimeter.logging_config import get_logger

_LOGGER = get_logger(__name__)

JUDGE_ROLE = "judge"

SYSTEM_PROMPT = (
    "You check whether a claim is supported by the text it cites. "
    "You are not deciding whether the claim is true, only whether this text "
    "supports it. Answer with JSON only: "
    '{"verdict": "supported" | "not_supported" | "partially_supported", '
    '"reason": "one sentence"}'
)


class Verdict(StrEnum):
    SUPPORTED = "supported"
    NOT_SUPPORTED = "not_supported"
    PARTIALLY_SUPPORTED = "partially_supported"


class JudgeVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    verdict: Verdict
    reason: str = Field(default="", max_length=500)


class JudgedClaim(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    claim: str = Field(min_length=1)
    chunk_id: str = Field(min_length=1)
    chunk_text: str = Field(min_length=1)
    verdict: Verdict
    reason: str = ""
    model_id: str
    input_tokens: int = 0
    output_tokens: int = 0


Converse = Callable[..., dict]


def _default_converse() -> Converse:
    from dosimeter.aws.aws import get_client

    return get_client("bedrock-runtime").converse


@dataclass
class GroundednessJudge:
    """One call per claim, on the pinned judge model."""

    settings: Settings
    converse: Converse | None = None

    def _client(self) -> Converse:
        return self.converse or _default_converse()

    def judge(self, claim: str, chunk_id: str, chunk_text: str) -> JudgedClaim:
        model_id = self.settings.model_for(JUDGE_ROLE)
        message = (
            f"Claim:\n{claim}\n\nCited text (chunk {chunk_id}):\n{chunk_text}\n\n"
            "Does the cited text support the claim?"
        )

        request = {
            "modelId": model_id,
            "system": [{"text": SYSTEM_PROMPT}],
            "messages": [{"role": "user", "content": [{"text": message}]}],
            "inferenceConfig": {
                "maxTokens": self.settings.bounds.tokens_for(JUDGE_ROLE),
                "temperature": 0,
            },
        }
        if self.settings.guardrail_id:
            request["guardrailConfig"] = {
                "guardrailIdentifier": self.settings.guardrail_id,
                "guardrailVersion": self.settings.guardrail_version,
            }

        response = self._client()(**request)
        verdict = _parse(response)
        usage = response.get("usage", {})

        _LOGGER.info(
            "judge.verdict",
            extra={"chunk_id": chunk_id, "verdict": verdict.verdict.value, "model_id": model_id},
        )

        return JudgedClaim(
            claim=claim,
            chunk_id=chunk_id,
            chunk_text=chunk_text,
            verdict=verdict.verdict,
            reason=verdict.reason,
            model_id=model_id,
            input_tokens=usage.get("inputTokens", 0),
            output_tokens=usage.get("outputTokens", 0),
        )


def _parse(response: dict) -> JudgeVerdict:
    """One retry is the caller's job; a shape we cannot read is a typed failure."""

    try:
        blocks = response["output"]["message"]["content"]
        text = "".join(block.get("text", "") for block in blocks).strip()
    except (KeyError, TypeError) as error:
        raise ExternalServiceError("the judge returned no content") from error

    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ExternalServiceError("the judge did not return JSON", detail=text[:200])

    try:
        return JudgeVerdict.model_validate(json.loads(text[start : end + 1]))
    except (json.JSONDecodeError, ValidationError) as error:
        raise ExternalServiceError("the judge verdict did not validate", detail=str(error)) from error
