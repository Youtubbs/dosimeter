"""Tests for Bedrock tool schema conversion."""

import pytest

from pydantic import BaseModel, ConfigDict
from unittest.mock import Mock, patch

from dosimeter.graph.state import Subject
from dosimeter.models.bedrock import bedrock_tool_config, bedrock_tool_spec, run_tool_loop
from dosimeter.tools.base import Tool


class ExampleInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str


class ExampleOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    result: str


def example_handler(
    subject: Subject,
    arguments: BaseModel,
) -> BaseModel:
    del subject
    del arguments

    return ExampleOutput(result="ok")


EXAMPLE_TOOL = Tool(
    name="example_tool",
    description="An example tool.",
    input_model=ExampleInput,
    output_model=ExampleOutput,
    handler=example_handler,
)


def test_bedrock_tool_spec_uses_tool_contract() -> None:
    spec = bedrock_tool_spec(EXAMPLE_TOOL)

    assert spec["toolSpec"]["name"] == "example_tool"
    assert spec["toolSpec"]["description"] == "An example tool."

    schema = spec["toolSpec"]["inputSchema"]["json"]

    assert "query" in schema["properties"]
    assert schema["required"] == ["query"]


def test_bedrock_tool_config_contains_tools() -> None:
    config = bedrock_tool_config([EXAMPLE_TOOL])

    assert len(config["tools"]) == 1
    assert config["tools"][0]["toolSpec"]["name"] == "example_tool"


def test_bedrock_tool_config_supports_multiple_tools() -> None:
    second_tool = Tool(
        name="second_tool",
        description="Another example tool.",
        input_model=ExampleInput,
        output_model=ExampleOutput,
        handler=example_handler,
    )

    config = bedrock_tool_config(
        [
            EXAMPLE_TOOL,
            second_tool,
        ]
    )

    names = {entry["toolSpec"]["name"] for entry in config["tools"]}

    assert names == {
        "example_tool",
        "second_tool",
    }


def test_run_tool_loop_returns_final_text() -> None:
    bedrock = Mock()

    bedrock.converse.return_value = {
        "stopReason": "end_turn",
        "output": {
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "text": "Final answer.",
                    }
                ],
            }
        },
    }

    dispatcher = Mock()

    with patch(
        "dosimeter.models.bedrock.get_client",
        return_value=bedrock,
    ):
        result = run_tool_loop(
            prompt="Evaluate this exposure.",
            system_prompt="You are a test worker.",
            tools=[EXAMPLE_TOOL],
            dispatcher=dispatcher,
        )

    assert result == "Final answer."
    dispatcher.invoke.assert_not_called()


def test_run_tool_loop_executes_requested_tool() -> None:
    bedrock = Mock()

    bedrock.converse.side_effect = [
        {
            "stopReason": "tool_use",
            "output": {
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "toolUse": {
                                "toolUseId": "tool-123",
                                "name": "example_tool",
                                "input": {
                                    "query": "exposure",
                                },
                            }
                        }
                    ],
                }
            },
        },
        {
            "stopReason": "end_turn",
            "output": {
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "text": "Evaluation complete.",
                        }
                    ],
                }
            },
        },
    ]

    dispatcher = Mock()

    dispatcher.invoke.return_value = Mock(
        ok=True,
        model_dump=Mock(
            return_value={
                "tool": "example_tool",
                "ok": True,
                "value": {
                    "result": "ok",
                },
            }
        ),
    )

    with patch(
        "dosimeter.models.bedrock.get_client",
        return_value=bedrock,
    ):
        result = run_tool_loop(
            prompt="Evaluate this exposure.",
            system_prompt="You are a test worker.",
            tools=[EXAMPLE_TOOL],
            dispatcher=dispatcher,
        )

    assert result == "Evaluation complete."

    dispatcher.invoke.assert_called_once_with(
        "example_tool",
        {
            "query": "exposure",
        },
    )

    assert bedrock.converse.call_count == 2


def test_run_tool_loop_stops_at_iteration_limit() -> None:
    bedrock = Mock()

    bedrock.converse.return_value = {
        "stopReason": "tool_use",
        "output": {
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "toolUse": {
                            "toolUseId": "tool-loop",
                            "name": "example_tool",
                            "input": {
                                "query": "again",
                            },
                        }
                    }
                ],
            }
        },
    }

    dispatcher = Mock()

    dispatcher.invoke.return_value = Mock(
        ok=True,
        model_dump=Mock(
            return_value={
                "tool": "example_tool",
                "ok": True,
                "value": {
                    "result": "ok",
                },
            }
        ),
    )

    with (
        patch(
            "dosimeter.models.bedrock.get_client",
            return_value=bedrock,
        ),
        pytest.raises(
            RuntimeError,
            match="exceeded 2 iterations",
        ),
    ):
        run_tool_loop(
            prompt="Evaluate.",
            system_prompt="Test worker.",
            tools=[EXAMPLE_TOOL],
            dispatcher=dispatcher,
            max_iterations=2,
        )

    assert bedrock.converse.call_count == 2
