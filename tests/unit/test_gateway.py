"""The read tools through the AgentCore Gateway: the transport choice, the tool schemas, and a Gateway that is down."""

import asyncio

import pytest

from dosimeter.api import mcp_server
from dosimeter.api.schemas import FindSimilarExposuresInput
from dosimeter.config.settings import Bounds, Settings
from dosimeter.errors import ConfigurationError, ExternalServiceError
from dosimeter.graph.schemas import Subject
from dosimeter.harness.budgets import SessionLedger
from dosimeter.tools.dispatcher import ToolDispatcher, ToolErrorCode, build_registry
from dosimeter.tools.gateway import GatewayTransport
from dosimeter.tools.registry import build_transport
from dosimeter.tools.tools import ApiToolset
from dosimeter.tools.transport import HttpTransport

# nothing listens here, so every call is refused straight away
DEAD_GATEWAY = "http://127.0.0.1:1/mcp"

SUBJECT = Subject(
    session_id="session-1",
    officer_id=1,
    officer_code="OFF-101",
    exposure_id="EXP-2026-0412",
)


def settings_for_tests(**overrides) -> Settings:
    return Settings(
        _env_file=None,
        bedrock_model_id="text-model-id",
        bedrock_embed_model_id="embedding-model-id",
        knowledge_base_id="kb",
        guardrail_id="gr",
        corpus_bucket="corpus",
        packet_bucket="packets",
        **overrides,
    )


def test_a_dead_gateway_disables_both_tools_and_the_turn_carries_on() -> None:
    toolset = ApiToolset(transport=GatewayTransport(DEAD_GATEWAY, token_provider=lambda: "token"))
    dispatcher = ToolDispatcher(
        registry=build_registry(toolset.tools()),
        ledger=SessionLedger(bounds=Bounds()),
        subject=SUBJECT,
    )

    response = dispatcher.invoke("find_similar_exposures", {"query_text": "retract failure"})

    assert response.error.reason_code == ToolErrorCode.UNAVAILABLE
    assert toolset.capabilities_lost() == ["find_similar_exposures", "get_exposure_extraction"]


def test_an_unreachable_gateway_is_a_typed_failure() -> None:
    with pytest.raises(ExternalServiceError, match="Gateway is unreachable"):
        GatewayTransport(DEAD_GATEWAY, token_provider=lambda: "token").call(
            "get_exposure_extraction", "EXP-2026-0412"
        )


def test_the_transport_setting_chooses_direct_http_or_the_gateway() -> None:
    assert isinstance(build_transport(settings_for_tests(), "OFF-101"), HttpTransport)

    with pytest.raises(ConfigurationError):
        build_transport(settings_for_tests(tool_transport="gateway"), "OFF-101")

    gateway = build_transport(
        settings_for_tests(
            tool_transport="gateway",
            gateway_url=DEAD_GATEWAY,
            identity_client_id="client-123",
            identity_password="demo-password",
        ),
        "OFF-101",
    )
    assert isinstance(gateway, GatewayTransport)


def test_the_mcp_tool_schemas_come_from_the_tool_models() -> None:
    tools = {tool.name: tool for tool in asyncio.run(mcp_server.mcp.list_tools())}

    assert set(tools) == {"get_exposure_extraction", "find_similar_exposures"}
    assert tools["get_exposure_extraction"].inputSchema["required"] == ["exposure_id"]

    similar = tools["find_similar_exposures"].inputSchema
    assert set(similar["properties"]) == {"exposure_id", "arguments"}
    assert (
        similar["$defs"]["FindSimilarExposuresInput"]["properties"].keys()
        == FindSimilarExposuresInput.model_json_schema()["properties"].keys()
    )
