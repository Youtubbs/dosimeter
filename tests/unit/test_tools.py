"""The tool contract: no subject in a schema, stable keys, structured errors."""

from __future__ import annotations
from enum import Enum

import pytest
from pydantic import BaseModel, ConfigDict, Field

from dosimeter.api.schemas import FindSimilarExposuresInput, SimilarExposures
from dosimeter.config.settings import Bounds
from dosimeter.errors import DosimeterError, RetrievalError
from dosimeter.graph.state import Subject
from dosimeter.harness.budgets import SessionLedger
from dosimeter.tools.api_clients import ApiToolset
from dosimeter.tools.base import Tool, ToolDispatcher, ToolError, ToolErrorCode, ToolRegistry
from dosimeter.tools.idempotency import (
    arguments_hash,
    canonicalize,
    idempotency_key,
    normalize_unit,
)
from dosimeter.tools.transport import TransportResponse

SUBJECT = Subject(
    session_id="session-1",
    officer_id=1,
    officer_code="OFF-101",
    exposure_id="EXP-2026-0412",
    worker_id="WKR-1047",
)


class EchoInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(description="What to ask.")
    dose_value: float = 0.0
    unit: str = "rem"


class EchoOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str
    exposure_id: str


class StrictJsonChoice(str, Enum):
    NONE = "none"
    REQUIRED = "required"


class StrictJsonInput(BaseModel):
    model_config = ConfigDict(
        strict=True,
        extra="forbid",
    )

    choice: StrictJsonChoice
    citations: tuple[str, ...]


class StrictJsonOutput(BaseModel):
    model_config = ConfigDict(
        strict=True,
        extra="forbid",
    )

    accepted: bool


def strict_json_handler(
    subject: Subject,
    arguments: BaseModel,
) -> BaseModel:
    del subject

    assert isinstance(arguments, StrictJsonInput)
    assert arguments.choice == StrictJsonChoice.NONE
    assert arguments.citations == (
        "source-a",
        "source-b",
    )

    return StrictJsonOutput(
        accepted=True,
    )


def echo(subject: Subject, arguments: EchoInput) -> EchoOutput:
    return EchoOutput(answer=arguments.question.upper(), exposure_id=subject.exposure_id)


def failing(subject: Subject, arguments: EchoInput) -> EchoOutput:
    raise RetrievalError("the index is down")


ECHO_TOOL = Tool(
    name="echo",
    description="Repeat the question back, for tests.",
    input_model=EchoInput,
    output_model=EchoOutput,
    handler=echo,
)


def dispatcher(*tools: Tool, bounds: Bounds | None = None) -> ToolDispatcher:
    registry = ToolRegistry(list(tools) or [ECHO_TOOL])
    return ToolDispatcher(
        registry=registry,
        ledger=SessionLedger(bounds=bounds or Bounds()),
        subject=SUBJECT,
    )


def test_dispatcher_accepts_json_for_strict_input_model() -> None:
    tool = Tool(
        name="strict_json_tool",
        description="Test the strict JSON tool boundary.",
        input_model=StrictJsonInput,
        output_model=StrictJsonOutput,
        handler=strict_json_handler,
    )

    registry = ToolRegistry([tool])

    subject = Subject(
        session_id="session-json-test",
        officer_id=1,
        officer_code="OFFICER-1",
        exposure_id="exposure-json-test",
        worker_id="test",
    )

    existing_dispatcher = dispatcher()

    strict_dispatcher = ToolDispatcher(
        registry=registry,
        ledger=existing_dispatcher.ledger,
        subject=subject,
    )

    response = strict_dispatcher.invoke(
        "strict_json_tool",
        {
            "choice": "none",
            "citations": [
                "source-a",
                "source-b",
            ],
        },
    )

    assert response.ok is True
    assert response.error is None
    assert response.value is not None
    assert response.value["accepted"] is True

    assert len(strict_dispatcher.invocations) == 1
    assert strict_dispatcher.invocations[0].outcome == "ok"


def test_no_tool_schema_takes_the_subject() -> None:
    transport_tools = ApiToolset(transport=None).tools()
    registry = ToolRegistry([ECHO_TOOL, *transport_tools])

    offenders = {tool.name: tool.subject_arguments() for tool in registry.all()}

    assert all(not found for found in offenders.values()), offenders


def test_registering_a_tool_that_takes_a_subject_is_refused() -> None:
    class Bad(BaseModel):
        exposure_id: str

    with pytest.raises(DosimeterError):
        ToolRegistry(
            [
                Tool(
                    name="bad",
                    description="takes what it must not",
                    input_model=Bad,
                    output_model=EchoOutput,
                    handler=echo,
                )
            ]
        )


def test_the_subject_reaches_the_handler_without_being_an_argument() -> None:
    response = dispatcher().invoke("echo", {"question": "which quantity"})

    assert response.ok
    assert response.value["exposure_id"] == SUBJECT.exposure_id
    assert "exposure_id" not in ECHO_TOOL.input_schema()["properties"]


def test_a_subject_passed_as_an_argument_is_rejected() -> None:
    response = dispatcher().invoke("echo", {"question": "q", "exposure_id": "EXP-2026-0411"})

    assert not response.ok
    assert response.error.reason_code == ToolErrorCode.INVALID_ARGUMENTS


def test_arguments_that_miss_the_schema_come_back_as_an_error() -> None:
    response = dispatcher().invoke("echo", {"wrong": 1})

    assert not response.ok
    assert response.error.reason_code == ToolErrorCode.INVALID_ARGUMENTS


