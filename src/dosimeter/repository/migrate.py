"""
Migration runner. Numbered SQL files in migrations/ are applied in order and
recorded, so running it twice only applies what is new.

    python -m dosimeter.repository.migrate up
    python -m dosimeter.repository.migrate status
"""

import argparse
import logging
from collections.abc import Sequence
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from dosimeter.errors import DosimeterError
from dosimeter.logging_config import configure_logging
from dosimeter.repository.connection import session_scope
from dosimeter.repository.orm import SchemaMigrationRow

MIGRATIONS_DIR = Path(__file__).parent / "migrations"

CREATE_VERSION_TABLE = text(
    """
    CREATE TABLE IF NOT EXISTS schema_migrations (
        version text PRIMARY KEY,
        applied_at timestamptz NOT NULL DEFAULT now()
    )
    """
)

logger = logging.getLogger(__name__)


def migration_files() -> list[Path]:
    """Every migration on disk, in order."""

    return sorted(MIGRATIONS_DIR.glob("*.sql"))


def applied_versions(session: Session) -> set[str]:
    """Versions already recorded in the database."""

    session.execute(CREATE_VERSION_TABLE)
    session.commit()
    return set(session.scalars(select(SchemaMigrationRow.version)).all())


def pending(session: Session) -> list[Path]:
    """Migrations on disk that this database has not run yet."""

    done = applied_versions(session)
    return [path for path in migration_files() if path.stem not in done]


def migrate_up(session: Session) -> list[str]:
    """Apply every pending migration. Returns the versions applied."""

    applied: list[str] = []
    for path in pending(session):
        session.execute(text(path.read_text(encoding="utf-8")))
        session.add(SchemaMigrationRow(version=path.stem))
        session.commit()
        applied.append(path.stem)
        logger.info("migration.applied", extra={"version": path.stem})
    return applied


def _setup_checkpointer() -> None:
    """The graph checkpointer owns its own tables, so it creates them here."""

    from dosimeter.graph.checkpointer import setup_checkpointer

    setup_checkpointer()
    logger.info("migrate.checkpointer_ready", extra={"tables": "checkpoints"})


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="dosimeter-migrate")
    parser.add_argument("command", choices=("up", "status"))
    args = parser.parse_args(argv)

    configure_logging()
    try:
        with session_scope() as session:
            if args.command == "up":
                applied = migrate_up(session)
                logger.info("migrate.up", extra={"applied": applied or "nothing pending"})
                _setup_checkpointer()
            else:
                waiting = [path.stem for path in pending(session)]
                logger.info("migrate.status", extra={"pending": waiting or "none"})
    except DosimeterError as error:
        logger.error("migrate.failed", extra={"detail": str(error)})
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
