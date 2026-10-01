"""AgentCore Identity: the tool API names the caller only from a verified Cognito token."""

import time
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from dosimeter.api.identity import VERIFIED_HEADER, cognito_issuer, resolve_caller
from dosimeter.config.settings import Settings

CLIENT_ID = "client-123"

SIGNING_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def settings_for_tests() -> Settings:
    return Settings(
        _env_file=None,
        bedrock_model_id="text-model-id",
        bedrock_embed_model_id="embedding-model-id",
        knowledge_base_id="kb",
        guardrail_id="gr",
        corpus_bucket="corpus",
        packet_bucket="packets",
        identity_user_pool_id="us-east-1_TestPool",
        identity_client_id=CLIENT_ID,
    )


def access_token(key=SIGNING_KEY, **overrides) -> str:
    claims = {
        "iss": cognito_issuer(settings_for_tests()),
        "token_use": "access",
        "client_id": CLIENT_ID,
        "username": "OFF-101",
        "exp": int(time.time()) + 300,
    }
    claims.update(overrides)
    return jwt.encode(claims, key, algorithm="RS256")


@pytest.fixture(autouse=True)
def user_pool_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stands in for the user pool's published public key."""

    keys = SimpleNamespace(
        get_signing_key_from_jwt=lambda token: SimpleNamespace(key=SIGNING_KEY.public_key())
    )
    monkeypatch.setattr("dosimeter.api.identity._signing_keys", lambda issuer: keys)


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_a_verified_token_names_the_officer() -> None:
    caller = resolve_caller(bearer(access_token()), settings_for_tests())

    assert caller.officer_code == "OFF-101"
    assert caller.source == "gateway_jwt"


def test_an_asserted_identity_without_a_token_is_rejected() -> None:
    assert resolve_caller({VERIFIED_HEADER: "OFF-101"}, settings_for_tests()) is None


def test_a_token_signed_by_anyone_else_is_rejected() -> None:
    assert resolve_caller(bearer(access_token(key=OTHER_KEY)), settings_for_tests()) is None


def test_a_token_for_another_client_or_an_id_token_is_rejected() -> None:
    assert resolve_caller(bearer(access_token(client_id="someone-else")), settings_for_tests()) is None
    assert resolve_caller(bearer(access_token(token_use="id")), settings_for_tests()) is None


def test_an_expired_token_is_rejected() -> None:
    expired = access_token(exp=int(time.time()) - 60)

    assert resolve_caller(bearer(expired), settings_for_tests()) is None
