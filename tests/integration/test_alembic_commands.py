from __future__ import annotations

import sqlite3
from collections.abc import Generator
from io import StringIO
from operator import itemgetter
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from _pytest.monkeypatch import MonkeyPatch
from alembic.util.exc import CommandError
from anyio import Path as AsyncPath
from pytest import CaptureFixture, FixtureRequest
from pytest_lazy_fixtures import lf
from sqlalchemy import Engine, ForeignKey, String, event
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from advanced_alchemy import base, mixins
from advanced_alchemy.alembic import commands
from advanced_alchemy.alembic.utils import drop_all, dump_tables
from advanced_alchemy.config.asyncio import AlembicAsyncConfig
from advanced_alchemy.config.sync import AlembicSyncConfig
from advanced_alchemy.extensions.litestar import SQLAlchemyAsyncConfig, SQLAlchemySyncConfig
from advanced_alchemy.utils.fixtures import open_fixture_sync
from advanced_alchemy.utils.sync_tools import async_
from tests.helpers import maybe_async

pytestmark = [
    pytest.mark.integration,
]


@pytest.fixture(
    params=[
        pytest.param(
            "sqlite_engine",
            marks=[
                pytest.mark.sqlite,
                pytest.mark.integration,
                pytest.mark.xdist_group("sqlite"),
            ],
        ),
        pytest.param(
            "duckdb_engine",
            marks=[
                pytest.mark.duckdb,
                pytest.mark.integration,
                pytest.mark.xdist_group("duckdb"),
            ],
        ),
        pytest.param(
            "oracle18c_engine",
            marks=[
                pytest.mark.oracledb_sync,
                pytest.mark.integration,
                pytest.mark.xdist_group("oracle18"),
            ],
        ),
        pytest.param(
            "oracle23ai_engine",
            marks=[
                pytest.mark.oracledb_sync,
                pytest.mark.integration,
                pytest.mark.xdist_group("oracle23"),
            ],
        ),
        pytest.param(
            "psycopg_engine",
            marks=[
                pytest.mark.psycopg_sync,
                pytest.mark.integration,
                pytest.mark.xdist_group("postgres"),
            ],
        ),
        pytest.param(
            "spanner_engine",
            marks=[
                pytest.mark.spanner,
                pytest.mark.integration,
                pytest.mark.xdist_group("spanner"),
            ],
        ),
        pytest.param(
            "mssql_engine",
            marks=[
                pytest.mark.mssql_sync,
                pytest.mark.integration,
                pytest.mark.xdist_group("mssql"),
            ],
        ),
        pytest.param(
            "cockroachdb_engine",
            marks=[
                pytest.mark.cockroachdb_sync,
                pytest.mark.integration,
                pytest.mark.xdist_group("cockroachdb"),
            ],
        ),
    ],
)
def sync_sqlalchemy_config(request: FixtureRequest) -> Generator[SQLAlchemySyncConfig, None, None]:
    engine = cast(Engine, request.getfixturevalue(request.param))
    orm_registry = base.create_registry()
    yield SQLAlchemySyncConfig(
        engine_instance=engine,
        session_maker=sessionmaker(bind=engine, expire_on_commit=False),
        metadata=orm_registry.metadata,
    )


@pytest.fixture(
    params=[
        pytest.param(
            "aiosqlite_engine",
            marks=[
                pytest.mark.aiosqlite,
                pytest.mark.integration,
                pytest.mark.xdist_group("sqlite"),
            ],
        ),
        pytest.param(
            "asyncmy_engine",
            marks=[
                pytest.mark.asyncmy,
                pytest.mark.integration,
                pytest.mark.xdist_group("mysql"),
            ],
        ),
        pytest.param(
            "asyncpg_engine",
            marks=[
                pytest.mark.asyncpg,
                pytest.mark.integration,
                pytest.mark.xdist_group("postgres"),
            ],
        ),
        pytest.param(
            "psycopg_async_engine",
            marks=[
                pytest.mark.psycopg_async,
                pytest.mark.integration,
                pytest.mark.xdist_group("postgres"),
            ],
        ),
        pytest.param(
            "cockroachdb_async_engine",
            marks=[
                pytest.mark.cockroachdb_async,
                pytest.mark.integration,
                pytest.mark.xdist_group("cockroachdb"),
            ],
        ),
        pytest.param(
            "oracle18c_async_engine",
            marks=[
                pytest.mark.oracledb_async,
                pytest.mark.integration,
                pytest.mark.xdist_group("oracle18"),
            ],
        ),
        pytest.param(
            "oracle23ai_async_engine",
            marks=[
                pytest.mark.oracledb_async,
                pytest.mark.integration,
                pytest.mark.xdist_group("oracle23"),
            ],
        ),
        pytest.param(
            "mssql_async_engine",
            marks=[
                pytest.mark.mssql_async,
                pytest.mark.integration,
                pytest.mark.xdist_group("mssql"),
            ],
        ),
    ],
)
def async_sqlalchemy_config(
    request: FixtureRequest,
) -> Generator[SQLAlchemyAsyncConfig, None, None]:
    async_engine = cast(AsyncEngine, request.getfixturevalue(request.param))
    orm_registry = base.create_registry()
    yield SQLAlchemyAsyncConfig(
        engine_instance=async_engine,
        session_maker=async_sessionmaker(bind=async_engine, expire_on_commit=False),
        metadata=orm_registry.metadata,
    )


