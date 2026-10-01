"""The submit command: it reads settings, runs the pipeline, prints the report."""

from contextlib import contextmanager
from pathlib import Path

import pytest

from dosimeter.cli import main as cli
from dosimeter.errors import ExtractionError
from dosimeter.ingestion.submit import IngestionReport


@pytest.fixture
def configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BEDROCK_MODEL_ID", "text-model-id")
    monkeypatch.setenv("BEDROCK_EMBED_MODEL_ID", "embedding-model-id")
    monkeypatch.setenv("BEDROCK_KB_ID", "kb-000000")
    monkeypatch.setenv("DOSIMETER_GUARDRAIL_ID", "gr-000000")
    monkeypatch.setenv("AWS_CORPUS_BUCKET_NAME", "dosimeter-corpus")
    monkeypatch.setenv("AWS_PACKET_BUCKET_NAME", "dosimeter-packets")


@contextmanager
def fake_session():
    yield object()


def test_submit_prints_the_report_and_exits_zero(
    configured: None,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("dosimeter.repository.connection.session_scope", fake_session)
    monkeypatch.setattr(
        "dosimeter.ingestion.submit.submit_packet",
        lambda **kwargs: IngestionReport(exposure_id="EXP-2026-0412", artifacts_processed=4),
    )

    exit_code = cli.main(["submit", "./packets/exp-0412"])

    printed = capsys.readouterr().out
    assert exit_code == 0
    assert printed.splitlines()[0] == "EXP-2026-0412"
    assert "artifacts processed: 4" in printed


def test_submit_reports_a_failure_without_a_traceback(
    configured: None,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def explode(**kwargs):
        raise ExtractionError("packet directory does not exist")

    monkeypatch.setattr("dosimeter.repository.connection.session_scope", fake_session)
    monkeypatch.setattr("dosimeter.ingestion.submit.submit_packet", explode)

    with caplog.at_level("ERROR"):
        exit_code = cli.main(["submit", "./packets/nope"])

    assert exit_code == cli.EXIT_FAILED
    assert caplog.records[-1].message == "submit.failed"


def test_submit_needs_a_packet_directory(configured: None) -> None:
    with pytest.raises(SystemExit) as caught:
        cli.main(["submit"])

    assert caught.value.code != 0


def test_the_parser_hands_the_path_through_as_a_path() -> None:
    args = cli.build_parser().parse_args(["submit", "./packets/exp-0412"])

    assert args.packet_dir == Path("./packets/exp-0412")
