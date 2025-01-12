"""Tests for the Flask extension."""

from __future__ import annotations

from pathlib import Path
from typing import Generator, Sequence

import pytest
from flask import Flask
from sqlalchemy import String, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, Session, mapped_column

from advanced_alchemy.base import BigIntBase
from advanced_alchemy.exceptions import ImproperConfigurationError
from advanced_alchemy.extensions.flask import AdvancedAlchemy, SQLAlchemyAsyncConfig, SQLAlchemySyncConfig
from advanced_alchemy.extensions.flask.config import CommitMode


class User(BigIntBase):
    """Test user model."""

    __tablename__ = "users_testing"
    __bind_key__ = None  # Ensure it uses the default bind key

    name: Mapped[str] = mapped_column(String(50))


@pytest.fixture
def app() -> Generator[Flask, None, None]:
    """Create a Flask app for testing."""
    app = Flask(__name__)
    with app.app_context():
        yield app


def test_sync_extension_init(app: Flask) -> None:
    """Test initializing the sync extension."""
    config = SQLAlchemySyncConfig(connection_string="sqlite:///")
    extension = AdvancedAlchemy(config, app)
    assert "advanced_alchemy" in app.extensions
    session = extension.get_session()
    assert isinstance(session, Session)


def test_sync_extension_init_with_app(app: Flask) -> None:
    """Test initializing the sync extension with app."""
    config = SQLAlchemySyncConfig(connection_string="sqlite:///")
    extension = AdvancedAlchemy(config, app)
    assert "advanced_alchemy" in app.extensions
    session = extension.get_session()
    assert isinstance(session, Session)


def test_sync_extension_multiple_init(app: Flask) -> None:
    """Test initializing the sync extension multiple times."""
    with pytest.raises(ImproperConfigurationError, match="Advanced Alchemy extension is already registered"):
        config = SQLAlchemySyncConfig(connection_string="sqlite:///")
        extension = AdvancedAlchemy(config, app)
        extension.init_app(app)


def test_async_extension_init(app: Flask) -> None:
    """Test initializing the async extension."""
    config = SQLAlchemyAsyncConfig(bind_key="async", connection_string="sqlite+aiosqlite:///")
    extension = AdvancedAlchemy(config, app)
    assert "advanced_alchemy" in app.extensions
    session = extension.get_session("async")
    assert isinstance(session, AsyncSession)


def test_async_extension_init_single_config_no_bind_key(app: Flask) -> None:
    """Test initializing the async extension."""
    config = SQLAlchemyAsyncConfig(connection_string="sqlite+aiosqlite:///")
    extension = AdvancedAlchemy(config, app)
    assert "advanced_alchemy" in app.extensions
    session = extension.get_session()
    assert isinstance(session, AsyncSession)


def test_async_extension_init_with_app(app: Flask) -> None:
    """Test initializing the async extension with app."""
    config = SQLAlchemyAsyncConfig(bind_key="async", connection_string="sqlite+aiosqlite:///")
    extension = AdvancedAlchemy(config, app)
    assert "advanced_alchemy" in app.extensions
    session = extension.get_session("async")
    assert isinstance(session, AsyncSession)


def test_async_extension_multiple_init(app: Flask) -> None:
    """Test initializing the async extension multiple times."""
    with pytest.raises(ImproperConfigurationError, match="Advanced Alchemy extension is already registered"):
        config = SQLAlchemyAsyncConfig(bind_key="async", connection_string="sqlite+aiosqlite:///")
        extension = AdvancedAlchemy(config, app)
        extension.init_app(app)


def test_sync_and_async_extension_init(app: Flask) -> None:
    """Test initializing the sync and async extension."""
    configs = [
        SQLAlchemySyncConfig(connection_string="sqlite:///"),
        SQLAlchemyAsyncConfig(connection_string="sqlite+aiosqlite:///", bind_key="async"),
    ]
    extension = AdvancedAlchemy(configs, app)
    assert "advanced_alchemy" in app.extensions
    session = extension.get_session()
    assert isinstance(session, Session)


