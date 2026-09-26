"""
The tool dispatcher.

A tool is a Pydantic model for its arguments and a handler. The model chooses
what a tool does, never whose record it does it to. the dispatcher injects the
subject from the session, and no tool schema may contain it.
"""

import logging
import time
from collections.abc import Callable
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from dosimeter.errors import BudgetError, DosimeterError
from dosimeter.graph.schemas import Subject
from dosimeter.harness.budgets import SessionLedger
from dosimeter.harness.run_record import RunRecorder
from dosimeter.tools.idempotency import arguments_hash, idempotency_key

SUBJECT_ARGUMENT_NAMES = frozenset(
    {
        "exposure_id",
        "exposureid",
        "worker_id",
        "workerid",
        "officer_id",
        "officerid",
        "officer_code",
        "session_id",
        "sessionid",
        "subject",
        "subject_id",
    }
)

logger = logging.getLogger(__name__)


class ToolErrorCode(StrEnum):
    INVALID_ARGUMENTS = "invalid_arguments"
    UNAVAILABLE = "tool_unavailable"
    DENIED = "not_entitled"
    BUDGET_EXHAUSTED = "budget_exhausted"
    NOT_FOUND = "not_found"
    DISABLED = "tool_disabled"
    INTERNAL = "tool_failed"


class ToolError(BaseModel):
    """Tools return this. They do not raise at the model."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    reason_code: ToolErrorCode
    message: str
    detail: dict[str, Any] = Field(default_factory=dict)


class ToolResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tool: str
    ok: bool
    value: dict[str, Any] | None = None
    error: ToolError | None = None
    idempotency_key: str | None = None
    arguments_sha256: str | None = None
    duration_ms: float | None = None


Handler = Callable[[Subject, BaseModel], BaseModel]


class Tool:
    """One tool: its name, what it is for, the arguments it takes, and what it does."""

    def __init__(
        self,
        name: str,
        description: str,
        input_model: type[BaseModel],
        handler: Handler,
    ) -> None:
        self.name = name
        self.description = description
        self.input_model = input_model
        self.handler = handler

    def subject_arguments(self) -> list[str]:
        """Any model-filled argument that names a subject. Must always be empty."""

        properties = self.input_model.model_json_schema().get("properties", {})
        return sorted(name for name in properties if name.lower() in SUBJECT_ARGUMENT_NAMES)


def build_registry(tools: list[Tool]) -> dict[str, Tool]:
    """Every tool by name. A tool whose schema takes the subject is refused."""

    for tool in tools:
        if tool.subject_arguments():
            raise DosimeterError(
                "a tool schema may not take the subject as an argument",
                tool=tool.name,
                arguments=tool.subject_arguments(),
            )
    return {tool.name: tool for tool in tools}


class ToolDispatcher:
    """
    Runs tools for one turn. injects the subject, enforces the invocation cap,
    derives the idempotency key and records every call on the run record.
    """

    def __init__(
        self,
        registry: dict[str, Tool],
        ledger: SessionLedger,
        subject: Subject,
        recorder: RunRecorder | None = None,
    ) -> None:
        self.registry = registry
        self.ledger = ledger
        self.subject = subject
        self.recorder = recorder
        self.disabled: set[str] = set()

    def disable(self, *names: str) -> None:
        self.disabled.update(names)

    def invoke(self, tool_name: str, arguments: dict[str, Any] | None = None) -> ToolResponse:
        supplied = dict(arguments or {})
        started = time.perf_counter()

        def fail(code: ToolErrorCode, message: str, **detail: Any) -> ToolResponse:
            error = ToolError(reason_code=code, message=message, detail=detail)
            return self._finish(tool_name, supplied, started, error=error)

        tool = self.registry.get(tool_name)
        if tool is None:
            return fail(ToolErrorCode.NOT_FOUND, f"no tool named {tool_name}")

        if tool_name in self.disabled:
            return fail(ToolErrorCode.DISABLED, f"{tool_name} is unavailable for this turn")

        breach = self.ledger.check()
        if breach is not None:
            return fail(
                ToolErrorCode.BUDGET_EXHAUSTED,
                breach.message,
                ceiling=breach.ceiling,
                limit=breach.limit,
            )

        # the model chooses what, never whose
        for name in supplied:
            if name.lower() in SUBJECT_ARGUMENT_NAMES:
                return fail(
                    ToolErrorCode.INVALID_ARGUMENTS,
                    "the subject is injected by the dispatcher, not chosen",
                    argument=name,
                )

        try:
            parsed = tool.input_model.model_validate(supplied)
        except ValidationError as error:
            return fail(
                ToolErrorCode.INVALID_ARGUMENTS,
                "the arguments did not match the tool schema",
                errors=error.errors(include_url=False),
            )

        self.ledger.record_tool_invocation()

        try:
            result = tool.handler(self.subject, parsed)
        except BudgetError as error:
            return fail(ToolErrorCode.BUDGET_EXHAUSTED, str(error))
        except DosimeterError as error:
            return fail(ToolErrorCode.INTERNAL, str(error))

        if isinstance(result, ToolError):
            return self._finish(tool_name, supplied, started, error=result)

        return self._finish(tool_name, supplied, started, value=result.model_dump(mode="json"))

    def _finish(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        started: float,
        value: dict[str, Any] | None = None,
        error: ToolError | None = None,
    ) -> ToolResponse:
        duration_ms = round((time.perf_counter() - started) * 1000, 3)
        outcome = "ok" if error is None else error.reason_code.value
        digest = arguments_hash(arguments)

        # every call lands on the turn's run record, redacted there
        if self.recorder is not None:
            self.recorder.tool_called(
                tool_name,
                arguments,
                value,
                outcome,
                duration_ms=duration_ms,
                argument_sha256=digest,
            )

        logger.info(
            "tool.invoked",
            extra={
                "tool": tool_name,
                "outcome": outcome,
                "arguments_sha256": digest,
                "duration_ms": duration_ms,
            },
        )

        return ToolResponse(
            tool=tool_name,
            ok=error is None,
            value=value,
            error=error,
            idempotency_key=idempotency_key(self.subject.session_id, tool_name, arguments),
            arguments_sha256=digest,
            duration_ms=duration_ms,
        )
