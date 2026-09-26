"""The tool contract: no subject in a schema, stable keys, structured errors."""

import pytest
from pydantic import BaseModel, ConfigDict, Field

from dosimeter.api.schemas import FindSimilarExposuresInput, SimilarExposures
from dosimeter.config.settings import Bounds
from dosimeter.errors import DosimeterError, ExternalServiceError, RetrievalError
from dosimeter.graph.schemas import Subject
from dosimeter.harness.budgets import SessionLedger
from dosimeter.tools.dispatcher import (
    Tool,
    ToolDispatcher,
    ToolError,
    ToolErrorCode,
    build_registry,
)
from dosimeter.tools.idempotency import arguments_hash, canonicalize, idempotency_key
from dosimeter.tools.tools import ApiToolset
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


def echo(subject: Subject, arguments: EchoInput) -> EchoOutput:
    return EchoOutput(answer=arguments.question.upper(), exposure_id=subject.exposure_id)


def failing(subject: Subject, arguments: EchoInput) -> EchoOutput:
    raise RetrievalError("the index is down")


ECHO_TOOL = Tool(
    name="echo",
    description="Repeat the question back, for tests.",
    input_model=EchoInput,
    handler=echo,
)


class FakeRecorder:
    """Keeps what RunRecorder.tool_called would have written."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def tool_called(self, tool_name, arguments, result, outcome, **extra) -> None:
        self.calls.append(
            {"tool": tool_name, "arguments": arguments, "result": result, "outcome": outcome, **extra}
        )


def dispatcher(*tools: Tool, bounds: Bounds | None = None, recorder=None) -> ToolDispatcher:
    return ToolDispatcher(
        registry=build_registry(list(tools) or [ECHO_TOOL]),
        ledger=SessionLedger(bounds=bounds or Bounds()),
        subject=SUBJECT,
        recorder=recorder,
    )


def test_no_tool_schema_takes_the_subject() -> None:
    tools = [ECHO_TOOL, *ApiToolset(transport=None).tools()]

    offenders = {tool.name: tool.subject_arguments() for tool in tools}

    assert all(not found for found in offenders.values()), offenders


def test_registering_a_tool_that_takes_a_subject_is_refused() -> None:
    class Bad(BaseModel):
        exposure_id: str

    with pytest.raises(DosimeterError):
        build_registry([Tool(name="bad", description="takes what it must not", input_model=Bad, handler=echo)])


def test_the_subject_reaches_the_handler_without_being_an_argument() -> None:
    response = dispatcher().invoke("echo", {"question": "which quantity"})

    assert response.ok
    assert response.value["exposure_id"] == SUBJECT.exposure_id
    assert "exposure_id" not in EchoInput.model_json_schema()["properties"]


def test_a_subject_passed_as_an_argument_is_rejected() -> None:
    response = dispatcher().invoke("echo", {"question": "q", "exposure_id": "EXP-2026-0411"})

    assert not response.ok
    assert response.error.reason_code == ToolErrorCode.INVALID_ARGUMENTS


def test_arguments_that_miss_the_schema_come_back_as_an_error() -> None:
    response = dispatcher().invoke("echo", {"wrong": 1})

    assert not response.ok
    assert response.error.reason_code == ToolErrorCode.INVALID_ARGUMENTS


def test_a_failing_tool_returns_an_error_rather_than_raising() -> None:
    tool = Tool(name="flaky", description="always fails", input_model=EchoInput, handler=failing)

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


def test_every_call_lands_on_the_run_record() -> None:
    recorder = FakeRecorder()
    dispatcher(recorder=recorder).invoke("echo", {"question": "recorded"})

    call = recorder.calls[-1]

    assert call["tool"] == "echo"
    assert call["arguments"] == {"question": "recorded"}
    assert call["result"]["answer"] == "RECORDED"
    assert call["outcome"] == "ok"
    assert len(call["argument_sha256"]) == 64


def test_a_disabled_tool_says_so() -> None:
    dispatch = dispatcher()
    dispatch.disable("echo")

    response = dispatch.invoke("echo", {"question": "q"})

    assert response.error.reason_code == ToolErrorCode.DISABLED


def test_keys_do_not_depend_on_argument_order() -> None:
    first = {"query_text": "retract failure", "limit": 5, "unit": "rem"}
    shuffled = {"unit": "rem", "limit": 5, "query_text": "retract failure"}

    assert canonicalize(first) == canonicalize(shuffled)
    assert arguments_hash(first) == arguments_hash(shuffled)
    assert idempotency_key("s1", "t", first) == idempotency_key("s1", "t", shuffled)


def test_keys_differ_by_session_and_tool() -> None:
    arguments = {"query_text": "retract failure"}

    assert idempotency_key("s1", "t", arguments) != idempotency_key("s2", "t", arguments)
    assert idempotency_key("s1", "t", arguments) != idempotency_key("s1", "other", arguments)


def test_nested_arguments_canonicalize_too() -> None:
    left = {"filters": {"status": "in_force", "doc_type": "regulation"}, "dose": {"unit": "rad"}}
    right = {"dose": {"unit": "rad"}, "filters": {"doc_type": "regulation", "status": "in_force"}}

    assert canonicalize(left) == canonicalize(right)


class UnreachableTransport:
    def get(self, path):
        raise ExternalServiceError("connection refused")

    def post(self, path, body=None):
        raise ExternalServiceError("connection refused")


class DenyingTransport:
    def get(self, path):
        return TransportResponse(status=403, payload={"reason_code": "district_not_granted", "message": "no"})

    def post(self, path, body=None):
        return TransportResponse(status=403, payload={"reason_code": "district_not_granted", "message": "no"})


def test_an_unreachable_api_disables_both_tools_and_names_them() -> None:
    toolset = ApiToolset(transport=UnreachableTransport())
    dispatch = dispatcher(*toolset.tools())

    response = dispatch.invoke("find_similar_exposures", {"query_text": "retract failure"})

    assert response.error.reason_code == ToolErrorCode.UNAVAILABLE
    assert toolset.capabilities_lost() == ["find_similar_exposures", "get_exposure_extraction"]
    assert response.error.detail["disabled"] == toolset.capabilities_lost()


def test_a_denial_from_the_api_is_surfaced_not_swallowed() -> None:
    toolset = ApiToolset(transport=DenyingTransport())
    dispatch = dispatcher(*toolset.tools())

    response = dispatch.invoke("get_exposure_extraction", {})

    assert response.error.reason_code == ToolErrorCode.DENIED
    assert response.error.detail["api_reason_code"] == "district_not_granted"


def test_similar_exposures_returns_candidates_not_a_conclusion() -> None:
    assert "outcome" in SimilarExposures.model_json_schema()["$defs"]["SimilarExposureCandidate"][
        "properties"
    ]
    assert "conclusion" not in SimilarExposures.model_json_schema()["properties"]
    assert "limit" in FindSimilarExposuresInput.model_json_schema()["properties"]


def test_tool_errors_are_plain_data() -> None:
    error = ToolError(reason_code=ToolErrorCode.DENIED, message="no grant")

    assert error.model_dump()["reason_code"] == "not_entitled"
