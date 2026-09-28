"""Tests for the central Dosimeter tool registry."""

from dosimeter.tools.registry import build_tool_registry


class DummyTransport:
    """Transport placeholder used only for registry construction tests."""

    def get(self, path: str, params: dict | None = None):
        raise AssertionError("transport should not be called")

    def post(self, path: str, payload: dict):
        raise AssertionError("transport should not be called")


def test_registry_contains_expected_tools() -> None:
    registry = build_tool_registry(DummyTransport())

    assert registry.names() == [
        "evaluate_rule",
        "find_similar_exposures",
        "get_exposure_extraction",
        "propose_notification",
        "propose_written_report",
        "search_knowledge_base",
    ]


def test_registered_tools_do_not_expose_subject_arguments() -> None:
    registry = build_tool_registry(DummyTransport())

    for tool in registry.all():
        assert tool.subject_arguments() == []
