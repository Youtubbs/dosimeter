"""reaching the read tools through the AgentCore Gateway, which exposes them as MCP tools"""

import asyncio
import json
from collections.abc import Callable
from typing import Any

from mcp.types import CallToolResult

from dosimeter.aws.gateway import call_gateway_tool
from dosimeter.errors import ExternalServiceError


class GatewayTransport:
    """
    The same call as HttpTransport, made as an MCP tool call on the Gateway. The
    caller proves who it is with a Cognito access token, and the Gateway passes that
    token on to the tool server.
    """

    def __init__(self, url: str, token_provider: Callable[[], str]) -> None:
        self.url = url
        self.token_provider = token_provider

    def call(
        self, tool: str, exposure_id: str, arguments: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        tool_arguments: dict[str, Any] = {"exposure_id": exposure_id}
        if arguments:
            tool_arguments["arguments"] = arguments

        # an unreachable Gateway or tool server, or a refused token, disables these tools for the turn
        try:
            result = asyncio.run(
                call_gateway_tool(
                    self.url,
                    tool,
                    lambda _tool: tool_arguments,
                    headers={"Authorization": f"Bearer {self.token_provider()}"},
                )
            )
        except ExternalServiceError:
            raise
        except Exception as error:
            raise ExternalServiceError(
                "the AgentCore Gateway is unreachable",
                detail=f"{type(error).__name__}: {error}",
            ) from error

        return payload_from(result)


def payload_from(result: CallToolResult) -> dict[str, Any]:
    """the tool server answers with the same JSON body the Flask API sends"""

    if result.structuredContent:
        return dict(result.structuredContent)

    text = "".join(getattr(block, "text", "") for block in result.content)
    try:
        return json.loads(text)
    except json.JSONDecodeError as error:
        raise ExternalServiceError(
            "the Gateway did not answer with JSON", detail=text[:200]
        ) from error
