"""the two read tools as an MCP server, behind the AgentCore Gateway passthrough target.
the Gateway passes the officer token through; each call verifies it and runs the
same entitlement check as the Flask routes"""

import json

from mcp.server.fastmcp import Context, FastMCP
from mcp.types import CallToolResult, TextContent
from pydantic import BaseModel
from starlette.requests import Request
from starlette.responses import JSONResponse

from dosimeter.api.app import (
    NO_IDENTITY,
    Embedder,
    embedding_unavailable,
    extraction_for,
    similar_for,
)
from dosimeter.api.identity import resolve_caller
from dosimeter.api.schemas import Denial, FindSimilarExposuresInput
from dosimeter.config.settings import get_settings
from dosimeter.logging_config import configure_logging, correlation_scope
from dosimeter.repository.connection import session_scope

mcp = FastMCP(
    "DosimeterTools", host="0.0.0.0", stateless_http=True # noqa: S104 - runs in a container
)

# no embedding model is wired into the tool services yet, same as the Flask app
embedder: Embedder | None = None


def _officer(ctx: Context) -> str | None:
    request = ctx.request_context.request
    identity = resolve_caller(request.headers if request else {}, get_settings())
    return identity.officer_code if identity else None


def _answer(payload: BaseModel, status: int) -> CallToolResult:
    """the same body the Flask route sends; a denial is a tool error carrying its reason code"""

    body = payload.model_dump(mode="json")
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(body))],
        structuredContent=body,
        isError=status != 200,
    )


def _no_identity() -> CallToolResult:
    denial = Denial(
        reason_code=NO_IDENTITY,
        message="this call carries no verified identity",
        officer_code="unknown",
    )
    return _answer(denial, 403)


@mcp.tool()
def get_exposure_extraction(exposure_id: str, ctx: Context) -> CallToolResult:
    """Read the normalized fields cracked from one exposure packet."""

    officer_code = _officer(ctx)
    if officer_code is None:
        return _no_identity()

    with correlation_scope(), session_scope() as active:
        return _answer(
            *extraction_for(active, get_settings(), officer_code, exposure_id)
        )


@mcp.tool()
def find_similar_exposures(
    exposure_id: str, body: FindSimilarExposuresInput, ctx: Context
) -> CallToolResult:
    """Find earlier exposures whose narrative resembles this one."""

    officer_code = _officer(ctx)
    if officer_code is None:
        return _no_identity()

    if embedder is None:
        return _answer(embedding_unavailable(officer_code), 503)

    with correlation_scope(), session_scope() as active:
        return _answer(*similar_for(active, officer_code, exposure_id, body, embedder))


# the health check docker compose uses
@mcp.custom_route("/mcp/health", methods=["GET"])
async def health(_request: Request) -> JSONResponse:
    return JSONResponse({"status": "alive"})


if __name__ == "__main__":

    configure_logging(get_settings().log_level)

    # serves POST /mcp on port 8000
    mcp.run(transport="streamable-http")