@pytest.fixture(
    params=[lf("sync_sqlalchemy_config"), lf("async_sqlalchemy_config")],
    ids=["sync", "async"],
)
def any_config(request: FixtureRequest) -> Generator[SQLAlchemySyncConfig | SQLAlchemyAsyncConfig, None, None]:
    """Return a config for the current test."""
    if isinstance(request.param, SQLAlchemyAsyncConfig):
        request.getfixturevalue("async_sqlalchemy_config")
    else:
        request.getfixturevalue("sync_sqlalchemy_config")
    if request.param.metadata is not None:
        base.metadata_registry.set(request.param.bind_key, request.param.metadata)
    yield request.param  # type: ignore[no-any-return]


@pytest.fixture()
def alembic_commands(
    any_config: SQLAlchemySyncConfig | SQLAlchemyAsyncConfig,
) -> Generator[commands.AlembicCommands, None, None]:
    if any_config.metadata is not None:
        base.metadata_registry.set(any_config.bind_key, any_config.metadata)
    yield commands.AlembicCommands(
        sqlalchemy_config=any_config,
    )


@pytest.fixture()
def tmp_project_dir(monkeypatch: MonkeyPatch, tmp_path: Path) -> Generator[Path, None, None]:
    path = tmp_path / "project_dir"
    path.mkdir(exist_ok=True)
    monkeypatch.chdir(path)
    yield path


@pytest.mark.unit
def test_alembic_command_config_propagates_alembic_options() -> None:
    sqlalchemy_config = SQLAlchemySyncConfig(
        connection_string="sqlite://",
        bind_key="analytics",
        alembic_config=AlembicSyncConfig(
            version_table_name="custom_alembic_versions",
            version_table_schema="custom_schema",
            render_as_batch=False,
            compare_type=True,
            user_module_prefix="sqlalchemy.",
        ),
    )

    command_config = commands.AlembicCommands(sqlalchemy_config).config

    assert command_config.bind_key == "analytics"
    assert command_config.version_table_name == "custom_alembic_versions"
    assert command_config.version_table_schema == "custom_schema"
    assert command_config.render_as_batch is False
    assert command_config.compare_type is True
    assert command_config.user_module_prefix == "sqlalchemy."


@pytest.mark.sqlite
@pytest.mark.xdist_group("sqlite")
@pytest.mark.parametrize("async_mode", [False, True], ids=["sync", "async"])
@pytest.mark.parametrize("offline", [False, True], ids=["online", "offline"])
@pytest.mark.parametrize("schema", [None, "custom_schema"], ids=["default_schema", "custom_schema"])
def test_alembic_version_table_schema(
    tmp_project_dir: Path, async_mode: bool, offline: bool, schema: str | None
) -> None:
    database = tmp_project_dir / "main.db"
    schema_database = tmp_project_dir / "custom.db"
    sqlalchemy_config: SQLAlchemySyncConfig | SQLAlchemyAsyncConfig
    if async_mode:
        sqlalchemy_config = SQLAlchemyAsyncConfig(
            connection_string=f"sqlite+aiosqlite:///{database}",
            alembic_config=AlembicAsyncConfig(version_table_schema=schema),
        )
    else:
        sqlalchemy_config = SQLAlchemySyncConfig(
            connection_string=f"sqlite:///{database}",
            alembic_config=AlembicSyncConfig(version_table_schema=schema),
        )
    engine = sqlalchemy_config.get_engine()
    if schema is not None:
        sync_engine = engine.sync_engine if isinstance(engine, AsyncEngine) else engine

        @event.listens_for(sync_engine, "connect")
        def attach_schema(dbapi_connection: Any, connection_record: Any) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("ATTACH DATABASE ? AS custom_schema", (str(schema_database),))
            cursor.close()

    migration_commands = commands.AlembicCommands(sqlalchemy_config)
    migration_commands.init(directory="migrations")
    migration_commands.revision(message="version table schema", rev_id="schema_test")
    output = StringIO()
    migration_commands.config.output_buffer = output
    migration_commands.upgrade(sql=offline)

    if offline:
        table = "custom_schema.alembic_versions" if schema else "alembic_versions"
        assert f"CREATE TABLE {table}" in output.getvalue()
        assert f"INSERT INTO {table}" in output.getvalue()
    else:
        with sqlite3.connect(schema_database if schema else database) as connection:
            assert connection.execute("SELECT version_num FROM alembic_versions").fetchall() == [("schema_test",)]
        if schema is not None:
            with sqlite3.connect(database) as connection:
                assert (
                    connection.execute("SELECT name FROM sqlite_master WHERE name = 'alembic_versions'").fetchall()
                    == []
                )


