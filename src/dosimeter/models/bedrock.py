"""invoking our bedrock modal"""

import time
from functools import lru_cache
from typing import Any

from langchain_aws import BedrockEmbeddings, ChatBedrockConverse
from langchain_core.language_models import BaseChatModel

from ..aws.aws import client_config, get_client
from ..config.settings import get_settings
from ..harness.budgets import SessionLedger
from ..harness.run_record import RunRecorder
from ..prompts import SYSTEM_PROMPT
from ..redaction import redact
from ..tools.dispatcher import Tool, ToolDispatcher

# the role each model call is recorded under; settings say which model serves it
REASONING_ROLE = "reasoning"
FAST_ROLE = "fast"


def converse(
    prompt: str,
    *,
    ledger: SessionLedger | None = None,
    recorder: RunRecorder | None = None,
    agent: str | None = None,
) -> str:
    """calling our bedrock modal"""

    settings = get_settings()
    bedrock = get_client("bedrock-runtime")

    check_budget(ledger, agent)

    started = time.perf_counter()
    response = bedrock.converse(
        modelId=settings.bedrock_model_id,
        system=[
            {
                "text": SYSTEM_PROMPT,
            }
        ],
        messages=[
            {
                "role": "user",
                # names and dose histories come out before anything reaches the model
                "content": [{"text": redact(prompt)}],
            }
        ],
        inferenceConfig={
            "maxTokens": max_tokens_for(ledger, agent),
        },
    )

    record_usage(
        ledger=ledger,
        recorder=recorder,
        agent=agent,
        role=REASONING_ROLE,
        started=started,
        **usage_of(response),
    )

    return response["output"]["message"]["content"][0]["text"]


@lru_cache(maxsize=1)
def _embeddings() -> BedrockEmbeddings:
    settings = get_settings()
    return BedrockEmbeddings(
        model_id=settings.bedrock_embed_model_id,
        region_name=settings.aws_region,
        credentials_profile_name=settings.aws_profile,
        config=client_config(),
    )


def embed_text(text: str) -> list[float]:
    """The same embedding model the Knowledge Base uses, for the similar-exposure search."""

    return _embeddings().embed_query(text)


def get_chat_model(*, temperature: float = 0.0, max_tokens: int | None = None) -> BaseChatModel:
    """Return a configured bedrock chat model - could be swapped out for any BaseChatModel"""

    settings = get_settings()

    return ChatBedrockConverse(
        model=settings.bedrock_model_id,
        region_name=settings.aws_region,
        credentials_profile_name=settings.aws_profile,
        temperature=temperature,
        max_tokens=max_tokens or settings.bounds.default_max_tokens_per_call,
        config=client_config(),
        # content filters on every model call
        guardrail_config={
            "guardrailIdentifier": settings.guardrail_id,
            "guardrailVersion": settings.guardrail_version,
        },
    )


def usage_of(response: dict[str, Any]) -> dict[str, int]:
    """retrieving the token usage of a Converse response"""

    usage = response.get("usage", {})

    return {
        "input_tokens": usage.get("inputTokens", 0),
        "output_tokens": usage.get("outputTokens", 0),
    }


def check_budget(ledger: SessionLedger | None, agent: str | None) -> None:
    """Refuse to start the next model call once any budget is spent."""

    if ledger is not None:
        ledger.require(agent=agent)


def max_tokens_for(ledger: SessionLedger | None, agent: str | None) -> int:
    """
    The per-call token limit every model call asks for: the agent's limit from
    config, and never more than the session has left.
    """

    if ledger is not None:
        return ledger.tokens_left_for(agent)

    return get_settings().bounds.tokens_for(agent)


def record_usage(
    *,
    ledger: SessionLedger | None,
    recorder: RunRecorder | None,
    agent: str | None,
    role: str,
    input_tokens: int,
    output_tokens: int,
    started: float,
) -> None:
    """Add one model call to the session budget and to the turn's run record."""

    if ledger is not None:
        ledger.record_model_call(input_tokens, output_tokens)

    if recorder is not None:
        recorder.model_called(
            model_id=get_settings().model_for(role),
            role=role,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            agent=agent,
            duration_ms=round((time.perf_counter() - started) * 1000, 3),
        )


def bedrock_tool_spec(tool: Tool) -> dict[str, Any]:
    """Convert a Dosimeter Tool into a Bedrock Converse tool specification."""

    return {
        "toolSpec": {
            "name": tool.name,
            "description": tool.description,
            "inputSchema": {
                "json": tool.input_schema(),
            },
        }
    }


def bedrock_tool_config(tools: list[Tool]) -> dict[str, Any]:
    """Build a Bedrock Converse toolConfig from Dosimeter tools."""

    return {"tools": [bedrock_tool_spec(tool) for tool in tools]}


def run_tool_loop(
    *,
    prompt: str,
    system_prompt: str,
    tools: list[Tool],
    dispatcher: ToolDispatcher,
    max_iterations: int = 10,
) -> str:
    """Run a Bedrock Converse loop until the model returns a final response."""

    settings = get_settings()
    bedrock = get_client("bedrock-runtime")
    ledger = dispatcher.ledger
    agent = dispatcher.agent

    messages: list[dict[str, Any]] = [
        {
            "role": "user",
            # names and dose histories come out before anything reaches the model
            "content": [{"text": redact(prompt)}],
        }
    ]

    tool_config = bedrock_tool_config(tools)

    # the model's stop reason ends the loop; max_iterations is the hard cap
    for _ in range(max_iterations):
        check_budget(ledger, agent)

        started = time.perf_counter()
        response = bedrock.converse(
            modelId=settings.bedrock_model_id,
            system=[{"text": system_prompt}],
            messages=messages,
            toolConfig=tool_config,
            inferenceConfig={
                "maxTokens": max_tokens_for(ledger, agent),
            },
        )

        record_usage(
            ledger=ledger,
            recorder=dispatcher.recorder,
            agent=agent,
            role=REASONING_ROLE,
            started=started,
            **usage_of(response),
        )

        assistant_message = response["output"]["message"]
        messages.append(assistant_message)

        if response["stopReason"] != "tool_use":
            return _extract_text(assistant_message)

        tool_results: list[dict[str, Any]] = []
        proposed: list[tuple[str, bool]] = []

        for block in assistant_message["content"]:
            tool_use = block.get("toolUse")

            if tool_use is None:
                continue

            tool_use_id = tool_use["toolUseId"]
            tool_name = tool_use["name"]
            arguments = tool_use.get("input", {})

            result = dispatcher.invoke(
                tool_name,
                arguments,
            )
            proposed.append((tool_name, result.ok))

            result_payload = result.model_dump(
                mode="json",
                exclude_none=True,
            )

            tool_results.append(
                {
                    "toolResult": {
                        "toolUseId": tool_use_id,
                        "content": [
                            {
                                "json": result_payload,
                            }
                        ],
                        "status": "success" if result.ok else "error",
                    }
                }
            )

        if not tool_results:
            raise RuntimeError("Bedrock returned tool_use without a toolUse block")

        messages.append(
            {
                "role": "user",
                "content": tool_results,
            }
        )

        # a worker is done once its proposal is accepted
        if any(name.startswith("propose_") and ok for name, ok in proposed):
            return ""

    raise RuntimeError(f"Bedrock tool loop exceeded {max_iterations} iterations")


def _extract_text(message: dict[str, Any]) -> str:
    """Collect text blocks from a Bedrock Converse message."""

    text_blocks = [block["text"] for block in message.get("content", []) if "text" in block]

    return "\n".join(text_blocks)
