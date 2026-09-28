"""Worker-specific tool registry construction.

Each worker receives only the tools required for its responsibility.
"""

from collections.abc import Iterable

from dosimeter.tools.base import Tool, ToolRegistry
from dosimeter.tools.proposals import (
    PROPOSE_NOTIFICATION_TOOL,
    PROPOSE_WRITTEN_REPORT_TOOL,
)
from dosimeter.tools.rules import EVALUATE_RULE_TOOL

GET_EXPOSURE_EXTRACTION = "get_exposure_extraction"
SEARCH_KNOWLEDGE_BASE = "search_knowledge_base"


def _find_tool(
    tools: Iterable[Tool],
    name: str,
) -> Tool:
    """Return a required tool by name."""

    for tool in tools:
        if tool.name == name:
            return tool

    raise ValueError(f"required worker tool is unavailable: {name}")


def build_notification_registry(
    *,
    shared_tools: Iterable[Tool],
) -> ToolRegistry:
    """Build the least-privilege tool registry for the Notification Worker."""

    available = list(shared_tools)

    return ToolRegistry(
        [
            _find_tool(available, SEARCH_KNOWLEDGE_BASE),
            _find_tool(available, GET_EXPOSURE_EXTRACTION),
            EVALUATE_RULE_TOOL,
            PROPOSE_NOTIFICATION_TOOL,
        ]
    )


def build_written_report_registry(
    *,
    shared_tools: Iterable[Tool],
) -> ToolRegistry:
    """Build the least-privilege tool registry for the Written Report Worker."""

    available = list(shared_tools)

    return ToolRegistry(
        [
            _find_tool(available, SEARCH_KNOWLEDGE_BASE),
            _find_tool(available, GET_EXPOSURE_EXTRACTION),
            EVALUATE_RULE_TOOL,
            PROPOSE_WRITTEN_REPORT_TOOL,
        ]
    )


__all__ = [
    "GET_EXPOSURE_EXTRACTION",
    "SEARCH_KNOWLEDGE_BASE",
    "build_notification_registry",
    "build_written_report_registry",
]