async def test_alembic_init(alembic_commands: commands.AlembicCommands, tmp_project_dir: Path) -> None:
    alembic_commands.init(directory=f"{tmp_project_dir}/migrations/")
    expected_dirs = [f"{tmp_project_dir}/migrations/", f"{tmp_project_dir}/migrations/versions"]
    expected_files = [f"{tmp_project_dir}/migrations/env.py", f"{tmp_project_dir}/migrations/script.py.mako"]
    for dir in expected_dirs:
        assert await async_(Path(dir).is_dir)()
    for file in expected_files:
        assert await async_(Path(file).is_file)()


async def test_alembic_init_renders_postgres_enum_import(
    alembic_commands: commands.AlembicCommands, tmp_project_dir: Path
) -> None:
    """The generated ``env.py`` should opt into PostgreSQL enum autogenerate support.

    See https://github.com/litestar-org/advanced-alchemy/issues/492.
    """
    alembic_commands.init(directory=f"{tmp_project_dir}/migrations/")
    env_contents = await async_(Path(f"{tmp_project_dir}/migrations/env.py").read_text)()
    assert 'importlib.import_module("alembic_postgresql_enum")' in env_contents
    assert 'if config.db_url.startswith("postgresql"):' in env_contents
    assert "contextlib.suppress(ModuleNotFoundError)" in env_contents


async def test_alembic_init_already(alembic_commands: commands.AlembicCommands, tmp_project_dir: Path) -> None:
    alembic_commands.init(directory=f"{tmp_project_dir}/migrations/")
    expected_dirs = [f"{tmp_project_dir}/migrations/", f"{tmp_project_dir}/migrations/versions"]
    expected_files = [f"{tmp_project_dir}/migrations/env.py", f"{tmp_project_dir}/migrations/script.py.mako"]
    for dir in expected_dirs:
        assert await async_(Path(dir).is_dir)()
    for file in expected_files:
        assert await async_(Path(file).is_file)()
    with pytest.raises(CommandError):
        alembic_commands.init(directory=f"{tmp_project_dir}/migrations/")


async def test_drop_all(
    alembic_commands: commands.AlembicCommands,
    any_config: SQLAlchemySyncConfig | SQLAlchemyAsyncConfig,
    capfd: CaptureFixture[str],
) -> None:
    from examples.litestar.litestar_repo_only import app

    await maybe_async(any_config.create_all_metadata(app))
    if isinstance(any_config, SQLAlchemySyncConfig):
        assert any_config.metadata
        any_config.metadata.create_all(any_config.get_engine())
    else:
        async with any_config.get_engine().begin() as conn:
            assert any_config.metadata
            await conn.run_sync(any_config.metadata.create_all)

    await drop_all(
        alembic_commands.config.engine,
        alembic_commands.config.version_table_name,
        base.metadata_registry.get(alembic_commands.config.bind_key),
    )
    result = capfd.readouterr()
    assert "Successfully dropped all objects" in result.out


class _DumpBase(base.CommonTableAttributes, mixins.UUIDPrimaryKey, DeclarativeBase):
    registry = base.create_registry()


class DumpAuthorModel(_DumpBase):
    name: Mapped[str] = mapped_column(String(10))
    books: Mapped[list[DumpBookModel]] = relationship(lazy="joined", viewonly=True)


class DumpBookModel(_DumpBase):
    title: Mapped[str] = mapped_column(String(10))
    author_id: Mapped[UUID] = mapped_column(ForeignKey("dump_author_model.id"))
    author: Mapped[DumpAuthorModel] = relationship(lazy="joined", innerjoin=True, viewonly=True)


