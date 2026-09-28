"""
The groundedness judge. One separate model call per claim, given the claim and
the text it cited, returning a validated verdict.
"""

import logging
from enum import StrEnum

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict, Field

from dosimeter.config.settings import Settings
from dosimeter.errors import ExternalServiceError
from dosimeter.models.bedrock import get_chat_model
from dosimeter.prompts import JUDGE_PROMPT
from dosimeter.redaction import redact

logger = logging.getLogger(__name__)

# the run record names the role; settings say which model serves it
JUDGE_ROLE = "judge"


class Verdict(StrEnum):
    SUPPORTED = "supported"
    NOT_SUPPORTED = "not_supported"
    PARTIALLY_SUPPORTED = "partially_supported"


# the first line of the class docstring is the model's instructions
class JudgeVerdict(BaseModel):
    """Whether the cited text supports the claim. Judge only from the cited text."""

    verdict: Verdict = Field(
        description="supported, not_supported or partially_supported"
    )
    reason: str = Field(
        default="",
        max_length=500,
        description="One sentence on why.",
    )


class JudgedClaim(BaseModel):
    """One claim, the text it cited, and the verdict."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    claim: str = Field(min_length=1)
    chunk_id: str = Field(min_length=1)
    chunk_text: str = Field(min_length=1)
    verdict: Verdict
    reason: str = ""
    model_id: str
    input_tokens: int = 0
    output_tokens: int = 0


def judge_claim(
    claim: str,
    chunk_id: str,
    chunk_text: str,
    settings: Settings,
    model: BaseChatModel | None = None,
) -> JudgedClaim:
    """Ask whether the cited text supports the claim. A verdict that does not validate is a typed failure."""

    chat_model = model or get_chat_model(max_tokens=settings.bounds.tokens_for(JUDGE_ROLE))

    # include_raw keeps the token usage next to the parsed verdict
    structured = chat_model.with_structured_output(JudgeVerdict, include_raw=True)

    message = (
        f"Claim:\n{claim}\n\nCited text ({chunk_id}):\n{chunk_text}\n\n"
        "Does the cited text support the claim?"
    )
    result = structured.invoke([SystemMessage(JUDGE_PROMPT), HumanMessage(redact(message))])

    verdict = result.get("parsed")
    if verdict is None:
        raise ExternalServiceError(
            "the judge verdict did not validate",
            detail=str(result.get("parsing_error")),
        )

    model_id = settings.model_for(JUDGE_ROLE)
    usage = getattr(result.get("raw"), "usage_metadata", None) or {}

    logger.info(
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
        input_tokens=usage.get("input_tokens", 0),
        output_tokens=usage.get("output_tokens", 0),
    )
