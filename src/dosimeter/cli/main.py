"""The dosimeter command line app. Each command reads the settings first and
then quits with 'not implemented' until someone fills it in."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from dosimeter import __version__
from dosimeter.config.settings import Settings, load_settings
from dosimeter.errors import ConfigurationError
from dosimeter.logging_config import configure_logging, correlation_scope, get_logger

EXIT_CONFIG_ERROR = 2
EXIT_NOT_IMPLEMENTED = 3

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
        subparsers.add_parser(name, help=help_text, description=help_text)

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
        _LOGGER.error(
            "command.not_implemented",
            extra={"command": args.command, "detail": "not implemented"},
        )
        return EXIT_NOT_IMPLEMENTED


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
