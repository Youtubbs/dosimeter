"""Tests for the settings."""

from __future__ import annotations

import os
from typing import Any

import pytest

from dosimeter.config.settings import (
    DatabaseSettings,
    Settings,
    load_database_settings,
    load_settings,
)
from dosimeter.errors import ConfigurationError, DosimeterError

TEXT_MODEL = "text-model-id"
EMBED_MODEL = "embedding-model-id"

def valid_config(**overrides: Any) -> dict[str, Any]:
    """A working set of settings that a test can change one piece of."""

    payload: dict[str, Any] = {
        "_env_file": None,
        "bedrock_model_id": TEXT_MODEL,
        "bedrock_embed_model_id": EMBED_MODEL,
        "knowledge_base_id": "kb-000000",
        "guardrail_id": "gr-000000",
        "corpus_bucket": "dosimeter-corpus",
        "packet_bucket": "dosimeter-packets",
    }
    payload.update(overrides)
    return payload


def test_valid_configuration_loads() -> None:
    settings = load_settings(**valid_config())

    assert isinstance(settings, Settings)
    assert settings.aws_region == "us-east-1"
    assert settings.bedrock_model_id == TEXT_MODEL


def test_defaults_cover_floors_margins_and_bounds() -> None:
    settings = load_settings(**valid_config())

    assert settings.confidence_floor == 0.60
    assert settings.similarity_threshold == 0.50
    assert settings.near_boundary_margins.annual_limit_tede_rem == 0.25
    assert settings.near_boundary_margins.immediate_notification_shallow_rad == 10.0
    assert settings.bounds.max_tool_invocations_per_turn == 8
    assert settings.bounds.tokens_for("coordinator") == 4096
    assert settings.bounds.tokens_for("not-an-agent") == settings.bounds.default_max_tokens_per_call


def test_environment_overrides_a_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DOSIMETER_BOUNDS__MAX_TOOL_INVOCATIONS_PER_TURN", "3")
    monkeypatch.setenv("DOSIMETER_CONFIDENCE_FLOOR", "0.75")

    settings = load_settings(**valid_config())

    assert settings.bounds.max_tool_invocations_per_turn == 3
    assert settings.confidence_floor == 0.75


def test_missing_required_field_names_the_field() -> None:
    payload = valid_config()
    del payload["knowledge_base_id"]

    with pytest.raises(ConfigurationError) as caught:
        load_settings(**payload)

    assert "knowledge_base_id" in str(caught.value)
    assert "knowledge_base_id" in caught.value.context["fields"]
    assert isinstance(caught.value, DosimeterError)


def test_invalid_value_names_the_field() -> None:
    with pytest.raises(ConfigurationError) as caught:
        load_settings(**valid_config(confidence_floor=1.5))

    assert "confidence_floor" in str(caught.value)


def test_region_outside_us_east_is_rejected() -> None:
    with pytest.raises(ConfigurationError) as caught:
        load_settings(**valid_config(aws_region="eu-west-1"))

    assert "aws_region" in str(caught.value)


@pytest.fixture(autouse=True)
def clean_settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Importing dosimeter.aws.config loads the developer's .env into the real
    environment, so clear it before asserting what is missing.
    """

    for name in list(os.environ):
        if name.startswith("DOSIMETER_"):
            monkeypatch.delenv(name, raising=False)


@pytest.fixture
def clean_db_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ignore whatever the developer has in their own .env."""

    for name in list(os.environ):
        if name.startswith("DOSIMETER_DB_"):
            monkeypatch.delenv(name, raising=False)


def valid_database(**overrides: Any) -> dict[str, Any]:
    """Database settings that a test can change one piece of."""

    payload: dict[str, Any] = {
        "_env_file": None,
        "host": "dosimeter.example.us-east-1.rds.amazonaws.com",
        "name": "dosimeter",
        "user": "dosimeter_app",
    }
    payload.update(overrides)
    return payload


def test_database_settings_load_on_their_own(clean_db_env: None) -> None:
    settings = load_database_settings(**valid_database())

    assert isinstance(settings, DatabaseSettings)
    assert settings.port == 5432
    assert settings.sslmode == "require"


def test_missing_database_field_names_the_field(clean_db_env: None) -> None:
    payload = valid_database()
    del payload["host"]

    with pytest.raises(ConfigurationError) as caught:
        load_database_settings(**payload)

    assert "host" in str(caught.value)


def test_no_secret_has_a_default_in_code(clean_db_env: None) -> None:
    settings = load_database_settings(**valid_database())

    assert settings.use_iam_auth is True
    assert settings.password is None


def test_password_is_required_when_iam_auth_is_switched_off(clean_db_env: None) -> None:
    with pytest.raises(ConfigurationError) as caught:
        load_database_settings(**valid_database(use_iam_auth=False))

    assert "password" in str(caught.value)


def test_password_is_not_readable_from_the_string_form(clean_db_env: None) -> None:
    settings = load_database_settings(
        **valid_database(use_iam_auth=False, password="not-a-real-secret")
    )

    assert "not-a-real-secret" not in str(settings)
    assert settings.password is not None
    assert settings.password.get_secret_value() == "not-a-real-secret"


def test_database_settings_read_their_own_environment(
    clean_db_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DOSIMETER_DB_HOST", "localhost")
    monkeypatch.setenv("DOSIMETER_DB_PORT", "55432")

    settings = load_database_settings(_env_file=None, name="dosimeter", user="dosimeter")

    assert settings.host == "localhost"
    assert settings.port == 55432
