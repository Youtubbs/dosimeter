"""
Who is calling. The answer comes from a verified request context and never from
a body or a query argument, so swapping the local stub for gateway-propagated
identity later is a configuration change rather than a rewrite.
"""

import logging
from collections.abc import Mapping
from functools import lru_cache

import jwt
from pydantic import BaseModel, ConfigDict, Field

from dosimeter.config.settings import Settings

VERIFIED_HEADER = "X-Dosimeter-Verified-Officer"

logger = logging.getLogger(__name__)


class CallerIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    officer_code: str = Field(min_length=1)
    source: str = Field(min_length=1)


def resolve_caller(headers: Mapping[str, str], settings: Settings) -> CallerIdentity | None:
    """The caller, or None when the context carries no verified identity."""

    # once AgentCore Identity is configured, only a verified Cognito token names the caller
    if settings.identity_user_pool_id:
        return _token_caller(headers, settings)

    verified = headers.get(VERIFIED_HEADER)
    if verified:
        return CallerIdentity(officer_code=verified.strip(), source="verified_context")

    if settings.tool_api_dev_identity:
        stub = headers.get(settings.tool_api_identity_header)
        if stub:
            return CallerIdentity(officer_code=stub.strip(), source="dev_stub")

    return None


def cognito_issuer(settings: Settings) -> str:
    return f"https://cognito-idp.{settings.aws_region}.amazonaws.com/{settings.identity_user_pool_id}"


@lru_cache(maxsize=4)
def _signing_keys(issuer: str) -> jwt.PyJWKClient:
    """The user pool's public keys, fetched once and cached."""

    return jwt.PyJWKClient(f"{issuer}/.well-known/jwks.json")


def _token_caller(headers: Mapping[str, str], settings: Settings) -> CallerIdentity | None:
    """
    The officer named by the Cognito access token the Gateway passed on. The API
    checks the signature itself rather than trusting that the Gateway did.
    """

    scheme, _, token = headers.get("Authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None

    issuer = cognito_issuer(settings)

    try:
        key = _signing_keys(issuer).get_signing_key_from_jwt(token)
        claims = jwt.decode(token, key.key, algorithms=["RS256"], issuer=issuer)
    except jwt.PyJWTError as error:
        logger.warning("api.caller_rejected", extra={"detail": str(error)})
        return None

    if claims.get("token_use") != "access" or claims.get("client_id") != settings.identity_client_id:
        logger.warning("api.caller_rejected", extra={"detail": "not an access token for this client"})
        return None

    officer_code = claims.get("username")
    if not officer_code:
        return None

    logger.info(
        "api.caller_verified",
        extra={"officer_code": officer_code, "client_id": claims["client_id"]},
    )
    return CallerIdentity(officer_code=officer_code, source="gateway_jwt")
