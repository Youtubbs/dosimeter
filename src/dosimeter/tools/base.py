"""
The tool contract.

A tool is a pair of Pydantic models and a handler. The model chooses what a
tool does, never whose record it does it to: the subject is injected by the
dispatcher from the session, and no tool schema may contain it.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from dosimeter.errors import BudgetError, DosimeterError
from dosimeter.graph.state import Subject
from dosimeter.harness.budgets import SessionLedger
from dosimeter.logging_config import get_logger
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

_LOGGER = get_logger(__name__)


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


@dataclass(frozen=True)
class Tool:
    """One tool: its name, its models, and what it does."""

    name: str
    description: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    handler: Handler

    def input_schema(self) -> dict[str, Any]:
        return self.input_model.model_json_schema()

    def output_schema(self) -> dict[str, Any]:
        return self.output_model.model_json_schema()

    def subject_arguments(self) -> list[str]:
        """Any model-filled argument that names a subject. Must always be empty."""

        properties = self.input_schema().get("properties", {})
        return sorted(name for name in properties if name.lower() in SUBJECT_ARGUMENT_NAMES)


class ToolRegistry:
    """Every tool the project exposes, by name."""

    def __init__(self, tools: list[Tool] | None = None) -> None:
        self._tools: dict[str, Tool] = {}
        for tool in tools or []:
            self.register(tool)

    def register(self, tool: Tool) -> None:
        if tool.subject_arguments():
            raise DosimeterError(
                "a tool schema may not take the subject as an argument",
                tool=tool.name,
                arguments=tool.subject_arguments(),
            )
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return sorted(self._tools)

    def all(self) -> list[Tool]:
        return [self._tools[name] for name in self.names()]


@dataclass
class InvocationRecord:
    """What the run record keeps about one call."""

    tool: str
    arguments_sha256: str
    arguments: dict[str, Any]
    result: dict[str, Any] | None
    outcome: str
    duration_ms: float


@dataclass
class ToolDispatcher:
    """
    Runs tools for one turn: injects the subject, enforces the invocation cap,
    derives the idempotency key and records every call.
    """

    registry: ToolRegistry
    ledger: SessionLedger
    subject: Subject
    disabled: set[str] = field(default_factory=set)
    invocations: list[InvocationRecord] = field(default_factory=list)

    def disable(self, *names: str) -> None:
        self.disabled.update(names)

    def invoke(self, tool_name: str, arguments: dict[str, Any] | None = None) -> ToolResponse:
        supplied = dict(arguments or {})
        digest = arguments_hash(supplied)
        key = idempotency_key(self.subject.session_id, tool_name, supplied)
        started = time.perf_counter()

        tool = self.registry.get(tool_name)
        if tool is None:
            return self._finish(
                tool_name,
                digest,
                key,
                supplied,
                started,
                error=ToolError(
                    reason_code=ToolErrorCode.NOT_FOUND,
                    message=f"no tool named {tool_name}",
                ),
            )

        if tool_name in self.disabled:
            return self._finish(
                tool_name,
                digest,
                key,
                supplied,
                started,
                error=ToolError(
                    reason_code=ToolErrorCode.DISABLED,
                    message=f"{tool_name} is unavailable for this turn",
                ),
            )

        breach = self.ledger.check()
        if breach is not None:
            return self._finish(
                tool_name,
                digest,
                key,
                supplied,
                started,
                error=ToolError(
                    reason_code=ToolErrorCode.BUDGET_EXHAUSTED,
                    message=breach.message,
                    detail={"ceiling": breach.ceiling, "limit": breach.limit},
                ),
            )

        for name in supplied:
            if name.lower() in SUBJECT_ARGUMENT_NAMES:
                return self._finish(
                    tool_name,
                    digest,
                    key,
                    supplied,
                    started,
                    error=ToolError(
                        reason_code=ToolErrorCode.INVALID_ARGUMENTS,
                        message="the subject is injected by the dispatcher, not chosen",
                        detail={"argument": name},
                    ),
                )

        try:
            parsed = tool.input_model.model_validate(supplied)
        except ValidationError as error:
            return self._finish(
                tool_name,
                digest,
                key,
                supplied,
                started,
                error=ToolError(
                    reason_code=ToolErrorCode.INVALID_ARGUMENTS,
                    message="the arguments did not match the tool schema",
                    detail={"errors": error.errors(include_url=False)},
                ),
            )

        self.ledger.record_tool_invocation()

        try:
            result = tool.handler(self.subject, parsed)
        except BudgetError as error:
            return self._finish(
                tool_name,
                digest,
                key,
                supplied,
                started,
                error=ToolError(
                    reason_code=ToolErrorCode.BUDGET_EXHAUSTED,
                    message=str(error),
                ),
            )
        except DosimeterError as error:
            return self._finish(
                tool_name,
                digest,
                key,
                supplied,
                started,
                error=ToolError(reason_code=ToolErrorCode.INTERNAL, message=str(error)),
            )

        if isinstance(result, ToolError):
            return self._finish(tool_name, digest, key, supplied, started, error=result)

        return self._finish(
            tool_name,
            digest,
            key,
            supplied,
            started,
            value=result.model_dump(mode="json"),
        )

    def _finish(
        self,
        tool_name: str,
        digest: str,
        key: str,
        arguments: dict[str, Any],
        started: float,
        value: dict[str, Any] | None = None,
        error: ToolError | None = None,
    ) -> ToolResponse:
        duration_ms = round((time.perf_counter() - started) * 1000, 3)
        outcome = "ok" if error is None else error.reason_code.value

        self.invocations.append(
            InvocationRecord(
                tool=tool_name,
                arguments_sha256=digest,
                arguments=arguments,
                result=value,
                outcome=outcome,
                duration_ms=duration_ms,
            )
        )
        _LOGGER.info(
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
            idempotency_key=key,
            arguments_sha256=digest,
            duration_ms=duration_ms,
        )