def test_multiple_binds(app: Flask) -> None:
    """Test multiple database bindings."""

    extension = AdvancedAlchemy(
        [
            SQLAlchemySyncConfig(connection_string="sqlite:///", bind_key="db1"),
            SQLAlchemySyncConfig(connection_string="sqlite:///", bind_key="db2"),
        ],
        app,
    )

    session = extension.get_session("db1")
    assert isinstance(session, Session)
    session = extension.get_session("db2")
    assert isinstance(session, Session)


def test_multiple_binds_async(app: Flask) -> None:
    """Test multiple database bindings with async config."""

    configs: Sequence[SQLAlchemyAsyncConfig] = [
        SQLAlchemyAsyncConfig(connection_string="sqlite+aiosqlite:///", bind_key="db1"),
        SQLAlchemyAsyncConfig(connection_string="sqlite+aiosqlite:///", bind_key="db2"),
    ]
    extension = AdvancedAlchemy(configs, app)

    session = extension.get_session("db1")
    assert isinstance(session, AsyncSession)
    session = extension.get_session("db2")
    assert isinstance(session, AsyncSession)


def test_mixed_binds(app: Flask) -> None:
    """Test mixed sync and async database bindings."""
    configs = [
        SQLAlchemySyncConfig(connection_string="sqlite:///", bind_key="sync"),
        SQLAlchemyAsyncConfig(connection_string="sqlite+aiosqlite:///", bind_key="async"),
    ]
    extension = AdvancedAlchemy(configs, app)

    session = extension.get_session("sync")
    assert isinstance(session, Session)
    session = extension.get_session("async")
    assert isinstance(session, AsyncSession)


def test_sync_autocommit(tmp_path: Path) -> None:
    """Test synchronous autocommit functionality."""
    app = Flask(__name__)
    config = SQLAlchemySyncConfig(
        connection_string=f"sqlite:///{tmp_path}/test_sync_autocommit.db",
        commit_mode=CommitMode.AUTOCOMMIT,
        create_all=True,
    )
    print(f"Bind key: {config.bind_key}")
    print(f"Metadata: {User.__metadata_registry__.get(config.bind_key)}")
    print(f"Connection string: {config.connection_string}")

    # Register User model's metadata with the config's bind key
    User.__metadata_registry__.get(config.bind_key).create_all(config.get_engine())
    extension = AdvancedAlchemy(config, app)

    # Create tables before the test client starts
    config.create_all_metadata()

    with app.test_client() as client:

        @app.route("/test", methods=["POST"])
        def test_route() -> tuple[dict[str, str], int]:
            session = extension.get_session()
            assert isinstance(session, Session)
            user = User(name="test")
            session.add(user)
            print(f"Session new: {session.new}")
            return {"status": "success"}, 200

        # Test successful response (should commit)
        response = client.post("/test")
        assert response.status_code == 200

        # Verify the data was committed
        session = extension.get_session()
        assert isinstance(session, Session)
        result = session.execute(select(User).where(User.name == "test"))
        assert result.scalar_one().name == "test"


def test_sync_autocommit_with_redirect(app: Flask, tmp_path: Path) -> None:
    """Test synchronous autocommit with redirect functionality."""
    config = SQLAlchemySyncConfig(
        connection_string=f"sqlite:///{tmp_path}/test_sync_autocommit_with_redirect.db",
        commit_mode=CommitMode.AUTOCOMMIT_WITH_REDIRECT,
        create_all=True,
    )
    # Create tables before initializing extension
    User.__metadata_registry__.get(config.bind_key).create_all(config.get_engine())
    extension = AdvancedAlchemy(config, app)

    with app.test_client() as client:
        config.create_all_metadata()

        @app.route("/test", methods=["POST"])
        def test_route() -> tuple[str, int, dict[str, str]]:
            session = extension.get_session()
            assert isinstance(session, Session)
            session.add(User(name="test_redirect"))
            return "", 302, {"Location": "/redirected"}

        # Test redirect response (should commit with AUTOCOMMIT_WITH_REDIRECT)
        response = client.post("/test")
        assert response.status_code == 302

        # Verify the data was committed
        session = extension.get_session()
        assert isinstance(session, Session)
        result = session.execute(select(User).where(User.name == "test_redirect"))
        assert result.scalar_one().name == "test_redirect"


