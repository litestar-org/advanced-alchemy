from contextlib import AbstractAsyncContextManager, AbstractContextManager
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional, Union

from sqlalchemy import Column, Engine, MetaData, String, Table, select
from sqlalchemy.orm import lazyload
from typing_extensions import TypeIs

from advanced_alchemy.base import model_to_dict
from advanced_alchemy.exceptions import MissingDependencyError
from advanced_alchemy.utils.fixtures import write_fixture_async, write_fixture_sync
from advanced_alchemy.utils.sync_tools import async_

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterable

    from sqlalchemy import Select
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
    from sqlalchemy.orm import DeclarativeBase, Session

    from advanced_alchemy.utils.fixtures import FixtureCompression, FixtureFormat

__all__ = ("drop_all", "dump_tables")


async def drop_all(engine: "Union[AsyncEngine, Engine]", version_table_name: str, metadata: MetaData) -> None:
    """Drop all tables in the database.

    Args:
        engine: The database engine.
        version_table_name: The name of the version table.
        metadata: The metadata object containing the tables to drop.

    Raises:
        MissingDependencyError: If the `rich` package is not installed.
    """
    try:
        from rich import get_console
    except ImportError as e:  # pragma: no cover
        msg = "rich"
        raise MissingDependencyError(msg, install_package="cli") from e

    console = get_console()

    def _is_sync(engine: "Union[Engine, AsyncEngine]") -> "TypeIs[Engine]":
        return isinstance(engine, Engine)

    def _drop_tables_sync(engine: Engine) -> None:
        console.rule("[bold red]Connecting to database backend.")
        with engine.begin() as db:
            console.rule("[bold red]Dropping the db", align="left")
            metadata.drop_all(db)
            console.rule("[bold red]Dropping the version table", align="left")
            # Create a properly defined Alembic version table with required column structure
            # Using a temporary metadata instance prevents modifying the shared metadata object
            temp_metadata = MetaData()
            alembic_version_table = Table(
                version_table_name,
                temp_metadata,
                Column("version_num", String(32), primary_key=True, nullable=False),
            )
            alembic_version_table.drop(db, checkfirst=True)
        console.rule("[bold yellow]Successfully dropped all objects", align="left")

    async def _drop_tables_async(engine: "AsyncEngine") -> None:
        console.rule("[bold red]Connecting to database backend.", align="left")
        async with engine.begin() as db:
            console.rule("[bold red]Dropping the db", align="left")
            await db.run_sync(metadata.drop_all)
            console.rule("[bold red]Dropping the version table", align="left")
            # Create a properly defined Alembic version table with required column structure
            # Using a temporary metadata instance prevents modifying the shared metadata object
            temp_metadata = MetaData()
            alembic_version_table = Table(
                version_table_name,
                temp_metadata,
                Column("version_num", String(32), primary_key=True, nullable=False),
            )
            await db.run_sync(alembic_version_table.drop, checkfirst=True)
        console.rule("[bold yellow]Successfully dropped all objects", align="left")

    if _is_sync(engine):
        return _drop_tables_sync(engine)
    return await _drop_tables_async(engine)


async def dump_tables(
    dump_dir: Path,
    session: "Union[AbstractContextManager[Session], AbstractAsyncContextManager[AsyncSession]]",
    models: "list[type[DeclarativeBase]]",
    *,
    file_format: "FixtureFormat" = "json",
    compression: "Optional[FixtureCompression]" = None,
    max_bytes: "Optional[int]" = None,
    max_records: "Optional[int]" = None,
    batch_size: int = 1000,
) -> None:
    """Stream every row of each model into fixture files under ``dump_dir``.

    Rows are queried in primary-key order with ``lazyload("*")`` and
    ``yield_per=batch_size`` so joined collection eager loaders remain
    compatible with ``yield_per`` and do not trigger extra queries while a
    server-side cursor is open. Async dialects without server-side cursor
    support are read through buffered :meth:`AsyncSession.scalars`.

    Args:
        dump_dir: Directory where fixture files are written.
        session: Sync or async SQLAlchemy session context manager.
        models: Sequence of declarative model classes to dump.
        file_format: Output format (``"json"``, ``"jsonl"``, or ``"csv"``).
        compression: Optional compression (``"gzip"``, ``"zip"``, or ``None``).
        max_bytes: Optional maximum on-disk byte size per shard.
        max_records: Optional maximum record count per shard.
        batch_size: Number of rows fetched and buffered per streaming batch.

    Raises:
        ValueError: If ``batch_size`` is less than 1, or the writer rejects an argument.
        MissingDependencyError: If the ``rich`` package is not installed.
    """
    if batch_size < 1:
        msg = f"batch_size must be at least 1, got {batch_size}"
        raise ValueError(msg)

    try:
        from rich import get_console
    except ImportError as e:  # pragma: no cover
        msg = "rich"
        raise MissingDependencyError(msg, install_package="cli") from e

    console = get_console()

    def _statement(model: "type[DeclarativeBase]") -> "Select[tuple[DeclarativeBase]]":
        return (
            select(model)
            .options(lazyload("*"))
            .order_by(*model.__mapper__.primary_key)
            .execution_options(yield_per=batch_size)
        )

    def _announce(model: "type[DeclarativeBase]") -> None:
        console.rule(
            f"[yellow bold]Dumping table '{model.__tablename__}' to '{dump_dir}'",
            style="yellow",
            align="left",
        )

    def _report(paths: "list[Path]") -> None:
        for path in paths:
            console.print(
                f"Wrote {path}",
                style="green",
                markup=False,
                highlight=False,
                soft_wrap=True,
            )

    def _is_sync(
        session: "Union[AbstractAsyncContextManager[AsyncSession], AbstractContextManager[Session]]",
    ) -> "TypeIs[AbstractContextManager[Session]]":
        return isinstance(session, AbstractContextManager)

    def _dump_table_sync(session: "AbstractContextManager[Session]") -> None:
        with session as _session:
            for model in models:
                _announce(model)
                rows = _session.execute(_statement(model)).scalars()
                _report(
                    write_fixture_sync(
                        dump_dir,
                        model.__tablename__,
                        (model_to_dict(row) for row in rows),
                        file_format=file_format,
                        compression=compression,
                        max_bytes=max_bytes,
                        max_records=max_records,
                    )
                )

    async def _dump_table_async(session: "AbstractAsyncContextManager[AsyncSession]") -> None:
        async with session as _session:
            for model in models:
                _announce(model)
                statement = _statement(model)
                records: Union[Iterable[dict[str, Any]], AsyncIterator[dict[str, Any]]]
                if _session.get_bind(mapper=model).dialect.supports_server_side_cursors:
                    streamed = await _session.stream_scalars(statement)
                    records = (model_to_dict(row) async for row in streamed)
                else:
                    buffered = await _session.scalars(statement)
                    records = (model_to_dict(row) for row in buffered)
                _report(
                    await write_fixture_async(
                        dump_dir,
                        model.__tablename__,
                        records,
                        file_format=file_format,
                        compression=compression,
                        max_bytes=max_bytes,
                        max_records=max_records,
                        batch_size=batch_size,
                    )
                )

    await async_(dump_dir.mkdir)(exist_ok=True)

    if _is_sync(session):
        return await async_(_dump_table_sync)(session)
    return await _dump_table_async(session)
