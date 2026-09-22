"""Tests for the settings."""

from __future__ import annotations

from typing import Any

import pytest

from dosimeter.config.settings import Settings, load_settings
from dosimeter.errors import ConfigurationError, DosimeterError

MODEL_ROLES = {
    "reasoning": "reasoning-model-id",
    "fast": "fast-model-id",
    "embedding": "embedding-model-id",
    "multimodal": "multimodal-model-id",
    "judge": "judge-model-id",
}

def valid_config(**overrides: Any) -> dict[str, Any]:
    """A working set of settings that a test can change one piece of."""

    payload: dict[str, Any] = {
        "models": dict(MODEL_ROLES),
        "knowledge_base_id": "kb-000000",
        "guardrail_id": "gr-000000",
        "corpus_bucket": "dosimeter-corpus",
        "packet_bucket": "dosimeter-packets",
        "db_host": "dosimeter.example.us-east-1.rds.amazonaws.com",
        "db_name": "dosimeter",
        "db_user": "dosimeter_app",
    }
    payload.update(overrides)
    return payload


def test_valid_configuration_loads() -> None:
    settings = load_settings(**valid_config())

    assert isinstance(settings, Settings)
    assert settings.aws_region == "us-east-1"
    assert settings.models.judge == "judge-model-id"


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


def test_no_secret_has_a_default_in_code() -> None:
    settings = load_settings(**valid_config())

    assert settings.db_use_iam_auth is True
    assert settings.db_password is None


def test_password_is_required_when_iam_auth_is_switched_off() -> None:
    with pytest.raises(ConfigurationError) as caught:
        load_settings(**valid_config(db_use_iam_auth=False))

    assert "db_password" in str(caught.value)


def test_dsn_carries_no_password() -> None:
    settings = load_settings(**valid_config(db_use_iam_auth=False, db_password="not-a-real-secret"))

    dsn = settings.dsn()

    assert "not-a-real-secret" not in dsn
    assert "dbname=dosimeter" in dsn
    assert "sslmode=require" in dsn


def test_password_is_not_readable_from_the_string_form() -> None:
    settings = load_settings(**valid_config(db_use_iam_auth=False, db_password="not-a-real-secret"))

    assert "not-a-real-secret" not in str(settings)
    assert settings.db_password is not None
    assert settings.db_password.get_secret_value() == "not-a-real-secret"
