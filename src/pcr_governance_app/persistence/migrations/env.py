from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection

from pcr_governance_app.persistence import models  # noqa: F401 -- registers tables on Base.metadata
from pcr_governance_app.persistence.base import Base
from pcr_governance_app.persistence.session import create_database_engine
from pcr_governance_app.web.services import get_database_url

# Alembic Config object, giving access to values within alembic.ini.
config = context.config

# Interpret the config file for Python logging, unless invoked programmatically
# without one configured.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Autogenerate support: compare against the same metadata the app writes with.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations without a live DB connection, emitting SQL to stdout."""
    url = get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=url.startswith("sqlite"),
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live DB connection."""
    engine = create_database_engine(get_database_url())

    with engine.connect() as connection:
        _configure_and_run(connection)

    engine.dispose()


def _configure_and_run(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=connection.engine.dialect.name == "sqlite",
    )

    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
