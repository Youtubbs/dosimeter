"""The dosimeter command line app. Each command reads the settings first and
then quits with 'not implemented' until someone fills it in."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from dosimeter import __version__
from dosimeter.config.settings import Settings, load_settings
from dosimeter.errors import ConfigurationError, DosimeterError
from dosimeter.logging_config import configure_logging, correlation_scope, get_logger

EXIT_CONFIG_ERROR = 2
EXIT_NOT_IMPLEMENTED = 3
EXIT_FAILED = 1

COMMANDS: dict[str, str] = {
    "submit": "Submit an exposure packet and produce a normalized record",
    "assess": "Apply the rules engine to a submitted exposure",
    "dossier": "Draft the cited dossier for an officer to review",
    "ask": "Answer a question grounded in the regulatory corpus",
    "sources": "List the sources behind an answer or a dossier",
    "trace": "Show the recorded trace for a run",
    "queue": "List exposures waiting for officer review",
    "review": "Record an officer decision on a queued exposure",
}

_LOGGER = get_logger(__name__)


def build_parser() -> argparse.ArgumentParser:
    """Set up the command line arguments, one entry per command."""

    parser = argparse.ArgumentParser(
        prog="dosimeter",
        description="Radiation exposure reporting copilot. The system describes; "
        "the officer determines.",
    )
    parser.add_argument("--version", action="version", version=f"dosimeter {__version__}")

    subparsers = parser.add_subparsers(dest="command", metavar="command", required=True)
    for name, help_text in COMMANDS.items():
        command = subparsers.add_parser(name, help=help_text, description=help_text)
        if name == "submit":
            command.add_argument("packet_dir", type=Path, help="the packet directory to submit")
        if name in ("assess", "trace", "dossier", "sources", "review"):
            command.add_argument("exposure_id", help="the exposure, for example EXP-2026-0412")
        if name in ("assess", "queue", "review"):
            command.add_argument(
                "--officer",
                required=True,
                help="the officer code this command runs as",
            )
        if name == "review":
            command.add_argument(
                "--decision",
                choices=("approve", "edit-then-approve", "reject"),
                help="record a decision instead of showing the card",
            )
            command.add_argument("--note", help="a note to add when editing then approving")

    return parser


def _load_configuration() -> Settings:
    return load_settings()


def main(argv: Sequence[str] | None = None) -> int:
    """What runs when you type dosimeter."""

    parser = build_parser()
    args = parser.parse_args(argv)

    configure_logging()

    with correlation_scope():
        try:
            settings = _load_configuration()
        except ConfigurationError as error:
            _LOGGER.error(
                "config.invalid",
                extra={"command": args.command, "fields": error.context.get("fields", [])},
            )
            return EXIT_CONFIG_ERROR

        configure_logging(settings.log_level)

        if args.command == "submit":
            return _submit(args.packet_dir, settings)

        if args.command == "assess":
            return _assess(args.exposure_id, args.officer, settings)

        if args.command == "trace":
            return _trace(args.exposure_id)

        if args.command == "queue":
            return _queue(args.officer)

        if args.command == "review":
            return _review(args.exposure_id, args.officer, args.decision, args.note)

        _LOGGER.error(
            "command.not_implemented",
            extra={"command": args.command, "detail": "not implemented"},
        )
        return EXIT_NOT_IMPLEMENTED


def _submit(packet_dir: Path, settings: Settings) -> int:
    """Run the submit pipeline and print its report."""

    from dosimeter.ingestion.artifact_store import S3ObjectStore
    from dosimeter.ingestion.submit import submit_packet
    from dosimeter.repository.connection import session_scope

    try:
        with session_scope() as session:
            report = submit_packet(
                session=session,
                packet_dir=packet_dir,
                settings=settings,
                store=S3ObjectStore(),
            )
    except DosimeterError as error:
        _LOGGER.error("submit.failed", extra={"detail": str(error)})
        return EXIT_FAILED

    sys.stdout.write(report.render() + "\n")
    return 0


def _assess(exposure_id: str, officer_code: str, settings: Settings) -> int:
    """Run the workflow on a submitted exposure and persist what it produced."""

    from dosimeter.graph.nodes import build_nodes, escalation_evaluator
    from dosimeter.harness.assess import run_assess
    from dosimeter.repository.connection import session_scope

    try:
        with session_scope() as session:
            result = run_assess(
                session=session,
                exposure_id=exposure_id,
                officer_code=officer_code,
                settings=settings,
                nodes=build_nodes(settings),
                evaluate=escalation_evaluator(),
            )
    except DosimeterError as error:
        _LOGGER.error("assess.failed", extra={"detail": str(error)})
        return EXIT_FAILED

    lines = [
        result.exposure_id,
        f"outcome:   {result.outcome}",
        f"run id:    {result.run_id}",
        f"duration:  {result.duration_seconds:.2f} s",
    ]
    if result.eligibility is not None:
        lines.append(f"triggers:  {result.eligibility.outcome.reason()}")
        if result.escalated:
            lines.append(f"queued as: {result.eligibility.queue_id}")

    sys.stdout.write("\n".join(lines) + "\n")
    return 0


def _trace(exposure_id: str) -> int:
    """Render the stored run record."""

    from dosimeter.harness.trace import render_trace
    from dosimeter.repository.connection import session_scope

    try:
        with session_scope() as session:
            rendered = render_trace(session, exposure_id)
    except DosimeterError as error:
        _LOGGER.error("trace.failed", extra={"detail": str(error)})
        return EXIT_FAILED

    sys.stdout.write(rendered + "\n")
    return 0


def _queue(officer_code: str) -> int:
    """List the escalated dossiers this officer may see."""

    from dosimeter.harness.review import queue_entries
    from dosimeter.repository.connection import session_scope

    try:
        with session_scope() as session:
            entries = queue_entries(session, officer_code)
    except DosimeterError as error:
        _LOGGER.error("queue.failed", extra={"detail": str(error)})
        return EXIT_FAILED

    if not isinstance(entries, list):
        sys.stdout.write(f"{entries.reason_code}: {entries.message}\n")
        return EXIT_FAILED

    if not entries:
        sys.stdout.write("nothing waiting for review\n")
        return 0

    lines = []
    for entry in entries:
        lines.append(f"{entry.queue_id}  {entry.exposure_id}  {entry.district}")
        for trigger in entry.triggers:
            lines.append(f"      {trigger}")

    sys.stdout.write("\n".join(lines) + "\n")
    return 0


def _review(exposure_id: str, officer_code: str, decision: str | None, note: str | None) -> int:
    """Show the decision card, or record a decision."""

    from dosimeter.harness.review_cli import record_from_cli, render_decision_card
    from dosimeter.repository.connection import session_scope

    try:
        with session_scope() as session:
            if decision is None:
                rendered = render_decision_card(session, exposure_id, officer_code)
            else:
                rendered = record_from_cli(session, exposure_id, officer_code, decision, note)
    except DosimeterError as error:
        _LOGGER.error("review.failed", extra={"detail": str(error)})
        return EXIT_FAILED

    sys.stdout.write(rendered + "\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
