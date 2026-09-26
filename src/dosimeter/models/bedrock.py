"""Amazon Bedrock Converse helpers."""

from typing import Any

from dosimeter.tools.base import ToolDispatcher
from dosimeter.aws.aws import get_client
from dosimeter.aws.config import BEDROCK_MAX_TOKENS, BEDROCK_MODEL_ID
from dosimeter.prompts import SYSTEM_PROMPT
from dosimeter.tools.base import Tool


def converse(prompt: str) -> str:
    """Send a simple text-only request to the configured Bedrock model."""

    bedrock = get_client("bedrock-runtime")

    response = bedrock.converse(
        modelId=BEDROCK_MODEL_ID,
        system=[
            {
                "text": SYSTEM_PROMPT,
            }
        ],
        messages=[
            {
                "role": "user",
                "content": [{"text": prompt}],
            }
        ],
        inferenceConfig={
            "maxTokens": BEDROCK_MAX_TOKENS,
        },
    )

    return response["output"]["message"]["content"][0]["text"]


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

    bedrock = get_client("bedrock-runtime")

    messages: list[dict[str, Any]] = [
        {
            "role": "user",
            "content": [{"text": prompt}],
        }
    ]

    tool_config = bedrock_tool_config(tools)

    for _ in range(max_iterations):
        response = bedrock.converse(
            modelId=BEDROCK_MODEL_ID,
            system=[{"text": system_prompt}],
            messages=messages,
            toolConfig=tool_config,
            inferenceConfig={
                "maxTokens": BEDROCK_MAX_TOKENS,
            },
        )

        assistant_message = response["output"]["message"]
        messages.append(assistant_message)

        if response["stopReason"] != "tool_use":
            return _extract_text(assistant_message)

        tool_results: list[dict[str, Any]] = []

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

    raise RuntimeError(f"Bedrock tool loop exceeded {max_iterations} iterations")


def _extract_text(message: dict[str, Any]) -> str:
    """Collect text blocks from a Bedrock Converse message."""

    text_blocks = [block["text"] for block in message.get("content", []) if "text" in block]

    return "\n".join(text_blocks)
