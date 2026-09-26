"""Builds the SQLAlchemy engine and hands out sessions. Nothing outside this
package talks to Postgres."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager

from sqlalchemy import URL, Engine, create_engine, event
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from dosimeter.config.settings import DatabaseSettings, get_database_settings
from dosimeter.errors import ConfigurationError, ExternalServiceError

TokenProvider = Callable[[], str]


def database_url(settings: DatabaseSettings, password: str | None = None) -> URL:
    return URL.create(
        "postgresql+psycopg",
        username=settings.user,
        password=password,
        host=settings.host,
        port=settings.port,
        database=settings.name,
        query={"sslmode": settings.sslmode},
    )


def build_engine(
    settings: DatabaseSettings | None = None,
    token_provider: TokenProvider | None = None,
) -> Engine:
    """
    An engine for the local path (password from typed config) or the deployed
    path (a fresh IAM token per connection, fetched through the provider).
    """

    resolved = settings or get_database_settings()

    if resolved.use_iam_auth:
        if token_provider is None:
            raise ConfigurationError(
                "IAM database authentication is on, so a token provider is required",
                field="DOSIMETER_DB_USE_IAM_AUTH",
            )
        engine = create_engine(
            database_url(resolved),
            pool_pre_ping=True,
            connect_args={"connect_timeout": resolved.connect_timeout_seconds},
        )

        @event.listens_for(engine, "do_connect")
        def _use_a_fresh_token(dialect, connection_record, cargs, cparams):  # noqa: ANN001
            cparams["password"] = token_provider()
            return None

        return engine

    if resolved.password is None:
        raise ConfigurationError("a database password is required", field="DOSIMETER_DB_PASSWORD")

    return create_engine(
        database_url(resolved, resolved.password.get_secret_value()),
        pool_pre_ping=True,
        connect_args={"connect_timeout": resolved.connect_timeout_seconds},
    )


def conn_string(
    settings: DatabaseSettings | None = None,
    token_provider: TokenProvider | None = None,
) -> str:
    """A psycopg connection string, for libraries that take one (the checkpointer)."""

    resolved = settings or get_database_settings()
    password = _password(resolved, token_provider)
    return database_url(resolved, password).render_as_string(hide_password=False).replace(
        "postgresql+psycopg://", "postgresql://", 1
    )


def _password(settings: DatabaseSettings, token_provider: TokenProvider | None) -> str:
    if settings.use_iam_auth:
        if token_provider is None:
            raise ConfigurationError(
                "IAM database authentication is on, so a token provider is required",
                field="DOSIMETER_DB_USE_IAM_AUTH",
            )
        return token_provider()

    if settings.password is None:
        raise ConfigurationError("a database password is required", field="DOSIMETER_DB_PASSWORD")
    return settings.password.get_secret_value()


@contextmanager
def session_scope(
    settings: DatabaseSettings | None = None,
    token_provider: TokenProvider | None = None,
    engine: Engine | None = None,
) -> Iterator[Session]:
    """One session, committed on success and rolled back on failure."""

    owned = engine is None
    resolved_engine = engine or build_engine(settings, token_provider)
    factory = sessionmaker(bind=resolved_engine, expire_on_commit=False)

    session = factory()
    try:
        yield session
        session.commit()
    except SQLAlchemyError as error:
        session.rollback()
        raise ExternalServiceError("database call failed") from error
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        if owned:
            resolved_engine.dispose()
