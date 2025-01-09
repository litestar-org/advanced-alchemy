"""Tests for the Flask extension."""

from __future__ import annotations

import pytest
from flask import Flask
from sqlalchemy import Engine, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import Session

from advanced_alchemy.extensions.flask import AdvancedAlchemy
from advanced_alchemy.extensions.flask.config import SQLAlchemyAsyncConfig, SQLAlchemySyncConfig

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from advanced_alchemy.base import Base, DefaultBase


class User(DefaultBase):
    """Test user model."""

    __tablename__ = "users_testing"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50))


def test_sync_extension_init() -> None:
    """Test initializing the sync extension."""
    app = Flask(__name__)
    config = SQLAlchemySyncConfig(connection_string="sqlite:///")
    extension = AdvancedAlchemy(config)
    extension.init_app(app)

    assert "advanced_alchemy" in app.extensions
    assert extension.get_engine() is not None
    assert isinstance(extension.get_engine(), Engine)
    assert isinstance(extension.get_session(), Session)


def test_sync_extension_init_with_app() -> None:
    """Test initializing the sync extension with app."""
    app = Flask(__name__)
    config = FlaskSQLAlchemySyncConfig(connection_string="sqlite:///")
    extension = AdvancedAlchemy(config, app)

    assert "advanced_alchemy" in app.extensions
    assert extension.get_engine() is not None
    assert isinstance(extension.get_engine(), Engine)
    assert isinstance(extension.get_session(), Session)


def test_sync_extension_multiple_init() -> None:
    """Test initializing the sync extension multiple times."""
    app = Flask(__name__)
    config = FlaskSQLAlchemySyncConfig(connection_string="sqlite:///")
    extension = AdvancedAlchemy(config)
    extension.init_app(app)

    with pytest.raises(RuntimeError, match="AdvancedAlchemy is already initialized"):
        extension.init_app(app)


@pytest.mark.asyncio
async def test_async_extension_init() -> None:
    """Test initializing the async extension."""
    app = Flask(__name__)
    config = SQLAlchemyAsyncConfig(connection_string="sqlite+aiosqlite:///")
    extension = AdvancedAlchemy(config)
    extension.init_app(app)

    assert "advanced_alchemy" in app.extensions
    assert extension.get_engine() is not None
    assert isinstance(extension.get_engine(), AsyncEngine)
    assert isinstance(extension.get_session(), AsyncSession)


@pytest.mark.asyncio
async def test_async_extension_init_with_app() -> None:
    """Test initializing the async extension with app."""
    app = Flask(__name__)
    config = SQLAlchemyAsyncConfig(connection_string="sqlite+aiosqlite:///")
    extension = AdvancedAlchemy(config, app)

    assert "advanced_alchemy" in app.extensions
    assert extension.get_engine() is not None
    assert isinstance(extension.get_engine(), AsyncEngine)
    assert isinstance(extension.get_session(), AsyncSession)


@pytest.mark.asyncio
async def test_async_extension_multiple_init() -> None:
    """Test initializing the async extension multiple times."""
    app = Flask(__name__)
    config = SQLAlchemyAsyncConfig(connection_string="sqlite+aiosqlite:///")
    extension = AdvancedAlchemy(config)
    extension.init_app(app)

    with pytest.raises(RuntimeError, match="AdvancedAlchemy is already initialized"):
        extension.init_app(app)


@pytest.mark.asyncio
async def test_async_extension_crud() -> None:
    """Test CRUD operations with async extension."""
    app = Flask(__name__)
    config = SQLAlchemyAsyncConfig(connection_string="sqlite+aiosqlite:///")
    extension = AdvancedAlchemy(config, app)

    async with extension.get_session() as session:
        async with session.begin():
            user = User(name="test")
            session.add(user)

        async with session.begin():
            result = await session.execute(select(User).where(User.name == "test"))
            user = result.scalar_one()
            assert user.name == "test"

            user.name = "updated"

        async with session.begin():
            result = await session.execute(select(User).where(User.name == "updated"))
            user = result.scalar_one()
            assert user.name == "updated"

            await session.delete(user)

        async with session.begin():
            result = await session.execute(select(User).where(User.name == "updated"))
            assert result.first() is None


def test_sync_extension_crud() -> None:
    """Test CRUD operations with sync extension."""
    app = Flask(__name__)
    config = FlaskSQLAlchemySyncConfig(connection_string="sqlite:///")
    extension = AdvancedAlchemy(config, app)

    with extension.get_session() as session:
        with session.begin():
            user = User(name="test")
            session.add(user)

        with session.begin():
            result = session.execute(select(User).where(User.name == "test"))
            user = result.scalar_one()
            assert user.name == "test"

            user.name = "updated"

        with session.begin():
            result = session.execute(select(User).where(User.name == "updated"))
            user = result.scalar_one()
            assert user.name == "updated"

            session.delete(user)

        with session.begin():
            result = session.execute(select(User).where(User.name == "updated"))
            assert result.first() is None


def test_multiple_binds() -> None:
    """Test multiple database bindings."""
    app = Flask(__name__)
    configs = [
        FlaskSQLAlchemySyncConfig(connection_string="sqlite:///", bind_key="db1"),
        FlaskSQLAlchemySyncConfig(connection_string="sqlite:///", bind_key="db2"),
    ]
    extension = AdvancedAlchemy(configs, app)

    assert isinstance(extension.get_engine("db1"), Engine)
    assert isinstance(extension.get_engine("db2"), Engine)
    assert isinstance(extension.get_session("db1"), Session)
    assert isinstance(extension.get_session("db2"), Session)


@pytest.mark.asyncio
async def test_multiple_binds_async() -> None:
    """Test multiple database bindings with async config."""
    app = Flask(__name__)
    configs = [
        SQLAlchemyAsyncConfig(connection_string="sqlite+aiosqlite:///", bind_key="db1"),
        SQLAlchemyAsyncConfig(connection_string="sqlite+aiosqlite:///", bind_key="db2"),
    ]
    extension = AdvancedAlchemy(configs, app)

    assert isinstance(extension.get_engine("db1"), AsyncEngine)
    assert isinstance(extension.get_engine("db2"), AsyncEngine)
    assert isinstance(extension.get_session("db1"), AsyncSession)
    assert isinstance(extension.get_session("db2"), AsyncSession)


@pytest.mark.asyncio
async def test_mixed_binds() -> None:
    """Test mixed sync and async database bindings."""
    app = Flask(__name__)
    configs = [
        FlaskSQLAlchemySyncConfig(connection_string="sqlite:///", bind_key="sync"),
        SQLAlchemyAsyncConfig(connection_string="sqlite+aiosqlite:///", bind_key="async"),
    ]
    extension = AdvancedAlchemy(configs, app)

    assert isinstance(extension.get_engine("sync"), Engine)
    assert isinstance(extension.get_engine("async"), AsyncEngine)
    assert isinstance(extension.get_session("sync"), Session)
    assert isinstance(extension.get_session("async"), AsyncSession)
