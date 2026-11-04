"""Alembic environment. Reads the database URL from application settings."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection

from app.core.config import get_settings
from app.db import models  # noqa: F401  (registers every table on Base.metadata)
from app.db.models import Base
from app.db.session import build_engine

config = context.config
if config.config_file_name is not None:
    # Keep loggers that exist already; migrations run in-process in tests.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _include_object(
    obj: object, name: str | None, type_: str, reflected: bool, compare_to: object | None
) -> bool:
    # Supabase and extensions may create their own tables; only manage ours.
    return not (type_ == "table" and reflected and compare_to is None)


def _configure(connection: Connection | None = None, url: str | None = None) -> None:
    context.configure(
        connection=connection,
        url=url,
        target_metadata=target_metadata,
        include_object=_include_object,
        compare_type=True,
        literal_binds=connection is None,
        dialect_opts={"paramstyle": "named"} if connection is None else {},
    )


def run_migrations_offline() -> None:
    _configure(url=get_settings().database_url.get_secret_value())
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:  # tests pass an open connection
        _configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()
        return

    engine = build_engine(
        get_settings().database_url.get_secret_value(), pool_size=1, max_overflow=0
    )
    try:
        with engine.connect() as conn:
            _configure(connection=conn)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
