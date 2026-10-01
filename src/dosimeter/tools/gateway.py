""" reaching the tool API through the AgentCore Gateway, which exposes it as MCP tools """

import asyncio
import json
import re
from collections.abc import Callable
from typing import Any

from mcp.types import CallToolResult, Tool as McpTool

from dosimeter.api.app import EMBEDDING_UNAVAILABLE, NO_IDENTITY, NOT_FOUND
from dosimeter.aws.gateway import call_gateway_tool
from dosimeter.errors import ExternalServiceError
from dosimeter.repository.entitlements import DISTRICT_NOT_GRANTED, NO_GRANTS, UNKNOWN_OFFICER
from dosimeter.tools.transport import TransportResponse

# the tool API path each read tool calls, and the MCP tool the Gateway exposes for it
TOOL_PATH = re.compile(r"^/v1/exposures/(?P<exposure_id>[^/]+)/(?P<resource>extraction|similar)$")
OPERATIONS = {
    "extraction": "get_exposure_extraction",
    "similar": "find_similar_exposures",
}

# the API's structured refusals, mapped back to the status the tool clients already understand
STATUS_FOR_REASON = {
    NO_IDENTITY: 403,
    UNKNOWN_OFFICER: 403,
    NO_GRANTS: 403,
    DISTRICT_NOT_GRANTED: 403,
    NOT_FOUND: 404,
    EMBEDDING_UNAVAILABLE: 503,
}


class GatewayTransport:
    """
    The same get and post as HttpTransport, but each call becomes an MCP tool call
    on the Gateway. The caller proves who it is with a Cognito access token, and the
    Gateway passes that token on to the tool API.
    """

    def __init__(self, url: str, token_provider: Callable[[], str]) -> None:
        self.url = url
        self.token_provider = token_provider

    def get(self, path: str) -> TransportResponse:
        return self._call(path, {})

    def post(self, path: str, body: dict[str, Any] | None = None) -> TransportResponse:
        return self._call(path, body or {})

    def _call(self, path: str, body: dict[str, Any]) -> TransportResponse:
        match = TOOL_PATH.match(path)
        if match is None:
            raise ExternalServiceError("the Gateway exposes no tool for this path", path=path)

        operation = OPERATIONS[match.group("resource")]

        # an unreachable Gateway or API, or a refused token, disables these tools for the turn
        try:
            result = asyncio.run(self._call_tool(operation, match.group("exposure_id"), body))
        except ExternalServiceError:
            raise
        except Exception as error:
            raise ExternalServiceError(
                "the AgentCore Gateway is unreachable",
                detail=f"{type(error).__name__}: {error}",
            ) from error

        return response_from(result)

    async def _call_tool(
        self,
        operation: str,
        exposure_id: str,
        body: dict[str, Any],
    ) -> CallToolResult:
        """ the officer token rides on every request; the Gateway passes it through to the tool server """

        return await call_gateway_tool(
            self.url,
            operation,
            lambda tool: tool_arguments(tool, exposure_id, body),
            headers={"Authorization": f"Bearer {self.token_provider()}"},
        )


def tool_arguments(tool: McpTool, exposure_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """ the exposure goes in as the path parameter; a request body is nested only if the tool asks for one """

    properties = (tool.inputSchema or {}).get("properties", {})

    if body and "body" in properties:
        return {"exposure_id": exposure_id, "body": body}

    return {"exposure_id": exposure_id, **body}


def response_from(result: CallToolResult) -> TransportResponse:
    """ turn an MCP tool result back into the status and payload the tool clients expect """

    payload = result.structuredContent or _payload_from_text(result)

    if not result.isError:
        return TransportResponse(status=200, payload=payload)

    return TransportResponse(
        status=STATUS_FOR_REASON.get(payload.get("reason_code"), 502),
        payload=payload,
    )


def _payload_from_text(result: CallToolResult) -> dict[str, Any]:
    text = "".join(getattr(block, "text", "") for block in result.content)

    try:
        payload = json.loads(text) if text else {}
    except json.JSONDecodeError:
        return {"message": text}

    return payload if isinstance(payload, dict) else {"result": payload}
