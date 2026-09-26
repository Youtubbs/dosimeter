"""
Who is calling. The answer comes from a verified request context and never from
a body or a query argument, so swapping the local stub for gateway-propagated
identity later is a configuration change rather than a rewrite.
"""

from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict, Field

from dosimeter.config.settings import Settings

VERIFIED_HEADER = "X-Dosimeter-Verified-Officer"


class CallerIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    officer_code: str = Field(min_length=1)
    source: str = Field(min_length=1)


def resolve_caller(headers: Mapping[str, str], settings: Settings) -> CallerIdentity | None:
    """The caller, or None when the context carries no verified identity."""

    verified = headers.get(VERIFIED_HEADER)
    if verified:
        return CallerIdentity(officer_code=verified.strip(), source="verified_context")

    if settings.tool_api_dev_identity:
        stub = headers.get(settings.tool_api_identity_header)
        if stub:
            return CallerIdentity(officer_code=stub.strip(), source="dev_stub")

    return None
