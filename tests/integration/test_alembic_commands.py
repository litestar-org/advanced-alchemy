from __future__ import annotations

from pathlib import Path
from typing import Generator, Type, cast
from uuid import UUID

import pytest
from _pytest.monkeypatch import MonkeyPatch
from pytest import CaptureFixture, FixtureRequest
from pytest_lazy_fixtures import lf
from sqlalchemy import Engine, ForeignKey, String
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column, relationship, sessionmaker

from advanced_alchemy import base
from advanced_alchemy.alembic import commands
from advanced_alchemy.alembic.utils import drop_all, dump_tables
from advanced_alchemy.extensions.litestar import SQLAlchemyAsyncConfig, SQLAlchemySyncConfig
from alembic.util.exc import CommandError
from tests.fixtures.uuid import models as models_uuid
from tests.helpers import maybe_async

AuthorModel = Type[models_uuid.UUIDAuthor]
RuleModel = Type[models_uuid.UUIDRule]
ModelWithFetchedValue = Type[models_uuid.UUIDModelWithFetchedValue]
ItemModel = Type[models_uuid.UUIDItem]
TagModel = Type[models_uuid.UUIDTag]

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
            "oracle23c_engine",
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
            "oracle23c_async_engine",
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


@pytest.fixture
def tmp_project_dir(monkeypatch: MonkeyPatch, tmp_path: Path) -> Generator[Path, None, None]:
    path = tmp_path / "project_dir"
    path.mkdir(exist_ok=True)
    monkeypatch.chdir(path)
    yield path


async def test_alembic_init(alembic_commands: commands.AlembicCommands, tmp_project_dir: Path) -> None:
    alembic_commands.init(directory=f"{tmp_project_dir}/migrations/")
    expected_dirs = [f"{tmp_project_dir}/migrations/", f"{tmp_project_dir}/migrations/versions"]
    expected_files = [f"{tmp_project_dir}/migrations/env.py", f"{tmp_project_dir}/migrations/script.py.mako"]
    for dir in expected_dirs:
        assert Path(dir).is_dir()
    for file in expected_files:
        assert Path(file).is_file()


async def test_alembic_init_already(alembic_commands: commands.AlembicCommands, tmp_project_dir: Path) -> None:
    alembic_commands.init(directory=f"{tmp_project_dir}/migrations/")
    expected_dirs = [f"{tmp_project_dir}/migrations/", f"{tmp_project_dir}/migrations/versions"]
    expected_files = [f"{tmp_project_dir}/migrations/env.py", f"{tmp_project_dir}/migrations/script.py.mako"]
    for dir in expected_dirs:
        assert Path(dir).is_dir()
    for file in expected_files:
        assert Path(file).is_file()
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
