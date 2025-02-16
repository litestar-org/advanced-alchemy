# ruff: noqa: RUF029
"""Tests for the Flask extension."""

from __future__ import annotations

from collections.abc import Generator, Sequence
from pathlib import Path

import pytest
from flask import Flask, Response
from msgspec import Struct
from pydantic import BaseModel
from sqlalchemy import String, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from advanced_alchemy import base, mixins
from advanced_alchemy.exceptions import ImproperConfigurationError
from advanced_alchemy.extensions.flask import (
    AdvancedAlchemy,
    FlaskServiceMixin,
    SQLAlchemyAsyncConfig,
    SQLAlchemySyncConfig,
)
from advanced_alchemy.repository import SQLAlchemyAsyncRepository, SQLAlchemySyncRepository
from advanced_alchemy.service import SQLAlchemyAsyncRepositoryService, SQLAlchemySyncRepositoryService

metadata = base.metadata_registry.get("flask_testing")


class NewBigIntBase(mixins.BigIntPrimaryKey, base.CommonTableAttributes, DeclarativeBase):
    """Base model with a big integer primary key."""

    __metadata__ = metadata


class User(NewBigIntBase):
    """Test user model."""

    __tablename__ = "users_testing"

    name: Mapped[str] = mapped_column(String(50))


class UserSchema(Struct):
    """Test user pydantic model."""

    name: str


class UserPydantic(BaseModel):
    """Test user pydantic model."""

    name: str


class UserService(SQLAlchemySyncRepositoryService[User], FlaskServiceMixin):
    """Test user service."""

    class Repo(SQLAlchemySyncRepository[User]):
        model_type = User

    repository_type = Repo


class AsyncUserService(SQLAlchemyAsyncRepositoryService[User], FlaskServiceMixin):
    """Test user service."""

    class Repo(SQLAlchemyAsyncRepository[User]):
        model_type = User

    repository_type = Repo


