"""Tests for Bedrock tool schema conversion."""

import pytest

from pydantic import BaseModel, ConfigDict
from unittest.mock import Mock, patch

from dosimeter.config.settings import Bounds
from dosimeter.errors import BudgetError
from dosimeter.graph.schemas import Subject
from dosimeter.harness.budgets import SessionLedger
from dosimeter.models.bedrock import bedrock_tool_config, bedrock_tool_spec, run_tool_loop
from dosimeter.tools.dispatcher import Tool, ToolDispatcher, build_registry


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


class FakeRecorder:
    """Keeps what RunRecorder would have written for the tool and model calls."""

    def __init__(self) -> None:
        self.model_calls: list[dict] = []
        self.tool_calls: list[dict] = []

    def model_called(self, **call) -> None:
        self.model_calls.append(call)

    def tool_called(self, tool_name, arguments, result, outcome, **extra) -> None:
        self.tool_calls.append({"tool": tool_name, "outcome": outcome, **extra})


def converse_response(stop_reason: str, content: list[dict], input_tokens: int, output_tokens: int):
    return {
        "stopReason": stop_reason,
        "output": {"message": {"role": "assistant", "content": content}},
        "usage": {"inputTokens": input_tokens, "outputTokens": output_tokens},
    }


TOOL_USE = [{"toolUse": {"toolUseId": "tool-1", "name": "example_tool", "input": {"query": "q"}}}]


def notification_dispatcher(ledger: SessionLedger, recorder: FakeRecorder) -> ToolDispatcher:
    return ToolDispatcher(
        registry=build_registry([EXAMPLE_TOOL]),
        ledger=ledger,
        subject=Subject(
            session_id="session-1",
            officer_id=1,
            officer_code="OFF-101",
            exposure_id="EXP-2026-0412",
        ),
        recorder=recorder,
        agent="notification",
    )


def test_run_tool_loop_counts_and_records_every_model_call() -> None:
    bedrock = Mock()
    bedrock.converse.side_effect = [
        converse_response("tool_use", TOOL_USE, input_tokens=100, output_tokens=20),
        converse_response("end_turn", [{"text": "done"}], input_tokens=50, output_tokens=10),
    ]
    ledger = SessionLedger(bounds=Bounds())
    recorder = FakeRecorder()

    with patch("dosimeter.models.bedrock.get_client", return_value=bedrock):
        run_tool_loop(
            prompt="Evaluate.",
            system_prompt="Test worker.",
            tools=[EXAMPLE_TOOL],
            dispatcher=notification_dispatcher(ledger, recorder),
        )

    assert ledger.session_tokens == 180
    assert [(call["agent"], call["input_tokens"], call["output_tokens"]) for call in recorder.model_calls] == [
        ("notification", 100, 20),
        ("notification", 50, 10),
    ]
    assert recorder.tool_calls[0]["worker"] == "notification"

    # the per-call limit is the worker's own, from typed config
    first_call = bedrock.converse.call_args_list[0].kwargs
    assert first_call["inferenceConfig"]["maxTokens"] == Bounds().tokens_for("notification")


def test_run_tool_loop_refuses_the_next_call_once_the_budget_is_spent() -> None:
    bedrock = Mock()
    bedrock.converse.return_value = converse_response(
        "tool_use", TOOL_USE, input_tokens=80, output_tokens=30
    )
    ledger = SessionLedger(bounds=Bounds(max_session_tokens=100))

    with (
        patch("dosimeter.models.bedrock.get_client", return_value=bedrock),
        pytest.raises(BudgetError) as caught,
    ):
        run_tool_loop(
            prompt="Evaluate.",
            system_prompt="Test worker.",
            tools=[EXAMPLE_TOOL],
            dispatcher=notification_dispatcher(ledger, FakeRecorder()),
        )

    assert caught.value.context["ceiling"] == "max_session_tokens"
    assert bedrock.converse.call_count == 1
