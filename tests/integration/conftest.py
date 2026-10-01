"""
Fixtures for the tests that need a real database.

They run against the compose database. Start it with:

    docker compose up -d

Set DOSIMETER_TEST_URL to point somewhere else. When nothing answers, these
tests skip, so a clone without Docker still runs the suite.

Every test drops and recreates the public schema of that database, so the
default is a separate dosimeter_test database, created if it is missing, and
never the dosimeter database the CLI uses. The app's DOSIMETER_DB_* settings
are pointed at the same test database for the whole run.
"""

import os
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, create_engine, make_url, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from dosimeter.config.settings import get_database_settings
from dosimeter.repository.migrate import migrate_up

DEFAULT_URL = "postgresql+psycopg://dosimeter:dosimeter_local_dev@localhost:55432/dosimeter_test"


def _url() -> str:
    return os.environ.get("DOSIMETER_TEST_URL", DEFAULT_URL)


def _create_database_if_missing(url: str) -> None:
    target = make_url(url)
    admin = create_engine(
        target.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        connect_args={"connect_timeout": 3},
    )
    try:
        with admin.connect() as connection:
            exists = connection.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": target.database}
            ).scalar()
            if not exists:
                connection.execute(text(f'CREATE DATABASE "{target.database}"'))
    finally:
        admin.dispose()


@pytest.fixture(scope="session", autouse=True)
def app_settings_point_at_the_test_database() -> Iterator[None]:
    """The checkpointer reads DOSIMETER_DB_*, so the whole run uses the test database too."""

    url = make_url(_url())
    overrides = {
        "DOSIMETER_DB_HOST": url.host or "localhost",
        "DOSIMETER_DB_PORT": str(url.port or 5432),
        "DOSIMETER_DB_NAME": url.database or "",
        "DOSIMETER_DB_USER": url.username or "",
        "DOSIMETER_DB_PASSWORD": url.password or "",
        "DOSIMETER_DB_USE_IAM_AUTH": "false",
        "DOSIMETER_DB_SSLMODE": "prefer",
    }
    saved = {name: os.environ.get(name) for name in overrides}
    os.environ.update(overrides)
    get_database_settings.cache_clear()
    yield
    for name, value in saved.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value
    get_database_settings.cache_clear()


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    try:
        _create_database_if_missing(_url())
    except SQLAlchemyError as error:
        pytest.skip(f"no database at {_url().rsplit('@', 1)[-1]}: {error}")

    # every test recreates the schema, so a statement psycopg prepared earlier would point at dropped tables
    engine = create_engine(_url(), connect_args={"connect_timeout": 3, "prepare_threshold": None})
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
