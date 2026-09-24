"""The eight commands exist, read the settings first, and quit non-zero."""

from __future__ import annotations

import os
from pathlib import Path

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

# submit is built, and has its own tests. Take a command out of this list as it
# lands.
IMPLEMENTED_COMMANDS = ("submit",)
UNFINISHED_COMMANDS = tuple(
    command for command in EXPECTED_COMMANDS if command not in IMPLEMENTED_COMMANDS
)


@pytest.fixture
def configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """A full set of settings, so a command only fails for being unfinished."""

    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setenv("BEDROCK_MODEL_ID", "text-model-id")
    monkeypatch.setenv("BEDROCK_EMBED_MODEL_ID", "embedding-model-id")
    monkeypatch.setenv("DOSIMETER_KNOWLEDGE_BASE_ID", "kb-000000")
    monkeypatch.setenv("DOSIMETER_GUARDRAIL_ID", "gr-000000")
    monkeypatch.setenv("AWS_CORPUS_BUCKET_NAME", "dosimeter-corpus")
    monkeypatch.setenv("AWS_PACKET_BUCKET_NAME", "dosimeter-packets")
    monkeypatch.setenv("DOSIMETER_DB_HOST", "dosimeter.example.us-east-1.rds.amazonaws.com")
    monkeypatch.setenv("DOSIMETER_DB_NAME", "dosimeter")
    monkeypatch.setenv("DOSIMETER_DB_USER", "dosimeter_app")


def test_the_eight_subcommands_are_the_whole_surface() -> None:
    assert tuple(COMMANDS) == EXPECTED_COMMANDS


@pytest.mark.parametrize("command", EXPECTED_COMMANDS)
def test_subcommand_parses(command: str) -> None:
    argv = [command, "./packets/exp-0412"] if command == "submit" else [command]
    args = build_parser().parse_args(argv)

    assert args.command == command


@pytest.mark.parametrize("command", UNFINISHED_COMMANDS)
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
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Run somewhere with no .env, so the developer's own file cannot supply
    # the settings this test needs to be missing.
    monkeypatch.chdir(tmp_path)
    for name in list(os.environ):
        if name.startswith("DOSIMETER_"):
            monkeypatch.delenv(name, raising=False)

    with caplog.at_level("ERROR"):
        exit_code = main(["assess"])

    assert exit_code == EXIT_CONFIG_ERROR
    assert caplog.records[-1].message == "config.invalid"
    assert "knowledge_base_id" in caplog.records[-1].fields


def test_an_unknown_subcommand_is_rejected() -> None:
    with pytest.raises(SystemExit) as caught:
        main(["notify"])

    assert caught.value.code != 0
