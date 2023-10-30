from __future__ import annotations

from typing import TYPE_CHECKING, cast

from sqlalchemy import Column, Engine, engine_from_config, pool

from advanced_alchemy.base import orm_registry
from alembic import context
from alembic.autogenerate import rewriter
from alembic.operations import ops

if TYPE_CHECKING:
    from sqlalchemy.engine import Connection

    from advanced_alchemy.alembic.commands import AlembicCommandConfig
    from alembic.runtime.environment import EnvironmentContext

__all__ = ["do_run_migrations", "run_migrations_offline", "run_migrations_online"]


# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config: AlembicCommandConfig = context.config  # type: ignore  # noqa: PGH003


# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = orm_registry.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# ... etc.

writer = rewriter.Rewriter()


@writer.rewrites(ops.CreateTableOp)
def order_columns(
    context: EnvironmentContext,  # noqa: ARG001
    revision: tuple[str, ...],  # noqa: ARG001
    op: ops.CreateTableOp,
) -> ops.CreateTableOp:
    """Orders ID first and the audit columns at the end."""
    special_names = {"id": -100, "sa_orm_sentinel": 3001, "created_at": 3002, "updated_at": 3003}
    cols_by_key = [
        (
            special_names.get(col.key, index) if isinstance(col, Column) else 2000,
            col.copy(),  # type: ignore[attr-defined]
        )
        for index, col in enumerate(op.columns)
    ]
    columns = [col for _, col in sorted(cols_by_key, key=lambda entry: entry[0])]
    return ops.CreateTableOp(
        op.table_name,
        columns,
        schema=op.schema,
        # TODO: Remove when https://github.com/sqlalchemy/alembic/issues/1193 is fixed  # noqa: FIX002
        _namespace_metadata=op._namespace_metadata,  # noqa: SLF001
        **op.kw,
    )


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.
    """
    context.configure(
        url=config.db_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=config.compare_type,
        version_table=config.version_table_name,
        version_table_pk=config.version_table_pk,
        user_module_prefix=config.user_module_prefix,
        render_as_batch=config.render_as_batch,
        process_revision_directives=writer,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Run migrations."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=config.compare_type,
        version_table=config.version_table_name,
        version_table_pk=config.version_table_pk,
        user_module_prefix=config.user_module_prefix,
        render_as_batch=config.render_as_batch,
        process_revision_directives=writer,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine and associate a
    connection with the context.
    """
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = config.db_url
    connectable = cast(
        "Engine",
        config.engine
        or engine_from_config(
            configuration,
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
            future=True,
        ),
    )
    if connectable is None:
        msg = "Could not get engine from config.  Please ensure your `alembic.ini` according to the official Alembic documentation."
        raise RuntimeError(
            msg,
        )

    with connectable.connect() as connection:
        do_run_migrations(connection=connection)

    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
