"""the two read tools as an MCP server, behind the AgentCore Gateway passthrough target.
the Gateway passes the officer token through; each call verifies it and runs the
same entitlement check as the Flask routes"""

from typing import Any

from mcp.server.fastmcp import Context, FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from dosimeter.api.app import (
    NO_IDENTITY,
    Embedder,
    extraction_for,
    similar_for,
)
from dosimeter.api.identity import resolve_caller
from dosimeter.api.schemas import Denial, FindSimilarExposuresInput
from dosimeter.config.settings import get_settings
from dosimeter.logging_config import configure_logging, correlation_scope
from dosimeter.models.bedrock import embed_text
from dosimeter.repository.connection import session_scope

mcp = FastMCP(
    "DosimeterTools",
    host="0.0.0.0",  # noqa: S104 - runs in a container
    stateless_http=True,
)

# the same embedding model the Knowledge Base uses; a test can swap it
embedder: Embedder = embed_text


def _officer(ctx: Context) -> str | None:
    request = ctx.request_context.request
    identity = resolve_caller(request.headers if request else {}, get_settings())
    return identity.officer_code if identity else None


def _no_identity() -> dict[str, Any]:
    return Denial(
        reason_code=NO_IDENTITY,
        message="this call carries no verified identity",
        officer_code="unknown",
    ).model_dump(mode="json")


# each tool answers with the same JSON body the Flask route sends; a refusal carries its reason_code
@mcp.tool()
def get_exposure_extraction(exposure_id: str, ctx: Context) -> dict[str, Any]:
    """Read the normalized fields cracked from one exposure packet."""

    officer_code = _officer(ctx)
    if officer_code is None:
        return _no_identity()

    with correlation_scope(), session_scope() as active:
        payload, _status = extraction_for(active, get_settings(), officer_code, exposure_id)
    return payload.model_dump(mode="json")


@mcp.tool()
def find_similar_exposures(
    exposure_id: str, arguments: FindSimilarExposuresInput, ctx: Context
) -> dict[str, Any]:
    """Find earlier exposures whose narrative resembles this one."""

    officer_code = _officer(ctx)
    if officer_code is None:
        return _no_identity()

    with correlation_scope(), session_scope() as active:
        payload, _status = similar_for(active, officer_code, exposure_id, arguments, embedder)
    return payload.model_dump(mode="json")


# the health check docker compose uses
@mcp.custom_route("/mcp/health", methods=["GET"])
async def health(_request: Request) -> JSONResponse:
    return JSONResponse({"status": "alive"})


if __name__ == "__main__":
    configure_logging(get_settings().log_level)

    # serves POST /mcp on port 8000
    mcp.run(transport="streamable-http")
