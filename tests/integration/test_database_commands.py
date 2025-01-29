from __future__ import annotations

from pathlib import Path
from typing import AsyncGenerator, Generator, cast

import pytest
from pytest import FixtureRequest
from sqlalchemy import Engine, NullPool, create_engine, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker

from advanced_alchemy import base
from advanced_alchemy.extensions.litestar import SQLAlchemyAsyncConfig, SQLAlchemySyncConfig
from advanced_alchemy.utils.databases import create_database, drop_database

pytestmark = [
    pytest.mark.integration,
]


@pytest.fixture()
def sqlite_engine_cd(tmp_path: Path) -> Generator[Engine, None, None]:
    """SQLite engine for end-to-end testing.

    Returns:
        Async SQLAlchemy engine instance.
    """
    engine = create_engine(f"sqlite:///{tmp_path}/test-cd.db", poolclass=NullPool)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture()
async def aiosqlite_engine_cd(tmp_path: Path) -> AsyncGenerator[AsyncEngine, None]:
    """SQLite engine for end-to-end testing.

    Returns:
        Async SQLAlchemy engine instance.
    """
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/test-cd-async.db", poolclass=NullPool)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture(
    params=[
        pytest.param(
            "sqlite_engine_cd",
            marks=[
                pytest.mark.sqlite,
                pytest.mark.integration,
            ],
        )
    ]
)
def sync_sqlalchemy_config(request: FixtureRequest) -> Generator[SQLAlchemySyncConfig, None, None]:
    engine = cast(Engine, request.getfixturevalue(request.param))
    orm_registry = base.create_registry()
    yield SQLAlchemySyncConfig(
        engine_instance=engine,
        session_maker=sessionmaker(bind=engine, expire_on_commit=False),
        metadata=orm_registry.metadata,
    )


async def test_create_and_drop_sqlite_sync(sqlite_engine_cd: Engine, tmp_path: Path) -> None:
    orm_registry = base.create_registry()
    cfg = SQLAlchemySyncConfig(
        engine_instance=sqlite_engine_cd,
        session_maker=sessionmaker(bind=sqlite_engine_cd, expire_on_commit=False),
        metadata=orm_registry.metadata,
    )
    file_path = f"{tmp_path}/test-cd.db"
    assert not Path(f"{tmp_path}/test-cd.db").exists()
    try:
        await create_database(cfg)
        assert Path(file_path).exists()
        with cfg.get_session() as sess:
            result = sess.execute(select(text("1")))
            assert result.scalar_one() == 1
        await drop_database(cfg)
        assert not Path(file_path).exists()
    finally:
        # always clean up
        if Path(file_path).exists():
            Path(file_path).unlink()


async def test_create_and_drop_sqlite_async(aiosqlite_engine_cd: AsyncEngine, tmp_path: Path) -> None:
    orm_registry = base.create_registry()
    cfg = SQLAlchemyAsyncConfig(
        engine_instance=aiosqlite_engine_cd,
        session_maker=async_sessionmaker(bind=aiosqlite_engine_cd, expire_on_commit=False),
        metadata=orm_registry.metadata,
    )
    file_path = f"{tmp_path}/test-cd-async.db"
    assert not Path(file_path).exists()
    try:
        await create_database(cfg)
        assert Path(file_path).exists()
        async with cfg.get_session() as sess:
            result = await sess.execute(select(text("1")))
            assert result.scalar_one() == 1
        await drop_database(cfg)
        assert not Path(file_path).exists()
    finally:
        # always clean up
        if Path(file_path).exists():
            Path(file_path).unlink()
