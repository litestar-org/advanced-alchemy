"""Tests for the Flask extension."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import pytest
from flask import Flask
from sqlalchemy import Engine, String, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import Mapped, Session, mapped_column

from advanced_alchemy.base import DefaultBase
from advanced_alchemy.exceptions import ImproperConfigurationError
from advanced_alchemy.extensions.flask import AdvancedAlchemy, SQLAlchemyAsyncConfig, SQLAlchemySyncConfig
from advanced_alchemy.extensions.flask.config import CommitMode


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
    with extension.get_session() as session:
        assert isinstance(session, Session)


def test_sync_extension_init_with_app() -> None:
    """Test initializing the sync extension with app."""
    app = Flask(__name__)
    config = SQLAlchemySyncConfig(connection_string="sqlite:///")
    extension = AdvancedAlchemy(config, app)

    assert "advanced_alchemy" in app.extensions
    assert extension.get_engine() is not None
    assert isinstance(extension.get_engine(), Engine)
    with extension.get_session() as session:
        assert isinstance(session, Session)


def test_sync_extension_multiple_init() -> None:
    """Test initializing the sync extension multiple times."""
    app = Flask(__name__)
    config = SQLAlchemySyncConfig(connection_string="sqlite:///")
    extension = AdvancedAlchemy(config)
    extension.init_app(app)

    with pytest.raises(ImproperConfigurationError, match="Advanced Alchemy extension is already registered"):
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
    async with extension.get_session() as session:
        assert isinstance(session, AsyncSession)


@pytest.mark.asyncio
async def test_async_extension_init_with_app(tmp_path: Path) -> None:
    """Test initializing the async extension with app."""
    app = Flask(__name__)
    config = SQLAlchemyAsyncConfig(
        connection_string=f"sqlite+aiosqlite:///{tmp_path}/test_async_extension_init_with_app.db"
    )
    extension = AdvancedAlchemy(config, app)

    assert "advanced_alchemy" in app.extensions
    assert extension.get_engine() is not None
    assert isinstance(extension.get_engine(), AsyncEngine)
    async with extension.get_session() as session:
        assert isinstance(session, AsyncSession)


@pytest.mark.asyncio
async def test_async_extension_multiple_init(tmp_path: Path) -> None:
    """Test initializing the async extension multiple times."""
    app = Flask(__name__)
    config = SQLAlchemyAsyncConfig(
        connection_string=f"sqlite+aiosqlite:///{tmp_path}/test_async_extension_multiple_init.db"
    )
    extension = AdvancedAlchemy(config)
    extension.init_app(app)

    with pytest.raises(ImproperConfigurationError, match="Advanced Alchemy extension is already registered"):
        extension.init_app(app)


@pytest.mark.asyncio
async def test_async_extension_crud(tmp_path: Path) -> None:
    """Test CRUD operations with async extension."""
    app = Flask(__name__)
    config = SQLAlchemyAsyncConfig(connection_string=f"sqlite+aiosqlite:///{tmp_path}/test_async_extension_crud.db")
    extension = AdvancedAlchemy(config, app)

    async with extension.get_session() as session:
        await config.create_all_metadata()
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


def test_sync_extension_crud(tmp_path: Path) -> None:
    """Test CRUD operations with sync extension."""
    app = Flask(__name__)
    config = SQLAlchemySyncConfig(connection_string=f"sqlite:///{tmp_path}/test_sync_extension_crud.db")
    extension = AdvancedAlchemy(config, app)
    config.create_all_metadata()
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
    configs: Sequence[SQLAlchemySyncConfig] = [
        SQLAlchemySyncConfig(connection_string="sqlite:///", bind_key="db1"),
        SQLAlchemySyncConfig(connection_string="sqlite:///", bind_key="db2"),
    ]
    extension = AdvancedAlchemy(configs, app)

    assert isinstance(extension.get_engine("db1"), Engine)
    assert isinstance(extension.get_engine("db2"), Engine)
    with extension.get_session("db1") as session:
        assert isinstance(session, Session)
    with extension.get_session("db2") as session:
        assert isinstance(session, Session)


@pytest.mark.asyncio
async def test_multiple_binds_async() -> None:
    """Test multiple database bindings with async config."""
    app = Flask(__name__)
    configs: Sequence[SQLAlchemyAsyncConfig] = [
        SQLAlchemyAsyncConfig(connection_string="sqlite+aiosqlite:///", bind_key="db1"),
        SQLAlchemyAsyncConfig(connection_string="sqlite+aiosqlite:///", bind_key="db2"),
    ]
    extension = AdvancedAlchemy(configs, app)

    assert isinstance(extension.get_engine("db1"), AsyncEngine)
    assert isinstance(extension.get_engine("db2"), AsyncEngine)
    async with extension.get_session("db1") as session:
        assert isinstance(session, AsyncSession)
    async with extension.get_session("db2") as session:
        assert isinstance(session, AsyncSession)


@pytest.mark.asyncio
async def test_mixed_binds() -> None:
    """Test mixed sync and async database bindings."""
    app = Flask(__name__)
    configs = [
        SQLAlchemySyncConfig(connection_string="sqlite:///", bind_key="sync"),
        SQLAlchemyAsyncConfig(connection_string="sqlite+aiosqlite:///", bind_key="async"),
    ]
    extension = AdvancedAlchemy(configs, app)

    assert isinstance(extension.get_engine("sync"), Engine)
    assert isinstance(extension.get_engine("async"), AsyncEngine)
    with extension.get_session("sync") as session:
        assert isinstance(session, Session)
    async with extension.get_session("async") as session:
        assert isinstance(session, AsyncSession)


def test_sync_session_context_manager(tmp_path: Path) -> None:
    """Test synchronous session context manager."""
    app = Flask(__name__)
    config = SQLAlchemySyncConfig(connection_string=f"sqlite:///{tmp_path}/test_sync_session_context_manager.db")
    extension = AdvancedAlchemy(config, app)

    with extension.get_session() as session:
        config.create_all_metadata()
        session.add(User(name="test"))
        session.commit()

        result = session.execute(select(User).where(User.name == "test"))
        user = result.scalar_one()
        assert user.name == "test"


@pytest.mark.asyncio
async def test_async_session_context_manager(tmp_path: Path) -> None:
    """Test asynchronous session context manager."""
    app = Flask(__name__)
    config = SQLAlchemyAsyncConfig(
        connection_string=f"sqlite+aiosqlite:///{tmp_path}/test_async_session_context_manager.db"
    )
    extension = AdvancedAlchemy(config, app)

    async with extension.async_session() as session:
        await config.create_all_metadata()
        session.add(User(name="test"))
        await session.commit()

        result = await session.execute(select(User).where(User.name == "test"))
        user = result.scalar_one()
        assert user.name == "test"


def test_sync_session_rollback(tmp_path: Path) -> None:
    """Test synchronous session rollback on error."""
    app = Flask(__name__)
    config = SQLAlchemySyncConfig(connection_string=f"sqlite:///{tmp_path}/test_sync_session_rollback.db")
    extension = AdvancedAlchemy(config, app)

    with pytest.raises(ValueError):
        with extension.get_session() as session:
            user = User(name="test")
            session.add(user)
            session.commit()
            raise ValueError("Test error")

    # Verify the transaction was rolled back
    with extension.get_session() as session:
        result = session.execute(select(User).where(User.name == "test"))
        assert result.first() is None


@pytest.mark.asyncio
async def test_async_session_wrong_config() -> None:
    """Test error when using async session with sync config."""
    app = Flask(__name__)
    config = SQLAlchemySyncConfig(connection_string="sqlite:///")
    extension = AdvancedAlchemy(config, app)

    with pytest.raises(ImproperConfigurationError):
        async with extension.get_session() as _:
            pass


def test_sync_autocommit(tmp_path: Path) -> None:
    """Test synchronous autocommit functionality."""
    app = Flask(__name__)
    config = SQLAlchemySyncConfig(
        connection_string=f"sqlite:///{tmp_path}/test_sync_autocommit.db", commit_mode=CommitMode.AUTOCOMMIT
    )
    extension = AdvancedAlchemy(config, app)

    with app.test_client() as client:

        @app.route("/test", methods=["POST"])
        def test_route() -> tuple[dict[str, str], int]:
            with extension.get_session() as session:
                session.add(User(name="test"))
            return {"status": "success"}, 200

        # Test successful response (should commit)
        response = client.post("/test")
        assert response.status_code == 200

        # Verify the data was committed
        with extension.get_session() as session:
            result = session.execute(select(User).where(User.name == "test"))
            assert result.scalar_one().name == "test"


def test_sync_autocommit_with_redirect(tmp_path: Path) -> None:
    """Test synchronous autocommit with redirect functionality."""
    app = Flask(__name__)
    config = SQLAlchemySyncConfig(
        connection_string=f"sqlite:///{tmp_path}/test_sync_autocommit_with_redirect.db",
        commit_mode=CommitMode.AUTOCOMMIT_WITH_REDIRECT,
    )
    extension = AdvancedAlchemy(config, app)

    with app.test_client() as client:

        @app.route("/test", methods=["POST"])
        def test_route() -> tuple[str, int, dict[str, str]]:
            with extension.get_session() as session:
                session.add(User(name="test_redirect"))
            return "", 302, {"Location": "/redirected"}

        # Test redirect response (should commit with AUTOCOMMIT_WITH_REDIRECT)
        response = client.post("/test")
        assert response.status_code == 302

        # Verify the data was committed
        with extension.session() as session:
            result = session.execute(select(User).where(User.name == "test_redirect"))
            assert result.scalar_one().name == "test_redirect"


def test_sync_no_autocommit_on_error(tmp_path: Path) -> None:
    """Test that autocommit doesn't occur on error responses."""
    app = Flask(__name__)
    config = SQLAlchemySyncConfig(
        connection_string=f"sqlite:///{tmp_path}/test_sync_no_autocommit_on_error.db",
        commit_mode=CommitMode.AUTOCOMMIT,
    )
    extension = AdvancedAlchemy(config, app)

    with app.test_client() as client:

        @app.route("/test", methods=["POST"])
        def test_route() -> tuple[dict[str, str], int]:
            with extension.session() as session:
                user = User(name="test_error")
                session.add(user)
            return {"error": "test error"}, 500

        # Test error response (should not commit)
        response = client.post("/test")
        assert response.status_code == 500

        # Verify the data was not committed
        with extension.session() as session:
            result = session.execute(select(User).where(User.name == "test_error"))
            assert result.first() is None