def test_a_failing_tool_returns_an_error_rather_than_raising() -> None:
    tool = Tool(
        name="flaky",
        description="always fails",
        input_model=EchoInput,
        output_model=EchoOutput,
        handler=failing,
    )

    response = dispatcher(tool).invoke("flaky", {"question": "q"})

    assert not response.ok
    assert response.error.reason_code == ToolErrorCode.INTERNAL
    assert "index is down" in response.error.message


def test_an_unknown_tool_is_an_error_not_an_exception() -> None:
    response = dispatcher().invoke("nope", {})

    assert response.error.reason_code == ToolErrorCode.NOT_FOUND


def test_the_invocation_cap_stops_the_next_call() -> None:
    dispatch = dispatcher(bounds=Bounds(max_tool_invocations_per_turn=2))

    first = dispatch.invoke("echo", {"question": "one"})
    second = dispatch.invoke("echo", {"question": "two"})
    third = dispatch.invoke("echo", {"question": "three"})

    assert first.ok and second.ok
    assert not third.ok
    assert third.error.reason_code == ToolErrorCode.BUDGET_EXHAUSTED
    assert "max_tool_invocations_per_turn" in third.error.message


def test_every_call_is_recorded_with_its_arguments_and_result() -> None:
    dispatch = dispatcher()
    dispatch.invoke("echo", {"question": "recorded"})

    record = dispatch.invocations[-1]

    assert record.tool == "echo"
    assert record.arguments == {"question": "recorded"}
    assert record.result["answer"] == "RECORDED"
    assert record.outcome == "ok"
    assert len(record.arguments_sha256) == 64


def test_a_disabled_tool_says_so() -> None:
    dispatch = dispatcher()
    dispatch.disable("echo")

    response = dispatch.invoke("echo", {"question": "q"})

    assert response.error.reason_code == ToolErrorCode.DISABLED


def test_keys_do_not_depend_on_argument_order() -> None:
    first = {"query_text": "retract failure", "limit": 5, "unit": "REM"}
    shuffled = {"unit": "rems", "limit": 5.0, "query_text": "retract failure"}

    assert canonicalize(first) == canonicalize(shuffled)
    assert arguments_hash(first) == arguments_hash(shuffled)
    assert idempotency_key("s1", "t", first) == idempotency_key("s1", "t", shuffled)


def test_keys_differ_by_session_and_tool() -> None:
    arguments = {"query_text": "retract failure"}

    assert idempotency_key("s1", "t", arguments) != idempotency_key("s2", "t", arguments)
    assert idempotency_key("s1", "t", arguments) != idempotency_key("s1", "other", arguments)


def test_nested_arguments_canonicalize_too() -> None:
    left = {"filters": {"status": "in_force", "doc_type": "regulation"}, "dose": {"unit": "Rads"}}
    right = {"dose": {"unit": "rad"}, "filters": {"doc_type": "regulation", "status": "in_force"}}

    assert canonicalize(left) == canonicalize(right)


def test_units_normalize_to_one_spelling() -> None:
    assert normalize_unit("REM") == normalize_unit("rems") == "rem"
    assert normalize_unit("Rads") == "rad"
    assert normalize_unit("bananas") == "bananas"


class UnreachableTransport:
    def get(self, path, params=None):
        raise_unreachable()

    def post(self, path, body=None):
        raise_unreachable()


def raise_unreachable() -> None:
    from dosimeter.errors import ExternalServiceError

    raise ExternalServiceError("connection refused")


class DenyingTransport:
    def get(self, path, params=None):
        return TransportResponse(403, {"reason_code": "district_not_granted", "message": "no"})

    def post(self, path, body=None):
        return TransportResponse(403, {"reason_code": "district_not_granted", "message": "no"})


def test_an_unreachable_api_disables_both_tools_and_names_them() -> None:
    toolset = ApiToolset(transport=UnreachableTransport())
    dispatch = ToolDispatcher(
        registry=ToolRegistry(toolset.tools()),
        ledger=SessionLedger(bounds=Bounds()),
        subject=SUBJECT,
    )

    response = dispatch.invoke("find_similar_exposures", {"query_text": "retract failure"})

    assert response.error.reason_code == ToolErrorCode.UNAVAILABLE
    assert toolset.capabilities_lost() == ["find_similar_exposures", "get_exposure_extraction"]
    assert response.error.detail["disabled"] == toolset.capabilities_lost()


def test_a_denial_from_the_api_is_surfaced_not_swallowed() -> None:
    toolset = ApiToolset(transport=DenyingTransport())
    dispatch = ToolDispatcher(
        registry=ToolRegistry(toolset.tools()),
        ledger=SessionLedger(bounds=Bounds()),
        subject=SUBJECT,
    )

    response = dispatch.invoke("get_exposure_extraction", {})

    assert response.error.reason_code == ToolErrorCode.DENIED
    assert response.error.detail["api_reason_code"] == "district_not_granted"


def test_similar_exposures_returns_candidates_not_a_conclusion() -> None:
    assert (
        "outcome"
        in SimilarExposures.model_json_schema()["$defs"]["SimilarExposureCandidate"]["properties"]
    )
    assert "conclusion" not in SimilarExposures.model_json_schema()["properties"]
    assert "limit" in FindSimilarExposuresInput.model_json_schema()["properties"]


def test_tool_errors_are_plain_data() -> None:
    error = ToolError(reason_code=ToolErrorCode.DENIED, message="no grant")

    assert error.model_dump()["reason_code"] == "not_entitled"
