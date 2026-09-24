"""Tests for worker-specific tool registries."""

import pytest
from pydantic import BaseModel, ConfigDict

from dosimeter.graph.state import Subject
from dosimeter.tools.base import Tool
from dosimeter.workers.toolsets import (
    build_notification_registry,
    build_written_report_registry,
)


class EmptyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EmptyOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool = True


def _dummy_handler(
    subject: Subject,
    arguments: BaseModel,
) -> BaseModel:
    del subject
    del arguments

    return EmptyOutput()


def make_shared_tool(name: str) -> Tool:
    """Create a harmless shared tool for registry tests."""

    return Tool(
        name=name,
        description=f"Test tool: {name}",
        input_model=EmptyInput,
        output_model=EmptyOutput,
        handler=_dummy_handler,
    )


def test_notification_registry_contains_only_notification_tools() -> None:
    extraction = make_shared_tool("get_exposure_extraction")

    registry = build_notification_registry(
        shared_tools=[extraction],
    )

    assert registry.names() == [
        "evaluate_rule",
        "get_exposure_extraction",
        "propose_notification",
    ]

    assert "propose_written_report" not in registry.names()


def test_written_report_registry_contains_only_report_tools() -> None:
    extraction = make_shared_tool("get_exposure_extraction")

    registry = build_written_report_registry(
        shared_tools=[extraction],
    )

    assert registry.names() == [
        "evaluate_rule",
        "get_exposure_extraction",
        "propose_written_report",
    ]

    assert "propose_notification" not in registry.names()


def test_notification_registry_can_include_retrieval() -> None:
    extraction = make_shared_tool("get_exposure_extraction")
    retrieval = make_shared_tool("search_knowledge_base")

    registry = build_notification_registry(
        shared_tools=[extraction, retrieval],
        include_retrieval=True,
    )

    assert registry.names() == [
        "evaluate_rule",
        "get_exposure_extraction",
        "propose_notification",
        "search_knowledge_base",
    ]


def test_written_report_registry_can_include_retrieval() -> None:
    extraction = make_shared_tool("get_exposure_extraction")
    retrieval = make_shared_tool("search_knowledge_base")

    registry = build_written_report_registry(
        shared_tools=[extraction, retrieval],
        include_retrieval=True,
    )

    assert registry.names() == [
        "evaluate_rule",
        "get_exposure_extraction",
        "propose_written_report",
        "search_knowledge_base",
    ]


def test_missing_extraction_tool_is_rejected() -> None:
    with pytest.raises(
        ValueError,
        match="required worker tool is unavailable: get_exposure_extraction",
    ):
        build_notification_registry(
            shared_tools=[],
        )


def test_missing_requested_retrieval_tool_is_rejected() -> None:
    extraction = make_shared_tool("get_exposure_extraction")

    with pytest.raises(
        ValueError,
        match="required worker tool is unavailable: search_knowledge_base",
    ):
        build_notification_registry(
            shared_tools=[extraction],
            include_retrieval=True,
        )
