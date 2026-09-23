"""The eight commands exist, read the settings first, and quit non-zero."""

from __future__ import annotations

import os

import pytest

from dosimeter.cli.main import COMMANDS, EXIT_CONFIG_ERROR, EXIT_NOT_IMPLEMENTED, build_parser, main

EXPECTED_COMMANDS = (
    "submit",
    "assess",
    "dossier",
    "ask",
    "sources",
    "trace",
    "queue",
    "review",
)


@pytest.fixture
def configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """A full set of settings, so a command only fails for being unfinished."""

    monkeypatch.setenv("DOSIMETER_AWS_REGION", "us-east-1")
    for role in ("reasoning", "fast", "embedding", "multimodal", "judge"):
        monkeypatch.setenv(f"DOSIMETER_MODELS__{role.upper()}", f"{role}-model-id")
    monkeypatch.setenv("DOSIMETER_KNOWLEDGE_BASE_ID", "kb-000000")
    monkeypatch.setenv("DOSIMETER_GUARDRAIL_ID", "gr-000000")
    monkeypatch.setenv("DOSIMETER_CORPUS_BUCKET", "dosimeter-corpus")
    monkeypatch.setenv("DOSIMETER_PACKET_BUCKET", "dosimeter-packets")
    monkeypatch.setenv("DOSIMETER_DB_HOST", "dosimeter.example.us-east-1.rds.amazonaws.com")
    monkeypatch.setenv("DOSIMETER_DB_NAME", "dosimeter")
    monkeypatch.setenv("DOSIMETER_DB_USER", "dosimeter_app")


def test_the_eight_subcommands_are_the_whole_surface() -> None:
    assert tuple(COMMANDS) == EXPECTED_COMMANDS


@pytest.mark.parametrize("command", EXPECTED_COMMANDS)
def test_subcommand_parses(command: str) -> None:
    args = build_parser().parse_args([command])

    assert args.command == command


@pytest.mark.parametrize("command", EXPECTED_COMMANDS)
def test_subcommand_exits_non_zero_with_not_implemented(
    command: str,
    configured: None,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level("ERROR"):
        exit_code = main([command])

    assert exit_code == EXIT_NOT_IMPLEMENTED
    assert exit_code != 0
    assert caplog.records[-1].message == "command.not_implemented"
    assert caplog.records[-1].detail == "not implemented"


def test_command_loads_configuration_before_anything_else(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    for name in list(os.environ):
        if name.startswith("DOSIMETER_"):
            monkeypatch.delenv(name, raising=False)

    with caplog.at_level("ERROR"):
        exit_code = main(["submit"])

    assert exit_code == EXIT_CONFIG_ERROR
    assert caplog.records[-1].message == "config.invalid"
    assert "knowledge_base_id" in caplog.records[-1].fields


def test_an_unknown_subcommand_is_rejected() -> None:
    with pytest.raises(SystemExit) as caught:
        main(["notify"])

    assert caught.value.code != 0
