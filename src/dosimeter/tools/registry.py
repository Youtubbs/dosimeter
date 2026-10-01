"""Central registry construction for Dosimeter tools."""

from dosimeter.aws.aws import cognito_access_token
from dosimeter.config.settings import Settings
from dosimeter.errors import ConfigurationError
from dosimeter.tools.dispatcher import Tool, build_registry
from dosimeter.tools.gateway import GatewayTransport
from dosimeter.tools.proposals import proposal_tools
from dosimeter.tools.rules import rule_tools
from dosimeter.tools.search_knowledge_base import SEARCH_KNOWLEDGE_BASE
from dosimeter.tools.tools import ApiToolset
from dosimeter.tools.transport import HttpTransport


def build_tool_registry(transport: HttpTransport | GatewayTransport) -> dict[str, Tool]:
    """Build the complete registry of currently implemented Dosimeter tools."""

    api_toolset = ApiToolset(transport=transport)

    return build_registry(
        [
            SEARCH_KNOWLEDGE_BASE,
            *api_toolset.tools(),
            *rule_tools(),
            *proposal_tools(),
        ]
    )


def build_transport(
    settings: Settings,
    officer_code: str,
    access_token: str | None = None,
) -> HttpTransport | GatewayTransport:
    """How the read tools reach the tool API for this officer: directly, or through the Gateway."""

    if settings.tool_transport == "http":
        return HttpTransport(settings.tool_api_base_url, officer_code)

    # on the Runtime the CLI signs the officer in and passes the token along
    if settings.gateway_url and access_token:
        return GatewayTransport(settings.gateway_url, token_provider=lambda: access_token)

    if not (settings.gateway_url and settings.identity_client_id and settings.identity_password):
        raise ConfigurationError(
            "the Gateway transport needs a Gateway URL and an identity client and password",
            fields=["gateway_url", "identity_client_id", "identity_password"],
        )

    password = settings.identity_password.get_secret_value()
    client_id = settings.identity_client_id

    # the token is fetched on each call, so it is never stale and never fetched when unused
    return GatewayTransport(
        settings.gateway_url,
        token_provider=lambda: cognito_access_token(officer_code, password, client_id),
    )


def shared_tools(
    settings: Settings,
    officer_code: str,
    access_token: str | None = None,
) -> list[Tool]:
    """Every tool, bound to this officer's transport. Each worker takes only the ones it needs."""

    transport = build_transport(settings, officer_code, access_token)
    return list(build_tool_registry(transport).values())
