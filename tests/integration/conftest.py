"""
Fixtures for the tests that need a real database.

They run against the compose database. Start it with:

    docker compose up -d

Set DOSIMETER_TEST_URL to point somewhere else. When nothing answers, these
tests skip, so a clone without Docker still runs the suite.

Every test drops and recreates the public schema of that database, so point it
at a database you do not mind losing, such as a separate dosimeter_test
database. The assess test opens its checkpointer from the DOSIMETER_DB_*
settings, so set DOSIMETER_DB_NAME to the same database.
"""

import os
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from dosimeter.repository.migrate import migrate_up

DEFAULT_URL = "postgresql+psycopg://dosimeter:dosimeter_local_dev@localhost:55432/dosimeter"


def _url() -> str:
    return os.environ.get("DOSIMETER_TEST_URL", DEFAULT_URL)


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    engine = create_engine(_url(), connect_args={"connect_timeout": 3})
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as error:
        engine.dispose()
        pytest.skip(f"no database at {_url().rsplit('@', 1)[-1]}: {error}")

    yield engine
    engine.dispose()


@pytest.fixture
def db(engine: Engine) -> Iterator[Session]:
    """A clean schema with every migration applied."""

    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))

    session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        migrate_up(session)
        yield session
    finally:
        session.rollback()
        session.close()
