from __future__ import annotations

from typing import TYPE_CHECKING

from litestar.cli._utils import console
from sqlalchemy import Engine, MetaData, Table
from typing_extensions import TypeIs

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine


async def drop_all(engine: AsyncEngine | Engine, version_table_name: str, metadata: MetaData) -> None:
    def _is_sync(engine: Engine | AsyncEngine) -> TypeIs[Engine]:
        return isinstance(engine, Engine)

    def _drop_tables_sync(engine: Engine) -> None:
        console.rule("[bold red]Connecting to database backend.")
        with engine.begin() as db:
            console.rule("[bold red]Dropping the db", align="left")
            metadata.drop_all(db)
            console.rule("[bold red]Dropping the version table", align="left")
            Table(version_table_name, metadata).drop(db, checkfirst=True)
        console.rule("[bold yellow]Successfully dropped all objects", align="left")

    async def _drop_tables_async(engine: AsyncEngine) -> None:
        console.rule("[bold red]Connecting to database backend.", align="left")
        async with engine.begin() as db:
            console.rule("[bold red]Dropping the db", align="left")
            await db.run_sync(metadata.drop_all)
            console.rule("[bold red]Dropping the version table", align="left")
            await db.run_sync(Table(version_table_name, metadata).drop, checkfirst=True)
        console.rule("[bold yellow]Successfully dropped all objects", align="left")

    if _is_sync(engine):
        return _drop_tables_sync(engine)
    return await _drop_tables_async(engine)
