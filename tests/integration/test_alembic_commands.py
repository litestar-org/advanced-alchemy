from __future__ import annotations

import sqlite3
from collections.abc import Generator
from io import StringIO
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest
from _pytest.monkeypatch import MonkeyPatch
from alembic.util.exc import CommandError
from pytest import CaptureFixture, FixtureRequest
from pytest_lazy_fixtures import lf
from sqlalchemy import Engine, ForeignKey, String, event
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column, relationship, sessionmaker

from advanced_alchemy import base
from advanced_alchemy.alembic import commands
from advanced_alchemy.alembic.utils import drop_all, dump_tables
from advanced_alchemy.config.asyncio import AlembicAsyncConfig
from advanced_alchemy.config.sync import AlembicSyncConfig
from advanced_alchemy.extensions.litestar import SQLAlchemyAsyncConfig, SQLAlchemySyncConfig
from tests.fixtures.uuid import models as models_uuid
from tests.helpers import maybe_async

AuthorModel = type[models_uuid.UUIDAuthor]
RuleModel = type[models_uuid.UUIDRule]
ModelWithFetchedValue = type[models_uuid.UUIDModelWithFetchedValue]
ItemModel = type[models_uuid.UUIDItem]
TagModel = type[models_uuid.UUIDTag]

pytestmark = [
    pytest.mark.integration,
    pytest.mark.xdist_group("alembic_commands"),
]


@pytest.fixture(
    scope="session",
    params=[
        pytest.param(
            "sqlite_engine",
            marks=[
                pytest.mark.sqlite,
                pytest.mark.integration,
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
    scope="session",
    params=[
        pytest.param(
            "aiosqlite_engine",
            marks=[
                pytest.mark.aiosqlite,
                pytest.mark.integration,
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
    scope="session",
    params=[lf("sync_sqlalchemy_config"), lf("async_sqlalchemy_config")],
    ids=["sync", "async"],
)
def any_config(request: FixtureRequest) -> Generator[SQLAlchemySyncConfig | SQLAlchemyAsyncConfig, None, None]:
    """Return a session for the current session"""
    if isinstance(request.param, SQLAlchemyAsyncConfig):
        request.getfixturevalue("async_sqlalchemy_config")
    else:
        request.getfixturevalue("sync_sqlalchemy_config")
    yield request.param  # type: ignore[no-any-return]


@pytest.fixture()
def alembic_commands(
    any_config: SQLAlchemySyncConfig | SQLAlchemyAsyncConfig,
) -> Generator[commands.AlembicCommands, None, None]:
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
    from advanced_alchemy.utils.sync_tools import async_

    alembic_commands.init(directory=f"{tmp_project_dir}/migrations/")
    expected_dirs = [f"{tmp_project_dir}/migrations/", f"{tmp_project_dir}/migrations/versions"]
    expected_files = [f"{tmp_project_dir}/migrations/env.py", f"{tmp_project_dir}/migrations/script.py.mako"]
    for dir in expected_dirs:
        assert await async_(Path(dir).is_dir)()
    for file in expected_files:
        assert await async_(Path(file).is_file)()


async def test_alembic_init_already(alembic_commands: commands.AlembicCommands, tmp_project_dir: Path) -> None:
    from advanced_alchemy.utils.sync_tools import async_

    alembic_commands.init(directory=f"{tmp_project_dir}/migrations/")
    expected_dirs = [f"{tmp_project_dir}/migrations/", f"{tmp_project_dir}/migrations/versions"]
    expected_files = [f"{tmp_project_dir}/migrations/env.py", f"{tmp_project_dir}/migrations/script.py.mako"]
    for dir in expected_dirs:
        assert await async_(Path(dir).is_dir)()
    for file in expected_files:
        assert await async_(Path(file).is_file)()
    with pytest.raises(CommandError):
        alembic_commands.init(directory=f"{tmp_project_dir}/migrations/")


@pytest.mark.xdist_group("alembic_drop_all")  # Isolate destructive test to prevent race conditions
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


async def test_dump_tables(
    any_config: SQLAlchemySyncConfig | SQLAlchemyAsyncConfig,
    capfd: CaptureFixture[str],
    tmp_project_dir: Path,
) -> None:
    from sqlalchemy.orm import DeclarativeBase

    from advanced_alchemy import base, mixins

    class _UUIDAuditBase(base.CommonTableAttributes, mixins.UUIDPrimaryKey, DeclarativeBase):
        registry = base.create_registry()

    class TestAuthorModel(_UUIDAuditBase):
        name: Mapped[str] = mapped_column(String(10))

    class TestBookModel(_UUIDAuditBase):
        title: Mapped[str] = mapped_column(String(10))
        author_id: Mapped[UUID] = mapped_column(ForeignKey("test_author_model.id"))

    TestBookModel.author = relationship(TestAuthorModel, lazy="joined", innerjoin=True, viewonly=True)
    TestAuthorModel.books = relationship(TestBookModel, back_populates="author", lazy="noload", uselist=True)

    if isinstance(any_config, SQLAlchemySyncConfig):
        TestBookModel.metadata.create_all(any_config.get_engine())
    else:
        async with any_config.get_engine().begin() as conn:
            await conn.run_sync(TestBookModel.metadata.create_all)

    await dump_tables(
        tmp_project_dir,
        any_config.get_session(),
        [TestAuthorModel, TestBookModel],
    )
    result = capfd.readouterr()
    assert "Dumping table 'test_author_model'" in result.out
    assert "Dumping table 'test_book_model" in result.out


"""
async def test_alembic_revision(alembic_commands: commands.AlembicCommands, tmp_project_dir: Path) -> None:
    alembic_commands.init(directory=f"{tmp_project_dir}/migrations/")
    alembic_commands.revision(message="test", autogenerate=True)


async def test_alembic_upgrade(alembic_commands: commands.AlembicCommands, tmp_project_dir: Path) -> None:
    alembic_commands.init(directory=f"{tmp_project_dir}/migrations/")
    alembic_commands.revision(message="test", autogenerate=True)
    alembic_commands.upgrade(revision="head")
"""
