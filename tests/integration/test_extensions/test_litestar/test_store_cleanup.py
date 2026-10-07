"""Verify expired-store cleanup against SQLite with both session configurations."""

import datetime
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Optional, Union

import pytest
import time_machine
from litestar.exceptions import ImproperlyConfiguredException
from sqlalchemy import select
from sqlalchemy.orm import Mapped, mapped_column

from advanced_alchemy.extensions.litestar import SQLAlchemyAsyncConfig, SQLAlchemySyncConfig
from advanced_alchemy.extensions.litestar.store import SQLAlchemyStore, StoreModelMixin
from advanced_alchemy.types import DateTimeUTC

pytestmark = pytest.mark.integration


class CleanupStoreModel(StoreModelMixin):
    __tablename__ = "cleanup_store"

    # Use a nullable custom column to exercise the store API's non-expiring values.
    expires_at: Mapped[Optional[datetime.datetime]] = mapped_column(  # type: ignore[assignment]
        DateTimeUTC(), nullable=True, index=True
    )


@pytest.fixture(params=["sync", "async"])
async def cleanup_config(
    request: pytest.FixtureRequest, tmp_path: Path
) -> AsyncGenerator[Union[SQLAlchemySyncConfig, SQLAlchemyAsyncConfig], None]:
    config: Union[SQLAlchemySyncConfig, SQLAlchemyAsyncConfig]
    if request.param == "async":
        config = SQLAlchemyAsyncConfig(connection_string=f"sqlite+aiosqlite:///{tmp_path / 'store.db'}")
        async with config.get_engine().begin() as connection:
            await connection.run_sync(CleanupStoreModel.__table__.create)
        yield config
        await config.get_engine().dispose()
    else:
        config = SQLAlchemySyncConfig(connection_string=f"sqlite:///{tmp_path / 'store.db'}")
        CleanupStoreModel.__table__.create(config.get_engine())
        yield config
        config.get_engine().dispose()


@pytest.mark.parametrize("namespace", ["LITESTAR", "sessions", "sessions_nested"])
async def test_delete_expired_preserves_other_entries(
    cleanup_config: Union[SQLAlchemySyncConfig, SQLAlchemyAsyncConfig], namespace: str
) -> None:
    now = datetime.datetime(2026, 9, 7, tzinfo=datetime.timezone.utc)
    rows = [
        CleanupStoreModel(
            key="expired", namespace=namespace, value=b"expired", expires_at=now - datetime.timedelta(seconds=1)
        ),
        CleanupStoreModel(key="boundary", namespace=namespace, value=b"boundary", expires_at=now),
        CleanupStoreModel(key="live", namespace=namespace, value=b"live", expires_at=now + datetime.timedelta(hours=1)),
        CleanupStoreModel(key="permanent", namespace=namespace, value=b"permanent", expires_at=None),
        CleanupStoreModel(key="other", namespace="other", value=b"other", expires_at=now),
        CleanupStoreModel(key="nested", namespace=f"{namespace}_child", value=b"nested", expires_at=now),
    ]
    if isinstance(cleanup_config, SQLAlchemyAsyncConfig):
        async with cleanup_config.get_session() as session:
            session.add_all(rows)
            await session.commit()
    else:
        with cleanup_config.get_session() as session:
            session.add_all(rows)
            session.commit()

    store = SQLAlchemyStore(config=cleanup_config, model=CleanupStoreModel, namespace=namespace)
    with time_machine.travel(now, tick=False):
        await store.delete_expired()
        await store.delete_expired()

    statement = select(CleanupStoreModel.key)
    if isinstance(cleanup_config, SQLAlchemyAsyncConfig):
        async with cleanup_config.get_session() as session:
            remaining_keys = set((await session.execute(statement)).scalars())
    else:
        with cleanup_config.get_session() as session:
            remaining_keys = set(session.execute(statement).scalars())
    assert remaining_keys == {"live", "permanent", "other", "nested"}


async def test_delete_expired_requires_namespace(
    cleanup_config: Union[SQLAlchemySyncConfig, SQLAlchemyAsyncConfig],
) -> None:
    store = SQLAlchemyStore(config=cleanup_config, model=CleanupStoreModel, namespace=None)
    with pytest.raises(ImproperlyConfiguredException, match="No namespace configured"):
        await store.delete_expired()
