"""calling one tool on an AgentCore Gateway over MCP. the read tools sign in with a Cognito
token; the knowledge base Gateway is signed with SigV4"""

from collections.abc import Callable
from typing import Any

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.types import CallToolResult
from mcp.types import Tool as McpTool

from dosimeter.config.settings import get_settings
from dosimeter.errors import ExternalServiceError


def gateway_tool(tools: list[McpTool], operation: str) -> McpTool:
    """the Gateway names a target's tools '<target>___<operation>'"""

    for tool in tools:
        if tool.name == operation or tool.name.endswith(f"___{operation}"):
            return tool

    raise ExternalServiceError(
        "the Gateway does not expose this tool", operation=operation
    )


async def call_gateway_tool(
    url: str,
    operation: str,
    arguments_for: Callable[[McpTool], dict[str, Any]],
    headers: dict[str, str] | None = None,
    auth: httpx.Auth | None = None,
) -> CallToolResult:
    """open an MCP session on the Gateway, find the tool, and call it with the arguments its schema asks for"""

    timeout = get_settings().bounds.per_call_http_timeout_seconds

    async with httpx.AsyncClient(
        timeout=timeout, headers=headers, auth=auth, follow_redirects=True
    ) as http_client:
        async with streamable_http_client(url, http_client=http_client) as (
            read,
            write,
            _,
        ):
            async with ClientSession(read, write) as session:
                await session.initialize()

                listed = await session.list_tools()
                tool = gateway_tool(listed.tools, operation)

                return await session.call_tool(tool.name, arguments_for(tool))