@pytest.fixture(scope="session")
def tmp_path_session(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("test_extensions_flask")


@pytest.fixture(scope="session")
def setup_database(tmp_path_session: Path) -> Generator[Path, None, None]:
    # Create a new database for each test
    db_path = tmp_path_session / "test.db"
    config = SQLAlchemySyncConfig(connection_string=f"sqlite:///{db_path}", metadata=metadata)
    engine = config.get_engine()
    User._sa_registry.metadata.create_all(engine)  # pyright: ignore[reportPrivateUsage]
    with config.get_session() as session:
        assert isinstance(session, Session)
        table_exists = session.execute(text("SELECT COUNT(*) FROM users_testing")).scalar_one()
    assert table_exists >= 0
    yield db_path


def test_sync_extension_init(setup_database: Path) -> None:
    app = Flask(__name__)

    with app.app_context():
        config = SQLAlchemySyncConfig(connection_string=f"sqlite:///{setup_database}", metadata=metadata)
        extension = AdvancedAlchemy(config, app)
        assert "advanced_alchemy" in app.extensions
        session = extension.get_session()
        assert isinstance(session, Session)


def test_sync_extension_init_with_app(setup_database: Path) -> None:
    app = Flask(__name__)

    with app.app_context():
        config = SQLAlchemySyncConfig(connection_string=f"sqlite:///{setup_database}", metadata=metadata)
        extension = AdvancedAlchemy(config, app)
        assert "advanced_alchemy" in app.extensions
        session = extension.get_session()
        assert isinstance(session, Session)


def test_sync_extension_multiple_init(setup_database: Path) -> None:
    app = Flask(__name__)

    with (
        app.app_context(),
        pytest.raises(ImproperConfigurationError, match="Advanced Alchemy extension is already registered"),
    ):
        config = SQLAlchemySyncConfig(connection_string=f"sqlite:///{setup_database}", metadata=metadata)
        extension = AdvancedAlchemy(config, app)
        extension.init_app(app)


def test_async_extension_init(setup_database: Path) -> None:
    app = Flask(__name__)

    with app.app_context():
        config = SQLAlchemyAsyncConfig(
            bind_key="async", connection_string=f"sqlite+aiosqlite:///{setup_database}", metadata=metadata
        )
        extension = AdvancedAlchemy(config, app)
        assert "advanced_alchemy" in app.extensions
        session = extension.get_session("async")
        assert isinstance(session, AsyncSession)
        extension.portal_provider.stop()


def test_async_extension_init_single_config_no_bind_key(setup_database: Path) -> None:
    app = Flask(__name__)

    with app.app_context():
        config = SQLAlchemyAsyncConfig(connection_string=f"sqlite+aiosqlite:///{setup_database}", metadata=metadata)
        extension = AdvancedAlchemy(config, app)
        assert "advanced_alchemy" in app.extensions
        session = extension.get_session()
        assert isinstance(session, AsyncSession)
        extension.portal_provider.stop()


def test_async_extension_init_with_app(setup_database: Path) -> None:
    app = Flask(__name__)

    with app.app_context():
        config = SQLAlchemyAsyncConfig(
            bind_key="async", connection_string=f"sqlite+aiosqlite:///{setup_database}", metadata=metadata
        )
        extension = AdvancedAlchemy(config, app)
        assert "advanced_alchemy" in app.extensions
        session = extension.get_session("async")
        assert isinstance(session, AsyncSession)
        extension.portal_provider.stop()


def test_async_extension_multiple_init(setup_database: Path) -> None:
    app = Flask(__name__)

    with (
        app.app_context(),
        pytest.raises(ImproperConfigurationError, match="Advanced Alchemy extension is already registered"),
    ):
        config = SQLAlchemyAsyncConfig(
            connection_string=f"sqlite+aiosqlite:///{setup_database}", bind_key="async", metadata=metadata
        )
        extension = AdvancedAlchemy(config, app)
        extension.init_app(app)


def test_sync_and_async_extension_init(setup_database: Path) -> None:
    app = Flask(__name__)

    with app.app_context():
        extension = AdvancedAlchemy(
            [
                SQLAlchemySyncConfig(connection_string=f"sqlite:///{setup_database}"),
                SQLAlchemyAsyncConfig(
                    connection_string=f"sqlite+aiosqlite:///{setup_database}", bind_key="async", metadata=metadata
                ),
            ],
            app,
        )
        assert "advanced_alchemy" in app.extensions
        session = extension.get_session()
        assert isinstance(session, Session)


def test_multiple_binds(setup_database: Path) -> None:
    app = Flask(__name__)

    with app.app_context():
        extension = AdvancedAlchemy(
            [
                SQLAlchemySyncConfig(
                    connection_string=f"sqlite:///{setup_database}", bind_key="db1", metadata=metadata
                ),
                SQLAlchemySyncConfig(
                    connection_string=f"sqlite:///{setup_database}", bind_key="db2", metadata=metadata
                ),
            ],
            app,
        )

        session = extension.get_session("db1")
        assert isinstance(session, Session)
        session = extension.get_session("db2")
        assert isinstance(session, Session)


def test_multiple_binds_async(setup_database: Path) -> None:
    app = Flask(__name__)

    with app.app_context():
        configs: Sequence[SQLAlchemyAsyncConfig] = [
            SQLAlchemyAsyncConfig(
                connection_string=f"sqlite+aiosqlite:///{setup_database}", bind_key="db1", metadata=metadata
            ),
            SQLAlchemyAsyncConfig(
                connection_string=f"sqlite+aiosqlite:///{setup_database}", bind_key="db2", metadata=metadata
            ),
        ]
        extension = AdvancedAlchemy(configs, app)

        session = extension.get_session("db1")
        assert isinstance(session, AsyncSession)
        session = extension.get_session("db2")
        assert isinstance(session, AsyncSession)
        extension.portal_provider.stop()


def test_mixed_binds(setup_database: Path) -> None:
    app = Flask(__name__)

    with app.app_context():
        configs: Sequence[SQLAlchemyAsyncConfig | SQLAlchemySyncConfig] = [
            SQLAlchemySyncConfig(connection_string=f"sqlite:///{setup_database}", bind_key="sync", metadata=metadata),
            SQLAlchemyAsyncConfig(
                connection_string=f"sqlite+aiosqlite:///{setup_database}", bind_key="async", metadata=metadata
            ),
        ]
        extension = AdvancedAlchemy(configs, app)

        session = extension.get_session("sync")
        assert isinstance(session, Session)
        session.close()
        session = extension.get_session("async")
        assert isinstance(session, AsyncSession)
        extension.portal_provider.portal.call(session.close)
        extension.portal_provider.stop()


def test_sync_autocommit(setup_database: Path) -> None:
    app = Flask(__name__)

    with app.test_client() as client:
        config = SQLAlchemySyncConfig(
            connection_string=f"sqlite:///{setup_database}", commit_mode="autocommit", metadata=metadata
        )

        extension = AdvancedAlchemy(config, app)

        @app.route("/test", methods=["POST"])
        def test_route() -> tuple[dict[str, str], int]:
            session = extension.get_session()
            assert isinstance(session, Session)
            user = User(name="test")
            session.add(user)
            return {"status": "success"}, 200

        # Test successful response (should commit)
        response = client.post("/test")
        assert response.status_code == 200

        # Verify the data was committed
        session = extension.get_session()
        assert isinstance(session, Session)
        result = session.execute(select(User).where(User.name == "test"))
        assert result.scalar_one().name == "test"


def test_sync_autocommit_include_redirect(setup_database: Path) -> None:
    app = Flask(__name__)

    with app.test_client() as client:
        config = SQLAlchemySyncConfig(
            connection_string=f"sqlite:///{setup_database}",
            commit_mode="autocommit_include_redirect",
            metadata=metadata,
        )

        extension = AdvancedAlchemy(config, app)

        @app.route("/test", methods=["POST"])
        def test_route() -> tuple[str, int, dict[str, str]]:
            session = extension.get_session()
            assert isinstance(session, Session)
            session.add(User(name="test_redirect"))
            return "", 302, {"Location": "/redirected"}

        # Test redirect response (should commit with autocommit_include_redirect)
        response = client.post("/test")
        assert response.status_code == 302

        # Verify the data was committed
        session = extension.get_session()
        assert isinstance(session, Session)
        result = session.execute(select(User).where(User.name == "test_redirect"))
        assert result.scalar_one().name == "test_redirect"


def test_sync_no_autocommit_on_error(setup_database: Path) -> None:
    app = Flask(__name__)

    with app.test_client() as client:
        config = SQLAlchemySyncConfig(
            connection_string=f"sqlite:///{setup_database}", commit_mode="autocommit", metadata=metadata
        )
        extension = AdvancedAlchemy(config, app)

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


def test_async_autocommit(setup_database: Path) -> None:
    app = Flask(__name__)

    with app.test_client() as client:
        config = SQLAlchemyAsyncConfig(
            connection_string=f"sqlite+aiosqlite:///{setup_database}", commit_mode="autocommit", metadata=metadata
        )
        extension = AdvancedAlchemy(config, app)

        @app.route("/test", methods=["POST"])
        def test_route() -> tuple[dict[str, str], int]:
            session = extension.get_session()
            assert isinstance(session, AsyncSession)
            session.add(User(name="test_async"))
            return {"status": "success"}, 200

        # Test successful response (should commit)
        response = client.post("/test")
        assert response.status_code == 200

        # Verify the data was committed
        session = extension.get_session()
        assert isinstance(session, AsyncSession)

        result = extension.portal_provider.portal.call(session.execute, select(User).where(User.name == "test_async"))
        assert result.scalar_one().name == "test_async"
    extension.portal_provider.stop()


def test_async_autocommit_include_redirect(setup_database: Path) -> None:
    app = Flask(__name__)

    with app.test_client() as client:
        config = SQLAlchemyAsyncConfig(
            connection_string=f"sqlite+aiosqlite:///{setup_database}",
            commit_mode="autocommit_include_redirect",
            metadata=metadata,
        )
        extension = AdvancedAlchemy(config, app)

        @app.route("/test", methods=["POST"])
        def test_route() -> tuple[str, int, dict[str, str]]:
            session = extension.get_session()
            assert isinstance(session, AsyncSession)
            user = User(name="test_async_redirect")  # type: ignore
            session.add(user)
            return "", 302, {"Location": "/redirected"}

        # Test redirect response (should commit with autocommit_include_redirect)
        response = client.post("/test")
        assert response.status_code == 302
        session = extension.get_session()
        assert isinstance(session, AsyncSession)

        result = extension.portal_provider.portal.call(
            session.execute, select(User).where(User.name == "test_async_redirect")
        )
        assert result.scalar_one().name == "test_async_redirect"
    extension.portal_provider.stop()


def test_async_no_autocommit_on_error(setup_database: Path) -> None:
    app = Flask(__name__)

    with app.test_client() as client:
        config = SQLAlchemyAsyncConfig(
            connection_string=f"sqlite+aiosqlite:///{setup_database}", commit_mode="autocommit", metadata=metadata
        )

        extension = AdvancedAlchemy(config, app)

        @app.route("/test", methods=["POST"])
        def test_route() -> tuple[dict[str, str], int]:
            session = extension.get_session()
            assert isinstance(session, AsyncSession)
            user = User(name="test_async_error")  # type: ignore
            session.add(user)
            return {"error": "test async error"}, 500

        # Test error response (should not commit)
        response = client.post("/test")
        assert response.status_code == 500

        session = extension.get_session()
        assert isinstance(session, AsyncSession)

        async def get_user() -> User | None:
            result = await session.execute(select(User).where(User.name == "test_async_error"))
            return result.scalar_one_or_none()

        # Verify the data was not committed
        user = extension.portal_provider.portal.call(get_user)
        assert user is None
    extension.portal_provider.stop()


def test_async_portal_cleanup(setup_database: Path) -> None:
    app = Flask(__name__)

    with app.test_client() as client:
        config = SQLAlchemyAsyncConfig(
            connection_string=f"sqlite+aiosqlite:///{setup_database}", commit_mode="manual", metadata=metadata
        )
        extension = AdvancedAlchemy(config, app)

        @app.route("/test", methods=["POST"])
        def test_route() -> tuple[dict[str, str], int]:
            session = extension.get_session()
            assert isinstance(session, AsyncSession)
            user = User(name="test_async_cleanup")  # type: ignore
            session.add(user)
            return {"status": "success"}, 200

        # Test successful response (should not commit since we're using MANUAL mode)
        response = client.post("/test")
        assert response.status_code == 200
        session = extension.get_session()
        assert isinstance(session, AsyncSession)

        # Verify the data was not committed (MANUAL mode)
        result = extension.portal_provider.portal.call(
            session.execute, select(User).where(User.name == "test_async_cleanup")
        )
        assert result.first() is None
    extension.portal_provider.stop()


def test_async_portal_explicit_stop(setup_database: Path) -> None:
    app = Flask(__name__)

    with app.test_client() as client:
        config = SQLAlchemyAsyncConfig(
            connection_string=f"sqlite+aiosqlite:///{setup_database}",
            metadata=metadata,
            commit_mode="manual",
        )
        extension = AdvancedAlchemy(config, app)

        @app.route("/test", methods=["POST"])
        def test_route() -> tuple[dict[str, str], int]:
            session = extension.get_session()
            assert isinstance(session, AsyncSession)
            user = User(name="test_async_explicit_stop")  # type: ignore
            session.add(user)
            return {"status": "success"}, 200

        # Test successful response (should not commit since we're using MANUAL mode)
        response = client.post("/test")
        assert response.status_code == 200

    with app.app_context():
        session = extension.get_session()
        assert isinstance(session, AsyncSession)

        # Verify the data was not committed (MANUAL mode)
        result = extension.portal_provider.portal.call(
            session.scalar, select(User).where(User.name == "test_async_explicit_stop")
        )
        assert result is None
    extension.portal_provider.stop()


def test_async_portal_explicit_stop_with_commit(setup_database: Path) -> None:
    app = Flask(__name__)

    @app.route("/test", methods=["POST"])
    def test_route() -> tuple[dict[str, str], int]:
        session = extension.get_session()
        assert isinstance(session, AsyncSession)

        async def create_user() -> None:
            user = User(name="test_async_explicit_stop_with_commit")  # type: ignore
            session.add(user)
            await session.commit()  # type: ignore

        extension.portal_provider.portal.call(create_user)
        return {"status": "success"}, 200

    with app.test_client() as client:
        config = SQLAlchemyAsyncConfig(
            connection_string=f"sqlite+aiosqlite:///{setup_database}",
            metadata=metadata,
            commit_mode="manual",
        )
        extension = AdvancedAlchemy(config, app)

        # Test successful response
        response = client.post("/test")
        assert response.status_code == 200

        # Verify in a new session
        session = extension.get_session()
        assert isinstance(session, AsyncSession)

        async def get_user() -> User | None:
            async with session:
                result = await session.execute(select(User).where(User.name == "test_async_explicit_stop_with_commit"))
                return result.scalar_one_or_none()

        user = extension.portal_provider.portal.call(get_user)
        assert isinstance(user, User)
        assert user.name == "test_async_explicit_stop_with_commit"
    extension.portal_provider.stop()


def test_sync_service_jsonify_msgspec(setup_database: Path) -> None:
    app = Flask(__name__)

    with app.test_client() as client:
        config = SQLAlchemySyncConfig(
            connection_string=f"sqlite:///{setup_database}", metadata=metadata, commit_mode="autocommit"
        )

        extension = AdvancedAlchemy(config, app)

        @app.route("/test", methods=["POST"])
        def test_route() -> Response:
            service = UserService(extension.get_sync_session())
            user = service.create({"name": "service_test"})
            return service.jsonify(service.to_schema(user, schema_type=UserSchema))

        # Test successful response (should commit)
        response = client.post("/test")
        assert response.status_code == 200

        # Verify the data was committed
        session = extension.get_session()
        assert isinstance(session, Session)
        result = session.execute(select(User).where(User.name == "service_test"))
        assert result.scalar_one().name == "service_test"


def test_async_service_jsonify_msgspec(setup_database: Path) -> None:
    app = Flask(__name__)

    with app.test_client() as client:
        config = SQLAlchemyAsyncConfig(
            connection_string=f"sqlite+aiosqlite:///{setup_database}", metadata=metadata, commit_mode="autocommit"
        )
        extension = AdvancedAlchemy(config, app)

        @app.route("/test", methods=["POST"])
        def test_route() -> Response:
            service = AsyncUserService(extension.get_async_session())
            user = extension.portal_provider.portal.call(service.create, {"name": "async_service_test"})
            return service.jsonify(service.to_schema(user, schema_type=UserSchema))

        # Test successful response (should commit)
        response = client.post("/test")
        assert response.status_code == 200

        # Verify the data was committed
        session = extension.get_session()
        assert isinstance(session, AsyncSession)
        result = extension.portal_provider.portal.call(
            session.scalar, select(User).where(User.name == "async_service_test")
        )
        assert result
        assert result.name == "async_service_test"
    extension.portal_provider.stop()


def test_sync_service_jsonify_pydantic(setup_database: Path) -> None:
    app = Flask(__name__)

    with app.test_client() as client:
        config = SQLAlchemySyncConfig(
            connection_string=f"sqlite:///{setup_database}", metadata=metadata, commit_mode="autocommit"
        )
        extension = AdvancedAlchemy(config, app)

        @app.route("/test", methods=["POST"])
        def test_route() -> Response:
            service = UserService(extension.get_sync_session())
            user = service.create({"name": "test_sync_service_jsonify_pydantic"})
            return service.jsonify(service.to_schema(user, schema_type=UserPydantic))

        # Test successful response (should commit)
        response = client.post("/test")
        assert response.status_code == 200

        # Verify the data was committed
        session = extension.get_session()
        assert isinstance(session, Session)
        result = session.execute(select(User).where(User.name == "test_sync_service_jsonify_pydantic"))
        assert result.scalar_one().name == "test_sync_service_jsonify_pydantic"


def test_async_service_jsonify_pydantic(setup_database: Path) -> None:
    app = Flask(__name__)

    with app.test_client() as client:
        config = SQLAlchemyAsyncConfig(
            connection_string=f"sqlite+aiosqlite:///{setup_database}", metadata=metadata, commit_mode="autocommit"
        )
        extension = AdvancedAlchemy(config, app)

        @app.route("/test", methods=["POST"])
        def test_route() -> Response:
            service = AsyncUserService(extension.get_async_session())
            user = extension.portal_provider.portal.call(
                service.create, {"name": "test_async_service_jsonify_pydantic"}
            )
            return service.jsonify(service.to_schema(user, schema_type=UserPydantic))

        # Test successful response (should commit)
        response = client.post("/test")
        assert response.status_code == 200

        # Verify the data was committed
        session = extension.get_session()
        assert isinstance(session, AsyncSession)
        result = extension.portal_provider.portal.call(
            session.scalar, select(User).where(User.name == "test_async_service_jsonify_pydantic")
        )
        assert result
        assert result.name == "test_async_service_jsonify_pydantic"
    extension.portal_provider.stop()