def test_sync_no_autocommit_on_error(tmp_path: Path) -> None:
    """Test that autocommit doesn't occur on error responses."""
    app = Flask(__name__)
    config = SQLAlchemySyncConfig(
        connection_string=f"sqlite:///{tmp_path}/test_sync_no_autocommit_on_error.db",
        commit_mode=CommitMode.AUTOCOMMIT,
    )
    # Create tables before initializing extension
    config.create_all_metadata()
    extension = AdvancedAlchemy(config, app)

    with app.test_client() as client:

        @app.route("/test", methods=["POST"])
        def test_route() -> tuple[dict[str, str], int]:
            session = extension.get_session()
            assert isinstance(session, Session)
            user = User(name="test_error")
            session.add(user)
            return {"error": "test error"}, 500

        # Test error response (should not commit)
        response = client.post("/test")
        assert response.status_code == 500

        # Verify the data was not committed
        session = extension.get_session()
        assert isinstance(session, Session)
        result = session.execute(select(User).where(User.name == "test_error"))
        assert result.first() is None


def test_async_autocommit(tmp_path: Path) -> None:
    """Test asynchronous autocommit functionality."""
    app = Flask(__name__)
    config = SQLAlchemyAsyncConfig(
        connection_string=f"sqlite+aiosqlite:///{tmp_path}/test_async_autocommit.db",
        commit_mode=CommitMode.AUTOCOMMIT,
    )
    # Create tables before initializing extension

    extension = AdvancedAlchemy(config, app)

    with app.test_client() as client, extension.with_portal() as portal:
        assert portal is not None
        User.__metadata_registry__.get(config.bind_key).create_all(config.get_engine().sync_engine)

        @app.route("/test", methods=["POST"])
        def test_route() -> tuple[dict[str, str], int]:
            session = extension.get_session()
            assert isinstance(session, AsyncSession)
            user = User(name="test_async")  # type: ignore
            session.add(user)
            return {"status": "success"}, 200

        # Test successful response (should commit)
        response = client.post("/test")
        assert response.status_code == 200

        # Verify the data was committed
        session = extension.get_session()
        assert isinstance(session, AsyncSession)
        result = portal.call(session.execute, select(User).where(User.name == "test_async"))
        assert result.scalar_one().name == "test_async"


@pytest.mark.asyncio
async def test_async_autocommit_with_redirect(tmp_path: Path) -> None:
    """Test asynchronous autocommit with redirect functionality."""
    app = Flask(__name__)

    with app.test_client() as client:
        _ = User.__metadata_registry__.get(None)
        config = SQLAlchemyAsyncConfig(
            connection_string=f"sqlite+aiosqlite:///{tmp_path}/test_async_autocommit_with_redirect.db",
            commit_mode=CommitMode.AUTOCOMMIT_WITH_REDIRECT,
            metadata=User.__metadata_registry__.get(None),
            create_all=True,
        )
        extension = AdvancedAlchemy(config, app)
        User.__metadata_registry__.get(config.bind_key).create_all(config.get_engine().sync_engine)

        @app.route("/test", methods=["POST"])
        def test_route() -> tuple[str, int, dict[str, str]]:
            session = extension.get_session()
            assert isinstance(session, AsyncSession)
            user = User(name="test_async_redirect")  # type: ignore
            session.add(user)
            return "", 302, {"Location": "/redirected"}

        # Test redirect response (should commit with AUTOCOMMIT_WITH_REDIRECT)
        response = client.post("/test")
        assert response.status_code == 302

    session = extension.get_session()
    assert isinstance(session, AsyncSession)
    result = await session.execute(select(User).where(User.name == "test_async_redirect"))
    assert result.scalar_one().name == "test_async_redirect"
