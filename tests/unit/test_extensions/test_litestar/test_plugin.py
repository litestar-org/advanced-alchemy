from pathlib import Path
from typing import Any, Union

import pytest
from litestar import Litestar, get
from litestar.di import NamedDependency
from litestar.testing import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, Session

from advanced_alchemy._listeners import is_async_context
from advanced_alchemy.base import BigIntPrimaryKey
from advanced_alchemy.extensions.litestar import (
    SQLAlchemyAsyncConfig,
    SQLAlchemyInitPlugin,
    SQLAlchemySyncConfig,
)


def test_litestar_is_async_context(tmp_path: Path) -> None:
    """Test that is_async_context is set correctly in Litestar dependency injection."""
    db_path = tmp_path / "litestar_context_test.db"

    class Base(DeclarativeBase):
        pass

    class SyncModel(BigIntPrimaryKey, Base):  # type: ignore
        __tablename__ = "sync_model_litestar_test"
        name: Mapped[str]

    class AsyncModel(BigIntPrimaryKey, Base):  # type: ignore
        __tablename__ = "async_model_litestar_test"
        name: Mapped[str]

    @get("/sync")
    def sync_route(db_session: NamedDependency[Session]) -> dict[str, Any]:
        instance = db_session.execute(select(SyncModel).where(SyncModel.id == 1)).scalar_one()
        return {"id": instance.id, "name": instance.name, "is_async_context": is_async_context()}

    @get("/async")
    async def async_route(db_session: NamedDependency[AsyncSession]) -> dict[str, Any]:
        instance = await db_session.execute(select(AsyncModel).where(AsyncModel.id == 1))
        scalar_instance = instance.scalar_one()
        return {"id": scalar_instance.id, "name": scalar_instance.name, "is_async_context": is_async_context()}

    sync_config = SQLAlchemySyncConfig(connection_string=f"sqlite:///{db_path}")
    sync_plugin = SQLAlchemyInitPlugin(config=sync_config)

    @get("/test_sync")
    def sync_handler(db_session: NamedDependency[Session]) -> dict[str, Any]:
        return {"is_async": is_async_context()}

    sync_app = Litestar(route_handlers=[sync_handler], plugins=[sync_plugin])

    with sync_config.get_engine().begin() as conn:
        Base.metadata.create_all(conn)

    with TestClient(app=sync_app) as sync_client:
        response = sync_client.get("/test_sync")
        assert response.status_code == 200
        assert response.json() == {"is_async": True}

    async_config = SQLAlchemyAsyncConfig(connection_string=f"sqlite+aiosqlite:///{db_path}")
    async_plugin = SQLAlchemyInitPlugin(config=async_config)

    @get("/test_async")
    async def async_handler(db_session: NamedDependency[AsyncSession]) -> dict[str, Any]:
        return {"is_async": is_async_context()}

    async_app = Litestar(route_handlers=[async_handler], plugins=[async_plugin])

    async def create_async_tables() -> None:
        async with async_config.get_engine().begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    import asyncio

    asyncio.run(create_async_tables())

    with TestClient(app=async_app) as async_client:
        response = async_client.get("/test_async")
        assert response.status_code == 200
        assert response.json() == {"is_async": True}


def test_plugin_is_async_context(tmp_path: Path) -> None:
    """Test that is_async_context is set correctly via plugin dependency injection."""
    db_path = tmp_path / "litestar_plugin_context.db"

    class Base(DeclarativeBase):
        pass

    class SyncModel(BigIntPrimaryKey, Base):  # type: ignore
        __tablename__ = "sync_model_litestar_test"
        name: Mapped[str]

    class AsyncModel(BigIntPrimaryKey, Base):  # type: ignore
        __tablename__ = "async_model_litestar_test"
        name: Mapped[str]

    @get("/sync")
    def sync_route(db_session: NamedDependency[Session]) -> dict[str, Any]:
        instance = db_session.execute(select(SyncModel).where(SyncModel.id == 1)).scalar_one()
        return {"id": instance.id, "name": instance.name, "is_async_context": is_async_context()}

    @get("/async")
    async def async_route(db_session: NamedDependency[AsyncSession]) -> dict[str, Any]:
        instance = await db_session.execute(select(AsyncModel).where(AsyncModel.id == 1))
        scalar_instance = instance.scalar_one()
        return {"id": scalar_instance.id, "name": scalar_instance.name, "is_async_context": is_async_context()}

    sync_config = SQLAlchemySyncConfig(connection_string=f"sqlite:///{db_path}")
    sync_plugin = SQLAlchemyInitPlugin(config=sync_config)

    @get("/test_sync_plugin")
    def sync_plugin_handler(db_session: NamedDependency[Session]) -> dict[str, Any]:  # type: ignore[arg-type]
        return {"is_async": is_async_context()}

    sync_app = Litestar(route_handlers=[sync_plugin_handler], plugins=[sync_plugin])

    with sync_config.get_engine().begin() as conn:
        Base.metadata.create_all(conn)

    with TestClient(app=sync_app) as sync_client:
        response = sync_client.get("/test_sync_plugin")
        assert response.status_code == 200
        assert response.json() == {"is_async": True}

    async_config = SQLAlchemyAsyncConfig(connection_string=f"sqlite+aiosqlite:///{db_path}")
    async_plugin = SQLAlchemyInitPlugin(config=async_config)

    @get("/test_async_plugin")
    async def async_plugin_handler(db_session: NamedDependency[AsyncSession]) -> dict[str, Any]:  # type: ignore[arg-type]
        return {"is_async": is_async_context()}

    async_app = Litestar(route_handlers=[async_plugin_handler], plugins=[async_plugin])

    async def create_async_tables() -> None:
        async with async_config.get_engine().begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    import asyncio

    asyncio.run(create_async_tables())

    with TestClient(app=async_app) as async_client:
        response = async_client.get("/test_async_plugin")
        assert response.status_code == 200
        assert response.json() == {"is_async": True}


@pytest.mark.filterwarnings("error:Call to deprecated function 'set_async_context':DeprecationWarning")
@pytest.mark.parametrize("is_async", [True, False])
def test_provide_session_does_not_call_deprecated_set_async_context(tmp_path: Path, is_async: bool) -> None:
    """Providing a session must not emit the ``set_async_context`` deprecation warning."""
    db_path = tmp_path / "litestar_deprecation_test.db"
    config: Union[SQLAlchemyAsyncConfig, SQLAlchemySyncConfig]
    if is_async:
        config = SQLAlchemyAsyncConfig(connection_string=f"sqlite+aiosqlite:///{db_path}")

        @get("/")
        async def handler(db_session: NamedDependency[AsyncSession]) -> None:
            return None

    else:
        config = SQLAlchemySyncConfig(connection_string=f"sqlite:///{db_path}")

        @get("/", sync_to_thread=False)
        def handler(db_session: NamedDependency[Session]) -> None:
            return None

    app = Litestar(route_handlers=[handler], plugins=[SQLAlchemyInitPlugin(config=config)])

    with TestClient(app=app) as client:
        response = client.get("/")
        assert response.status_code == 200