_AUTHORS = [
    {"id": "00000000-0000-0000-0000-000000000001", "name": "alice"},
    {"id": "00000000-0000-0000-0000-000000000002", "name": "bob"},
    {"id": "00000000-0000-0000-0000-000000000003", "name": "carol"},
]
_BOOKS = [
    {
        "id": "00000000-0000-0000-0000-000000000011",
        "title": "red",
        "author_id": "00000000-0000-0000-0000-000000000001",
    },
    {
        "id": "00000000-0000-0000-0000-000000000012",
        "title": "green",
        "author_id": "00000000-0000-0000-0000-000000000001",
    },
    {
        "id": "00000000-0000-0000-0000-000000000013",
        "title": "blue",
        "author_id": "00000000-0000-0000-0000-000000000002",
    },
]


async def _seed_dump_models(config: SQLAlchemySyncConfig | SQLAlchemyAsyncConfig) -> None:
    authors = [DumpAuthorModel(id=UUID(row["id"]), name=row["name"]) for row in _AUTHORS]
    books = [DumpBookModel(id=UUID(row["id"]), title=row["title"], author_id=UUID(row["author_id"])) for row in _BOOKS]
    if isinstance(config, SQLAlchemySyncConfig):
        engine = config.get_engine()
        _DumpBase.metadata.drop_all(engine)
        _DumpBase.metadata.create_all(engine)
        with config.get_session() as session:
            session.add_all(authors)
            session.flush()
            session.add_all(books)
            session.commit()
    else:
        async_engine = config.get_engine()
        async with async_engine.begin() as conn:
            await conn.run_sync(_DumpBase.metadata.drop_all)
            await conn.run_sync(_DumpBase.metadata.create_all)
        async with config.get_session() as session:
            session.add_all(authors)
            await session.flush()
            session.add_all(books)
            await session.commit()


async def _drop_dump_models(config: SQLAlchemySyncConfig | SQLAlchemyAsyncConfig) -> None:
    if isinstance(config, SQLAlchemySyncConfig):
        _DumpBase.metadata.drop_all(config.get_engine())
    else:
        async with config.get_engine().begin() as conn:
            await conn.run_sync(_DumpBase.metadata.drop_all)


@pytest.fixture(
    params=[
        pytest.param(
            ("sqlite_engine", True),
            marks=[
                pytest.mark.sqlite,
                pytest.mark.integration,
                pytest.mark.xdist_group("sqlite"),
            ],
        ),
        pytest.param(
            ("aiosqlite_engine", True),
            marks=[
                pytest.mark.aiosqlite,
                pytest.mark.integration,
                pytest.mark.xdist_group("sqlite"),
            ],
        ),
        pytest.param(
            ("aiosqlite_engine", False),
            marks=[
                pytest.mark.aiosqlite,
                pytest.mark.integration,
                pytest.mark.xdist_group("sqlite"),
            ],
        ),
    ],
    ids=["sqlite", "aiosqlite-stream", "aiosqlite-buffered"],
)
def sqlite_dump_config(
    request: FixtureRequest, monkeypatch: MonkeyPatch
) -> Generator[SQLAlchemySyncConfig | SQLAlchemyAsyncConfig, None, None]:
    engine_fixture, supports_cursors = cast("tuple[str, bool]", request.param)
    engine = request.getfixturevalue(engine_fixture)
    orm_registry = base.create_registry()
    if isinstance(engine, AsyncEngine):
        if not supports_cursors:
            monkeypatch.setattr(engine.sync_engine.dialect, "supports_server_side_cursors", False)
        yield SQLAlchemyAsyncConfig(
            engine_instance=engine,
            session_maker=async_sessionmaker(bind=engine, expire_on_commit=False),
            metadata=orm_registry.metadata,
        )
    else:
        yield SQLAlchemySyncConfig(
            engine_instance=engine,
            session_maker=sessionmaker(bind=engine, expire_on_commit=False),
            metadata=orm_registry.metadata,
        )


async def test_dump_tables(
    any_config: SQLAlchemySyncConfig | SQLAlchemyAsyncConfig,
    capfd: CaptureFixture[str],
    tmp_project_dir: Path,
) -> None:
    await _seed_dump_models(any_config)
    try:
        await dump_tables(
            tmp_project_dir,
            any_config.get_session(),
            [DumpAuthorModel, DumpBookModel],
        )
    finally:
        await _drop_dump_models(any_config)
    result = capfd.readouterr()
    assert "Dumping table 'dump_author_model'" in result.out
    assert "Dumping table 'dump_book_model'" in result.out
    assert f"Wrote {tmp_project_dir / 'dump_author_model.json'}" in result.out
    assert sorted([p.name async for p in AsyncPath(tmp_project_dir).iterdir()]) == [
        "dump_author_model.json",
        "dump_book_model.json",
    ]
    assert sorted(open_fixture_sync(tmp_project_dir, "dump_author_model"), key=itemgetter("id")) == _AUTHORS
    assert sorted(open_fixture_sync(tmp_project_dir, "dump_book_model"), key=itemgetter("id")) == _BOOKS


