"""Integration tests for asyncpg session lifecycle in FastAPI extension."""

import warnings
from typing import Annotated

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import String
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.orm import Mapped, mapped_column

from advanced_alchemy.base import UUIDBase
from advanced_alchemy.extensions.fastapi import AdvancedAlchemy, SQLAlchemyAsyncConfig
from advanced_alchemy.repository import SQLAlchemyAsyncRepository
from advanced_alchemy.service import SQLAlchemyAsyncRepositoryService


class LifecycleWidget(UUIDBase):
    """Model for asyncpg lifecycle tests."""

    __tablename__ = "fastapi_asyncpg_lifecycle_widget"

    name: Mapped[str] = mapped_column(String(length=50))


class LifecycleWidgetRepository(SQLAlchemyAsyncRepository[LifecycleWidget]):
    """Async repository for lifecycle widgets."""

    model_type = LifecycleWidget


class LifecycleWidgetService(SQLAlchemyAsyncRepositoryService[LifecycleWidget, LifecycleWidgetRepository]):
    """Async service for lifecycle widgets."""

    repository_type = LifecycleWidgetRepository


@pytest.mark.asyncpg
@pytest.mark.integration
def test_no_gc_warning_on_service_create(asyncpg_engine: AsyncEngine) -> None:
    """Verify generator-managed services do not leave GC warnings."""
    config = SQLAlchemyAsyncConfig(engine_instance=asyncpg_engine)
    app = FastAPI()
    alchemy = AdvancedAlchemy(config=config, app=app)

    @app.get("/")
    async def handler(
        service: Annotated[LifecycleWidgetService, Depends(alchemy.provide_service(LifecycleWidgetService))],
    ) -> dict[str, str]:
        return {"status": "ok"}

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        with TestClient(app=app) as client:
            response = client.get("/")
            assert response.status_code == 200

    assert not any("non-checked-in connection" in str(warning.message) for warning in caught)


@pytest.mark.asyncpg
@pytest.mark.integration
def test_connection_returned_to_pool(asyncpg_engine: AsyncEngine) -> None:
    """Verify asyncpg connections are returned after generator cleanup."""
    config = SQLAlchemyAsyncConfig(engine_instance=asyncpg_engine)
    app = FastAPI()
    alchemy = AdvancedAlchemy(config=config, app=app)

    @app.get("/")
    async def handler(
        service: Annotated[LifecycleWidgetService, Depends(alchemy.provide_service(LifecycleWidgetService))],
    ) -> dict[str, str]:
        return {"status": "ok"}

    with TestClient(app=app) as client:
        response = client.get("/")
        assert response.status_code == 200

    pool = getattr(asyncpg_engine, "pool", None)
    if pool is None or not hasattr(pool, "checkedout"):
        pytest.skip("Pool does not expose checkedout metrics")
    assert pool.checkedout() == 0


@pytest.mark.asyncpg
@pytest.mark.integration
def test_pool_not_exhausted_under_load(asyncpg_engine: AsyncEngine) -> None:
    """Verify multiple requests do not exhaust the asyncpg pool."""
    config = SQLAlchemyAsyncConfig(engine_instance=asyncpg_engine)
    app = FastAPI()
    alchemy = AdvancedAlchemy(config=config, app=app)

    @app.get("/")
    async def handler(
        service: Annotated[LifecycleWidgetService, Depends(alchemy.provide_service(LifecycleWidgetService))],
    ) -> dict[str, str]:
        return {"status": "ok"}

    with TestClient(app=app) as client:
        for _ in range(5):
            response = client.get("/")
            assert response.status_code == 200

    pool = getattr(asyncpg_engine, "pool", None)
    if pool is None or not hasattr(pool, "checkedout"):
        pytest.skip("Pool does not expose checkedout metrics")
    assert pool.checkedout() == 0