@pytest.mark.asyncio
async def test_async_autocommit(tmp_path: Path) -> None:
    """Test asynchronous autocommit functionality."""
    app = Flask(__name__)
    config = SQLAlchemyAsyncConfig(
        connection_string=f"sqlite+aiosqlite:///{tmp_path}/test_async_autocommit.db",
        commit_mode=CommitMode.AUTOCOMMIT,
    )
    extension = AdvancedAlchemy(config, app)

    with app.test_client() as client:

        @app.route("/test", methods=["POST"])
        async def test_route() -> tuple[dict[str, str], int]:
            async with extension.async_session() as session:
                user = User(name="test_async")  # type: ignore
                session.add(user)
            return {"status": "success"}, 200

        # Test successful response (should commit)
        response = client.post("/test")
        assert response.status_code == 200

        # Verify the data was committed
        async with extension.async_session() as session:
            result = await session.execute(select(User).where(User.name == "test_async"))
            assert (await result.scalar_one()).name == "test_async"


@pytest.mark.asyncio
async def test_async_autocommit_with_redirect(tmp_path: Path) -> None:
    """Test asynchronous autocommit with redirect functionality."""
    app = Flask(__name__)
    config = SQLAlchemyAsyncConfig(
        connection_string=f"sqlite+aiosqlite:///{tmp_path}/test_async_autocommit_with_redirect.db",
        commit_mode=CommitMode.AUTOCOMMIT_WITH_REDIRECT,
    )
    extension = AdvancedAlchemy(config, app)

    with app.test_client() as client:

        @app.route("/test", methods=["POST"])
        async def test_route() -> tuple[str, int, dict[str, str]]:
            async with extension.async_session() as session:
                user = User(name="test_async_redirect")  # type: ignore
                session.add(user)
            return "", 302, {"Location": "/redirected"}

        # Test redirect response (should commit with AUTOCOMMIT_WITH_REDIRECT)
        response = client.post("/test")
        assert response.status_code == 302

        # Verify the data was committed
        async with extension.async_session() as session:
            result = await session.execute(select(User).where(User.name == "test_async_redirect"))
            assert (await result.scalar_one()).name == "test_async_redirect"