@pytest.mark.parametrize(
    ("dump_kwargs", "author_files", "book_files"),
    [
        ({}, ["dump_author_model.json"], ["dump_book_model.json"]),
        ({"file_format": "jsonl"}, ["dump_author_model.jsonl"], ["dump_book_model.jsonl"]),
        (
            {"file_format": "jsonl", "compression": "gzip"},
            ["dump_author_model.jsonl.gz"],
            ["dump_book_model.jsonl.gz"],
        ),
        (
            {"file_format": "csv", "compression": "zip"},
            ["dump_author_model.csv.zip"],
            ["dump_book_model.csv.zip"],
        ),
        (
            {"compression": "gzip", "max_records": 2},
            ["dump_author_model.001.json.gz", "dump_author_model.002.json.gz"],
            ["dump_book_model.001.json.gz", "dump_book_model.002.json.gz"],
        ),
        (
            {"file_format": "jsonl", "max_records": 1, "batch_size": 1},
            ["dump_author_model.001.jsonl", "dump_author_model.002.jsonl", "dump_author_model.003.jsonl"],
            ["dump_book_model.001.jsonl", "dump_book_model.002.jsonl", "dump_book_model.003.jsonl"],
        ),
        (
            {"file_format": "jsonl", "max_bytes": 200},
            ["dump_author_model.001.jsonl", "dump_author_model.002.jsonl"],
            ["dump_book_model.001.jsonl", "dump_book_model.002.jsonl", "dump_book_model.003.jsonl"],
        ),
    ],
    ids=[
        "default-json",
        "jsonl",
        "jsonl-gzip",
        "csv-zip",
        "json-gzip-max-records-2",
        "jsonl-max-records-1-batch-1",
        "jsonl-max-bytes-200",
    ],
)
async def test_dump_tables_fixture_options(
    sqlite_dump_config: SQLAlchemySyncConfig | SQLAlchemyAsyncConfig,
    capfd: CaptureFixture[str],
    tmp_project_dir: Path,
    dump_kwargs: dict[str, Any],
    author_files: list[str],
    book_files: list[str],
) -> None:
    await _seed_dump_models(sqlite_dump_config)
    try:
        await dump_tables(
            tmp_project_dir,
            sqlite_dump_config.get_session(),
            [DumpAuthorModel, DumpBookModel],
            **dump_kwargs,
        )
    finally:
        await _drop_dump_models(sqlite_dump_config)
    result = capfd.readouterr()
    expected_files = author_files + book_files
    assert sorted([p.name async for p in AsyncPath(tmp_project_dir).iterdir()]) == sorted(expected_files)
    assert all(f"Wrote {tmp_project_dir / name}" in result.out for name in expected_files)
    assert open_fixture_sync(tmp_project_dir, "dump_author_model") == _AUTHORS
    assert open_fixture_sync(tmp_project_dir, "dump_book_model") == _BOOKS
    if not dump_kwargs:
        author_text = await AsyncPath(tmp_project_dir / "dump_author_model.json").read_text(encoding="utf-8")
        assert author_text.startswith("[\n{")
        assert author_text.endswith("}\n]\n")
        assert author_text.count(",\n") == 2
    if "max_bytes" in dump_kwargs:
        assert all(
            [
                (await AsyncPath(tmp_project_dir / name).stat()).st_size <= dump_kwargs["max_bytes"]
                for name in expected_files
            ]
        )


@pytest.mark.unit
async def test_dump_tables_rejects_invalid_batch_size(tmp_project_dir: Path) -> None:
    out_dir = tmp_project_dir / "out"
    with pytest.raises(ValueError, match="batch_size must be at least 1, got 0"):
        await dump_tables(out_dir, MagicMock(), [], batch_size=0)
    assert not out_dir.exists()


"""
async def test_alembic_revision(alembic_commands: commands.AlembicCommands, tmp_project_dir: Path) -> None:
    alembic_commands.init(directory=f"{tmp_project_dir}/migrations/")
    alembic_commands.revision(message="test", autogenerate=True)


async def test_alembic_upgrade(alembic_commands: commands.AlembicCommands, tmp_project_dir: Path) -> None:
    alembic_commands.init(directory=f"{tmp_project_dir}/migrations/")
    alembic_commands.revision(message="test", autogenerate=True)
    alembic_commands.upgrade(revision="head")
"""
