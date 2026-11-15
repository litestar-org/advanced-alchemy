from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Annotated, Any, ClassVar, Optional, Union
from unittest.mock import MagicMock

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient as FastAPITestClient
from litestar import Litestar, get
from litestar.params import Dependency
from litestar.testing import TestClient as LitestarTestClient
from sqlalchemy import ForeignKey, String, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

import advanced_alchemy.extensions.fastapi.providers as fastapi_providers
import advanced_alchemy.extensions.litestar.providers as litestar_providers
import advanced_alchemy.extensions.litestar.service as litestar_service
import advanced_alchemy.service as aa_service
from advanced_alchemy.config import AsyncSessionConfig
from advanced_alchemy.exceptions import ImproperConfigurationError
from advanced_alchemy.extensions.fastapi import AdvancedAlchemy as FastAPIAlchemy
from advanced_alchemy.extensions.fastapi import SQLAlchemyAsyncConfig as FastAPIAsyncConfig
from advanced_alchemy.extensions.fastapi import SQLAlchemySyncConfig as FastAPISyncConfig
from advanced_alchemy.extensions.litestar import SQLAlchemyAsyncConfig as LitestarAsyncConfig
from advanced_alchemy.extensions.litestar import SQLAlchemyPlugin
from advanced_alchemy.extensions.litestar import SQLAlchemySyncConfig as LitestarSyncConfig
from advanced_alchemy.extensions.litestar.providers import (
    FilterConfig,
    create_service_dependencies,
    create_service_provider,
)
from advanced_alchemy.filters import FilterTypes
from advanced_alchemy.repository import SQLAlchemyAsyncRepository, SQLAlchemySyncRepository
from advanced_alchemy.service import (
    Empty,
    ServiceGroup,
    SQLAlchemyAsyncQueryService,
    SQLAlchemyAsyncRepositoryReadService,
    SQLAlchemyAsyncRepositoryService,
    SQLAlchemySyncQueryService,
    SQLAlchemySyncRepositoryReadService,
    SQLAlchemySyncRepositoryService,
)

pytestmark = pytest.mark.unit


class GroupBase(DeclarativeBase):
    """Base declarative model for service group unit tests."""


class RoleModel(GroupBase):
    """Role model bound to GroupBase."""

    __tablename__ = "sg_role"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64))


class UserModel(GroupBase):
    """User model referencing RoleModel."""

    __tablename__ = "sg_user"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64))
    role_id: Mapped[int] = mapped_column(ForeignKey("sg_role.id"))


class AsyncRoleRepo(SQLAlchemyAsyncRepository[RoleModel]):
    """Async repository for RoleModel."""

    model_type = RoleModel


class AsyncUserRepo(SQLAlchemyAsyncRepository[UserModel]):
    """Async repository for UserModel."""

    model_type = UserModel


class SyncRoleRepo(SQLAlchemySyncRepository[RoleModel]):
    """Sync repository for RoleModel."""

    model_type = RoleModel


class SyncUserRepo(SQLAlchemySyncRepository[UserModel]):
    """Sync repository for UserModel."""

    model_type = UserModel


class AsyncRoleService(SQLAlchemyAsyncRepositoryService[RoleModel, AsyncRoleRepo]):
    """Async repository service for roles."""

    repository_type = AsyncRoleRepo


class AsyncUserService(SQLAlchemyAsyncRepositoryService[UserModel, AsyncUserRepo]):
    """Async repository service for users."""

    repository_type = AsyncUserRepo


class AsyncReadOnlyRoleService(SQLAlchemyAsyncRepositoryReadService[RoleModel, AsyncRoleRepo]):
    """Async read-only service for roles."""

    repository_type = AsyncRoleRepo


class SyncRoleService(SQLAlchemySyncRepositoryService[RoleModel, SyncRoleRepo]):
    """Sync repository service for roles."""

    repository_type = SyncRoleRepo


class SyncUserService(SQLAlchemySyncRepositoryService[UserModel, SyncUserRepo]):
    """Sync repository service for users."""

    repository_type = SyncUserRepo


class SyncReadOnlyRoleService(SQLAlchemySyncRepositoryReadService[RoleModel, SyncRoleRepo]):
    """Sync read-only service for roles."""

    repository_type = SyncRoleRepo


class PositionalOnlyCustomService:
    """Custom service accepting session as a positional-only parameter."""

    def __init__(self, session: Any, /) -> None:
        self.session = session


class VarKwCustomService:
    """Custom service accepting arbitrary keyword arguments."""

    def __init__(self, session: Any, **kwargs: Any) -> None:
        self.session = session
        self.extra = kwargs


class UninspectableCustomService:
    """Custom service whose constructor signature triggers TypeError fallback."""

    __signature__ = "invalid"

    def __init__(self, session: Any) -> None:
        self.session = session


class AsyncAuthServices(ServiceGroup):
    """Annotated asynchronous ServiceGroup for multi-service coordination."""

    label: ClassVar[str] = "auth"
    session: AsyncSession
    roles: AsyncRoleService
    users: AsyncUserService


class ExtendedAsyncServices(AsyncAuthServices):
    """Derived ServiceGroup extending parent fields."""

    readonly_roles: Annotated[AsyncReadOnlyRoleService, "read-only"]


class SyncAuthServices(ServiceGroup):
    """Annotated synchronous ServiceGroup for multi-service coordination."""

    session: Session
    roles: SyncRoleService
    users: SyncUserService


class ExtendedSyncServices(SyncAuthServices):
    """Derived synchronous ServiceGroup extending parent fields."""

    readonly_roles: Annotated[SyncReadOnlyRoleService, "read-only"]


class AsyncQueryOnlyServices(ServiceGroup):
    """ServiceGroup composing an async query service."""

    queries: SQLAlchemyAsyncQueryService


class SyncQueryOnlyServices(ServiceGroup):
    """ServiceGroup composing a sync query service."""

    queries: SQLAlchemySyncQueryService


class CustomInitGroup(ServiceGroup):
    """ServiceGroup composing custom plain classes without SQLAlchemy base classes."""

    positional: PositionalOnlyCustomService
    var_kw: VarKwCustomService
    fallback: UninspectableCustomService


class EmptyGroup(ServiceGroup):
    """ServiceGroup subclass intentionally declaring no services."""

    marker: ClassVar[str] = "empty"


@pytest.mark.parametrize(
    ("module", "expected_symbol", "removed_symbols"),
    [
        (
            aa_service,
            ServiceGroup,
            ("provide_services", "ServiceSpec", "AsyncServiceProvider", "SyncServiceProvider"),
        ),
        (
            litestar_service,
            ServiceGroup,
            ("provide_services", "ServiceSpec", "AsyncServiceProvider", "SyncServiceProvider"),
        ),
        (
            litestar_providers,
            ServiceGroup,
            ("provide_services", "ServiceSpec", "AsyncServiceProvider", "SyncServiceProvider"),
        ),
        (
            fastapi_providers,
            ServiceGroup,
            ("provide_services", "ServiceSpec", "AsyncServiceProvider", "SyncServiceProvider"),
        ),
    ],
)
def test_service_group_public_exports(
    module: Any,
    expected_symbol: type[ServiceGroup],
    removed_symbols: tuple[str, ...],
) -> None:
    """Verify ServiceGroup re-exports and removal of legacy composition helpers."""
    assert module.ServiceGroup is expected_symbol
    assert all(not hasattr(module, name) for name in removed_symbols)


async def test_async_service_group_direct_init_and_shared_transaction() -> None:
    """Instantiate an async ServiceGroup directly and commit across two services."""
    config = LitestarAsyncConfig(
        connection_string="sqlite+aiosqlite:///:memory:",
        session_config=AsyncSessionConfig(expire_on_commit=False),
    )
    async with config.get_engine().begin() as conn:
        await conn.run_sync(GroupBase.metadata.create_all)

    async with config.get_session() as session:
        auth = AsyncAuthServices(session, execution_options={"timeout": 5})
        assert auth.session is session
        assert auth.roles.repository.session is session
        assert auth.users.repository.session is session
        assert auth.roles.repository._default_execution_options == {"timeout": 5}
        assert AsyncAuthServices.label == "auth"
        assert set(AsyncAuthServices.service_fields()) == {"roles", "users"}
        assert isinstance(AsyncAuthServices.roles, object)

        role = await auth.roles.create({"name": "admin"})
        user = await auth.users.create({"name": "ada", "role_id": role.id})
        await auth.session.commit()

        assert await auth.users.count() == 1
        assert user.role_id == role.id

    await config.get_engine().dispose()


def test_sync_service_group_direct_init_and_shared_transaction() -> None:
    """Instantiate a sync ServiceGroup directly and commit across two services."""
    config = LitestarSyncConfig(connection_string="sqlite:///:memory:")
    with config.get_engine().begin() as conn:
        GroupBase.metadata.create_all(conn)

    with config.get_session() as session:
        auth = SyncAuthServices(session, uniquify=True)
        assert auth.session is session
        assert auth.roles.repository.session is session
        assert auth.users.repository.session is session
        assert auth.users.repository._uniquify is True

        role = auth.roles.create({"name": "editor"})
        user = auth.users.create({"name": "grace", "role_id": role.id})
        auth.session.commit()

        assert auth.users.count() == 1
        assert user.role_id == role.id

    config.get_engine().dispose()


@pytest.mark.parametrize("source", ["session", "config", "connection"])
async def test_async_service_group_context_acquisition_sources(source: str) -> None:
    """Acquire an async ServiceGroup via session, config, or connection."""
    config = LitestarAsyncConfig(
        connection_string="sqlite+aiosqlite:///:memory:",
        session_config=AsyncSessionConfig(expire_on_commit=False),
    )
    async with config.get_engine().begin() as conn:
        await conn.run_sync(GroupBase.metadata.create_all)

    if source == "config":
        async with ExtendedAsyncServices.new(config=config, error_messages=Empty) as services:
            assert services.roles.repository.session is services.users.repository.session
            assert services.readonly_roles.repository.session is services.session
            role = await services.roles.create({"name": "owner"})
            await services.session.commit()
            assert (await services.readonly_roles.get(role.id)).name == "owner"
    elif source == "session":
        async with config.get_session() as session:
            async with ExtendedAsyncServices.new(session=session) as services:
                assert services.session is session
                assert services.roles.repository.session is session
    else:
        async with config.get_session() as session:
            app_mock = MagicMock()
            app_mock.state = MagicMock()
            connection = MagicMock()
            connection.app = app_mock
            connection.scope = {"type": "http"}
            config.provide_session = MagicMock(return_value=session)  # type: ignore[method-assign]
            async with ExtendedAsyncServices.new(connection=connection, config=config) as services:
                assert services.session is session
                config.provide_session.assert_called_once()

    await config.get_engine().dispose()


@pytest.mark.parametrize("source", ["session", "config", "connection"])
def test_sync_service_group_context_acquisition_sources(source: str) -> None:
    """Acquire a sync ServiceGroup via session, config, or connection."""
    config = LitestarSyncConfig(connection_string="sqlite:///:memory:")
    with config.get_engine().begin() as conn:
        GroupBase.metadata.create_all(conn)

    if source == "config":
        with ExtendedSyncServices.new(config=config) as services:
            assert services.roles.repository.session is services.users.repository.session
            assert services.readonly_roles.repository.session is services.session
            role = services.roles.create({"name": "member"})
            services.session.commit()
            assert services.readonly_roles.get(role.id).name == "member"
    elif source == "session":
        with config.get_session() as session:
            with ExtendedSyncServices.new(session=session) as services:
                assert services.session is session
                assert services.roles.repository.session is session
    else:
        with config.get_session() as session:
            app_mock = MagicMock()
            app_mock.state = MagicMock()
            connection = MagicMock()
            connection.app = app_mock
            connection.scope = {"type": "http"}
            config.provide_session = MagicMock(return_value=session)  # type: ignore[method-assign]
            with ExtendedSyncServices.new(connection=connection, config=config) as services:
                assert services.session is session
                config.provide_session.assert_called_once()

    config.get_engine().dispose()


def test_local_function_service_group_with_future_annotations() -> None:
    """Resolve locally scoped service classes inside a function under postponed annotations."""
    ns: dict[str, Any] = {
        "ServiceGroup": ServiceGroup,
        "SyncRoleService": SyncRoleService,
        "PositionalOnlyCustomService": PositionalOnlyCustomService,
        "VarKwCustomService": VarKwCustomService,
        "UninspectableCustomService": UninspectableCustomService,
    }
    exec(
        (
            "from __future__ import annotations\n"
            "def _build_local_group():\n"
            "    class LocalServices(ServiceGroup):\n"
            "        roles: SyncRoleService\n"
            "        positional: PositionalOnlyCustomService\n"
            "        var_kw: VarKwCustomService\n"
            "        fallback: UninspectableCustomService\n"
            "    return LocalServices\n"
            "LocalServices = _build_local_group()\n"
        ),
        ns,
    )
    local_services_cls = ns["LocalServices"]

    config = LitestarSyncConfig(connection_string="sqlite:///:memory:")
    with config.get_engine().begin() as conn:
        GroupBase.metadata.create_all(conn)

    with config.get_session() as session:
        services = local_services_cls(session, uniquify=True)
        assert services.roles.repository.session is session
        assert services.positional.session is session
        assert services.var_kw.session is session
        assert services.var_kw.extra == {"uniquify": True}
        assert services.fallback.session is session
        assert local_services_cls.is_async_group() is False

    config.get_engine().dispose()


async def test_custom_async_new_context_cleanup_and_failure_unwind() -> None:
    """Enter custom async/sync service contexts and unwind cleanly when an error occurs."""
    events: list[str] = []

    class AsyncCustomContextService(SQLAlchemyAsyncQueryService):
        @classmethod
        @asynccontextmanager
        async def new(  # type: ignore[override]
            cls,
            session: Optional[AsyncSession] = None,
            config: Any = None,
            **kwargs: Any,
        ) -> AsyncIterator["AsyncCustomContextService"]:
            assert session is not None
            events.append("async_enter")
            try:
                yield cls(session=session)
            finally:
                events.append("async_exit")

    class SyncBridgeService:
        def __init__(self, session: Any) -> None:
            self.session = session

        @classmethod
        @contextmanager
        def new(cls, session: Any, **kwargs: Any) -> Iterator["SyncBridgeService"]:
            events.append("sync_enter")
            try:
                yield cls(session=session)
            finally:
                events.append("sync_exit")

    class DirectFactoryService:
        def __init__(self, session: Any) -> None:
            self.session = session

        @classmethod
        async def new(cls, session: Any, **kwargs: Any) -> "DirectFactoryService":
            events.append("direct_factory")
            return cls(session=session)

    class FailingSecondService:
        def __init__(self, session: Any) -> None:
            self.session = session

        @classmethod
        @asynccontextmanager
        async def new(cls, session: Any, **kwargs: Any) -> AsyncIterator["FailingSecondService"]:
            if session is not None:
                raise RuntimeError("boom during build")
            yield cls(session=session)

    class WorkingMixedCustomGroup(ServiceGroup):
        first: AsyncCustomContextService
        second: SyncBridgeService
        third: DirectFactoryService

    class FailingMixedCustomGroup(ServiceGroup):
        first: AsyncCustomContextService
        second: FailingSecondService

    config = LitestarAsyncConfig(connection_string="sqlite+aiosqlite:///:memory:")
    async with config.get_session() as session:
        async with WorkingMixedCustomGroup.new(session=session) as group:
            assert group.first.repository.session is session
            assert group.second.session is session
            assert group.third.session is session
        assert events == ["async_enter", "sync_enter", "direct_factory", "sync_exit", "async_exit"]

        events.clear()
        with pytest.raises(RuntimeError, match="boom during build"):
            async with FailingMixedCustomGroup.new(session=session):
                pass
        assert events == ["async_enter", "async_exit"]

    await config.get_engine().dispose()


def test_custom_sync_new_context_cleanup_and_async_factory_rejection() -> None:
    """Enter sync custom contexts cleanly and reject async custom factories in sync groups."""
    events: list[str] = []

    class SyncCustomService(SQLAlchemySyncQueryService):
        @classmethod
        @contextmanager
        def new(  # type: ignore[override]
            cls,
            session: Optional[Session] = None,
            config: Any = None,
            **kwargs: Any,
        ) -> Iterator["SyncCustomService"]:
            assert session is not None
            events.append("sync_enter")
            try:
                yield cls(session=session)
            finally:
                events.append("sync_exit")

    class SyncDirectService:
        def __init__(self, session: Any) -> None:
            self.session = session

        @classmethod
        def new(cls, session: Any, **kwargs: Any) -> "SyncDirectService":
            events.append("sync_direct")
            return cls(session=session)

    class AsyncFactoryService:
        def __init__(self, session: Any) -> None:
            self.session = session

        @classmethod
        def new(cls, session: Any, **kwargs: Any) -> Any:
            @asynccontextmanager
            async def _cm() -> AsyncIterator["AsyncFactoryService"]:
                yield cls(session=session)

            return _cm()

    class SyncCustomGroup(ServiceGroup):
        first: SyncCustomService
        second: SyncDirectService

    class InvalidSyncGroup(ServiceGroup):
        first: SyncCustomService
        bad: AsyncFactoryService

    config = LitestarSyncConfig(connection_string="sqlite:///:memory:")
    with config.get_session() as session:
        with SyncCustomGroup.new(session=session) as group:
            assert group.first.repository.session is session
            assert group.second.session is session
        assert events == ["sync_enter", "sync_direct", "sync_exit"]

        events.clear()
        with pytest.raises(ImproperConfigurationError, match="async factory"):
            with InvalidSyncGroup.new(session=session):
                pass
        assert events == ["sync_enter", "sync_exit"]

    config.get_engine().dispose()


def test_service_group_definition_validation_errors() -> None:
    """Reject mixed sync/async, non-class, and unresolvable annotations at subclass creation."""
    with pytest.raises(ImproperConfigurationError, match="cannot mix async and sync"):

        class _MixedGroup(ServiceGroup):
            async_svc: AsyncRoleService
            sync_svc: SyncRoleService

    with pytest.raises(ImproperConfigurationError, match="must resolve to a service class"):

        class _NonClassGroup(ServiceGroup):
            bad_field: Union[int, str]  # type: ignore[misc]

    with pytest.raises(ImproperConfigurationError, match="Unable to resolve service annotation"):

        class _MissingSymbolGroup(ServiceGroup):
            bad_field: "UndefinedServiceSymbol"  # type: ignore[name-defined]  # noqa: F821


async def test_service_group_runtime_validation_errors() -> None:
    """Reject empty groups, mismatched session types, wrong context modes, and missing sources."""
    async_config = LitestarAsyncConfig(connection_string="sqlite+aiosqlite:///:memory:")
    sync_config = LitestarSyncConfig(connection_string="sqlite:///:memory:")

    async with async_config.get_session() as async_session:
        with sync_config.get_session() as sync_session:
            with pytest.raises(ImproperConfigurationError, match="declares no service attributes"):
                EmptyGroup(sync_session)
            with pytest.raises(ImproperConfigurationError, match="declares no service attributes"):
                EmptyGroup.new(config=sync_config)

            with pytest.raises(ImproperConfigurationError, match="requires an active"):
                SyncAuthServices(None)  # type: ignore[arg-type]

            with pytest.raises(ImproperConfigurationError, match="cannot accept a synchronous Session"):
                AsyncAuthServices(sync_session)  # type: ignore[arg-type]

            with pytest.raises(ImproperConfigurationError, match="cannot accept an asynchronous AsyncSession"):
                SyncAuthServices(async_session)  # type: ignore[arg-type]

            with pytest.raises(ImproperConfigurationError, match="Use 'async with' instead"):
                with AsyncAuthServices.new(config=async_config):
                    pass

            with pytest.raises(ImproperConfigurationError, match="Use 'with' instead"):
                async with SyncAuthServices.new(config=sync_config):
                    pass

            with pytest.raises(ImproperConfigurationError, match="synchronous Session cannot be used"):
                async with AsyncQueryOnlyServices.new(session=sync_session):
                    pass

            with pytest.raises(ImproperConfigurationError, match="asynchronous AsyncSession cannot be used"):
                with SyncQueryOnlyServices.new(session=async_session):
                    pass

            with pytest.raises(ImproperConfigurationError, match="synchronous session context"):
                async with AsyncQueryOnlyServices.new(config=sync_config):
                    pass

            with pytest.raises(ImproperConfigurationError, match="asynchronous session context"):
                with SyncQueryOnlyServices.new(config=async_config):
                    pass

            with pytest.raises(ImproperConfigurationError, match="valid config"):
                async with AsyncQueryOnlyServices.new(connection=MagicMock()):
                    pass

            with pytest.raises(ImproperConfigurationError, match="valid config"):
                with SyncQueryOnlyServices.new(connection=MagicMock()):
                    pass

            with pytest.raises(ImproperConfigurationError, match="One of session, config, or connection"):
                async with AsyncQueryOnlyServices.new():
                    pass

            with pytest.raises(ImproperConfigurationError, match="One of session, config, or connection"):
                with SyncQueryOnlyServices.new():
                    pass

            group = SyncAuthServices(sync_session)
            del group._instances["roles"]
            with pytest.raises(AttributeError, match="has no initialized service 'roles'"):
                _ = group.roles

    await async_config.get_engine().dispose()
    sync_config.get_engine().dispose()


def test_litestar_async_service_group_with_scoped_filters() -> None:
    """Inject an async ServiceGroup and isolated per-service filters in Litestar."""
    config = LitestarAsyncConfig(connection_string="sqlite+aiosqlite:///:memory:")

    @get(
        "/bootstrap-check",
        dependencies=create_service_dependencies(
            AsyncAuthServices,
            key="auth",
            filters={
                "roles": FilterConfig(search="name"),
                "users": FilterConfig(search="name"),
            },
        ),
    )
    async def list_filtered(
        auth: AsyncAuthServices,
        roles_filters: Annotated[list[FilterTypes], Dependency(skip_validation=True)],
        users_filters: Annotated[list[FilterTypes], Dependency(skip_validation=True)],
    ) -> dict[str, Any]:
        assert auth.roles.repository.session is auth.users.repository.session
        roles = await auth.roles.list(*roles_filters)
        users = await auth.users.list(*users_filters)
        return {
            "roles": [r.name for r in roles],
            "users": [u.name for u in users],
        }

    app = Litestar(route_handlers=[list_filtered], plugins=[SQLAlchemyPlugin(config=config)])
    with LitestarTestClient(app=app) as client:

        async def _seed() -> None:
            async with config.get_engine().begin() as conn:
                await conn.run_sync(GroupBase.metadata.create_all)
            async with AsyncAuthServices.new(config=config) as auth:
                admin = await auth.roles.create({"name": "admin"})
                viewer = await auth.roles.create({"name": "viewer"})
                await auth.users.create({"name": "ada", "role_id": admin.id})
                await auth.users.create({"name": "grace", "role_id": viewer.id})
                await auth.session.commit()

        with client.portal() as portal:
            portal.call(_seed)
        response = client.get("/bootstrap-check?rolesSearchString=adm&usersSearchString=grac")
        assert response.status_code == 200
        assert response.json() == {"roles": ["admin"], "users": ["grace"]}


def test_litestar_sync_service_group_provider_and_error_validation(tmp_path: Path) -> None:
    """Inject a sync ServiceGroup in Litestar and reject invalid group DI options."""
    db_path = tmp_path / "litestar_sync_group.db"
    config = LitestarSyncConfig(connection_string=f"sqlite:///{db_path}")
    with config.get_engine().begin() as conn:
        GroupBase.metadata.create_all(conn)

    @get(
        "/sync-auth",
        dependencies={"auth": create_service_provider(SyncAuthServices, config=config)},
    )
    def create_and_count(auth: SyncAuthServices) -> dict[str, int]:
        role = auth.roles.create({"name": "sync-role"})
        auth.users.create({"name": "sync-user", "role_id": role.id})
        auth.session.commit()
        return {"roles": auth.roles.count(), "users": auth.users.count()}

    app = Litestar(route_handlers=[create_and_count], plugins=[SQLAlchemyPlugin(config=config)])
    with LitestarTestClient(app=app) as client:
        response = client.get("/sync-auth")
        assert response.status_code == 200
        assert response.json() == {"roles": 1, "users": 1}

    config.get_engine().dispose()

    with pytest.raises(ImproperConfigurationError, match="statement"):
        create_service_provider(SyncAuthServices, statement=select(RoleModel))

    with pytest.raises(ImproperConfigurationError, match="load"):
        create_service_provider(SyncAuthServices, load=[])

    with pytest.raises(ImproperConfigurationError, match="map service attribute names"):
        create_service_dependencies(
            SyncAuthServices,
            key="auth",
            filters="invalid",  # type: ignore[arg-type]
        )

    with pytest.raises(ImproperConfigurationError, match="does not match any service attribute"):
        create_service_dependencies(
            SyncAuthServices,
            key="auth",
            filters=FilterConfig(id_filter=int),  # type: ignore[arg-type]
        )

    with pytest.raises(ImproperConfigurationError, match="does not match any service attribute"):
        create_service_dependencies(
            SyncAuthServices,
            key="auth",
            filters={"nonexistent": FilterConfig(id_filter=int)},
        )


@pytest.mark.parametrize("mode", ["async", "sync"])
def test_fastapi_service_group_dependency_lifecycle(mode: str, tmp_path: Path) -> None:
    """Provide async and sync ServiceGroups through FastAPI dependency injection."""
    fastapi_app = FastAPI()

    if mode == "async":
        async_cfg = FastAPIAsyncConfig(connection_string="sqlite+aiosqlite:///:memory:", commit_mode="autocommit")
        alchemy = FastAPIAlchemy(config=async_cfg, app=fastapi_app)

        @fastapi_app.post("/provision")
        async def provision_async(
            auth: Annotated[AsyncAuthServices, Depends(alchemy.provide_service(AsyncAuthServices))],
        ) -> dict[str, Any]:
            assert auth.roles.repository.session is auth.users.repository.session
            role = await auth.roles.create({"name": "fastapi-admin"})
            user = await auth.users.create({"name": "linus", "role_id": role.id})
            return {"role": role.name, "user": user.name}

        @fastapi_app.get("/counts")
        async def counts_async(
            auth: Annotated[AsyncAuthServices, Depends(alchemy.provide_service(AsyncAuthServices))],
        ) -> dict[str, int]:
            return {"roles": await auth.roles.count(), "users": await auth.users.count()}

        with FastAPITestClient(fastapi_app) as client:

            async def _create_schema() -> None:
                async with async_cfg.get_engine().begin() as conn:
                    await conn.run_sync(GroupBase.metadata.create_all)

            assert client.portal is not None
            client.portal.call(_create_schema)
            assert client.post("/provision").json() == {"role": "fastapi-admin", "user": "linus"}
            assert client.get("/counts").json() == {"roles": 1, "users": 1}
            client.portal.call(async_cfg.get_engine().dispose)
    else:
        db_path = tmp_path / "fastapi_sync_group.db"
        sync_cfg = FastAPISyncConfig(connection_string=f"sqlite:///{db_path}", commit_mode="autocommit")
        with sync_cfg.get_engine().begin() as conn:
            GroupBase.metadata.create_all(conn)
        alchemy = FastAPIAlchemy(config=sync_cfg, app=fastapi_app)

        @fastapi_app.post("/provision")
        def provision_sync(
            auth: Annotated[SyncAuthServices, Depends(alchemy.provide_service(SyncAuthServices))],
        ) -> dict[str, Any]:
            assert auth.roles.repository.session is auth.users.repository.session
            role = auth.roles.create({"name": "fastapi-sync"})
            user = auth.users.create({"name": "guido", "role_id": role.id})
            return {"role": role.name, "user": user.name}

        @fastapi_app.get("/counts")
        def counts_sync(
            auth: Annotated[SyncAuthServices, Depends(alchemy.provide_service(SyncAuthServices))],
        ) -> dict[str, int]:
            return {"roles": auth.roles.count(), "users": auth.users.count()}

        with FastAPITestClient(fastapi_app) as client:
            assert client.post("/provision").json() == {"role": "fastapi-sync", "user": "guido"}
            assert client.get("/counts").json() == {"roles": 1, "users": 1}

        sync_cfg.get_engine().dispose()


def test_fastapi_custom_group_fallback_and_validation(tmp_path: Path) -> None:
    """Resolve undetermined FastAPI ServiceGroups via session generator inspection and reject invalid kwargs."""
    fastapi_app = FastAPI()
    db_path = tmp_path / "fastapi_custom_group.db"
    sync_cfg = FastAPISyncConfig(connection_string=f"sqlite:///{db_path}")
    alchemy = FastAPIAlchemy(config=sync_cfg, app=fastapi_app)

    @fastapi_app.get("/custom")
    def read_custom(
        custom: Annotated[CustomInitGroup, Depends(alchemy.provide_service(CustomInitGroup))],
    ) -> dict[str, bool]:
        return {
            "shared": custom.positional.session is custom.var_kw.session is custom.fallback.session is custom.session,
        }

    with FastAPITestClient(fastapi_app) as client:
        assert client.get("/custom").json() == {"shared": True}

    sync_cfg.get_engine().dispose()

    with pytest.raises(ImproperConfigurationError, match="statement"):
        alchemy.provide_service(CustomInitGroup, statement=select(RoleModel))

    with pytest.raises(ImproperConfigurationError, match="load"):
        alchemy.provide_service(CustomInitGroup, load=[])


@pytest.mark.parametrize("failure", [RuntimeError, BaseException])
@pytest.mark.parametrize("failure_stage", ["factory", "init", "nested"])
@pytest.mark.parametrize("cleanup_raises", [False, True])
def test_group_acquisition_failure_reaches_managed_contexts(
    failure: type[BaseException], failure_stage: str, cleanup_raises: bool
) -> None:
    events: list[tuple[str, type[BaseException]]] = []

    class Managed:
        @classmethod
        @contextmanager
        def new(cls, session: Any) -> Iterator[Any]:
            try:
                yield cls()
            except BaseException as exc:
                events.append(("service", type(exc)))
                if cleanup_raises:
                    raise ValueError("cleanup") from exc
                raise

    class BrokenInit:
        def __init__(self, session: Any) -> None:
            raise failure("acquisition")

    class BrokenFactory:
        @classmethod
        @contextmanager
        def new(cls, session: Any) -> Iterator[Any]:
            if session is not None:
                raise failure("acquisition")
            yield cls()

    class Nested(ServiceGroup):
        broken: BrokenInit

    broken_type = {"factory": BrokenFactory, "init": BrokenInit, "nested": Nested}[failure_stage]

    Group = type("Group", (ServiceGroup,), {"__annotations__": {"managed": Managed, "broken": broken_type}})

    class Config:
        @contextmanager
        def get_session(self) -> Iterator[Session]:
            with Session() as session:
                try:
                    yield session
                except BaseException as exc:
                    events.append(("session", type(exc)))
                    raise

    expected_error = ValueError if cleanup_raises else failure
    with pytest.raises(expected_error):
        with Group.new(config=Config()):  # type: ignore[arg-type]
            pytest.fail("group acquisition must fail")
    assert events == [("service", failure), ("session", expected_error)]


@pytest.mark.parametrize("asynchronous", [False, True])
async def test_nested_group_factories_receive_options_and_unwind(asynchronous: bool) -> None:
    events: list[tuple[str, Any]] = []

    class Managed:
        def __init__(self, session: Any) -> None:
            self.session = session

        @classmethod
        @contextmanager
        def new(cls, session: Any, *, auto_commit: bool = True) -> Iterator[Any]:
            events.append(("enter", auto_commit))
            try:
                yield cls(session)
            finally:
                events.append(("exit", auto_commit))

    class Inner(ServiceGroup):
        managed: Managed

    class Outer(ServiceGroup):
        inner: Inner

    if asynchronous:
        async with AsyncSession() as async_session:
            async with Outer.new(session=async_session, auto_commit=False, uniquify=True) as group:
                assert group.inner.managed.session is async_session
                assert events == [("enter", False)]
    else:
        with Session() as session:
            with Outer.new(session=session, auto_commit=False, uniquify=True) as group:
                assert group.inner.managed.session is session
                assert events == [("enter", False)]
    assert events == [("enter", False), ("exit", False)]


def test_quoted_postponed_group_annotations() -> None:
    namespace = {"ServiceGroup": ServiceGroup, "Annotated": Annotated, "ClassVar": ClassVar}
    exec(
        "from __future__ import annotations\n"
        "def build():\n"
        "    class LocalService:\n"
        "        def __init__(self, session): self.session = session\n"
        "    class Group(ServiceGroup):\n"
        "        service: 'Annotated[LocalService, \\\"member\\\"]'\n"
        "        marker: 'ClassVar[str]' = 'ignored'\n"
        "    return Group, LocalService\n"
        "Group, LocalService = build()\n",
        namespace,
    )
    assert dict(namespace["Group"].service_fields()) == {"service": namespace["LocalService"]}


def test_litestar_group_provider_accepts_sync_config_subclass() -> None:
    class ApplicationDatabase(LitestarSyncConfig):
        pass

    config = ApplicationDatabase(connection_string="sqlite://")
    assert litestar_providers._is_async_provider_target(CustomInitGroup, config) is False


@pytest.mark.parametrize("failure_stage", ["factory", "init", "nested"])
@pytest.mark.parametrize("cleanup_raises", [False, True])
async def test_async_group_cancellation_unwinds_session_and_services(failure_stage: str, cleanup_raises: bool) -> None:
    from asyncio import CancelledError

    events: list[tuple[str, type[BaseException]]] = []

    class Managed:
        @classmethod
        @asynccontextmanager
        async def new(cls, session: Any) -> AsyncIterator[Any]:
            try:
                yield cls()
            except BaseException as exc:
                events.append(("service", type(exc)))
                if cleanup_raises:
                    raise ValueError("cleanup") from exc
                raise

    class BrokenInit:
        def __init__(self, session: Any) -> None:
            raise CancelledError("acquisition")

    class BrokenFactory:
        @classmethod
        @asynccontextmanager
        async def new(cls, session: Any) -> AsyncIterator[Any]:
            if session is not None:
                raise CancelledError("acquisition")
            yield cls()

    class Nested(ServiceGroup):
        broken: BrokenInit

    broken_type = {"factory": BrokenFactory, "init": BrokenInit, "nested": Nested}[failure_stage]

    Group = type("Group", (ServiceGroup,), {"__annotations__": {"managed": Managed, "broken": broken_type}})

    class Config:
        @asynccontextmanager
        async def get_session(self) -> AsyncIterator[AsyncSession]:
            async with AsyncSession() as session:
                try:
                    yield session
                except BaseException as exc:
                    events.append(("session", type(exc)))
                    raise

    expected_error = ValueError if cleanup_raises else CancelledError
    with pytest.raises(expected_error):
        async with Group.new(config=Config()):  # type: ignore[arg-type]
            pytest.fail("group acquisition must fail")
    assert events == [("service", CancelledError), ("session", expected_error)]


def test_direct_nested_groups_use_constructors_without_entering_factories() -> None:
    class Managed:
        def __init__(self, session: Any, *, auto_commit: bool = True) -> None:
            self.session = session
            self.auto_commit = auto_commit

        @classmethod
        def new(cls, session: Any) -> Any:
            pytest.fail("direct groups must not acquire factory contexts")

    class Nested(ServiceGroup):
        managed: Managed

    class Group(ServiceGroup):
        nested: Nested

    with Session() as session:
        group = Group(session, auto_commit=False)
        assert group.nested.managed.session is session
        assert group.nested.managed.auto_commit is False


@pytest.mark.parametrize("asynchronous", [False, True])
async def test_group_acquisition_failure_cannot_be_suppressed(asynchronous: bool) -> None:
    class Suppressing:
        @classmethod
        @contextmanager
        def new(cls, session: Any) -> Iterator[Any]:
            try:
                yield cls()
            except RuntimeError:
                pass

    class Broken:
        def __init__(self, session: Any) -> None:
            raise RuntimeError("acquisition")

    class Group(ServiceGroup):
        suppressing: Suppressing
        broken: Broken

    with pytest.raises(RuntimeError, match="acquisition"):
        if asynchronous:
            async with AsyncSession() as async_session:
                async with Group.new(session=async_session):
                    pytest.fail("group acquisition must fail")
        else:
            with Session() as session:
                with Group.new(session=session):
                    pytest.fail("group acquisition must fail")


def test_local_forward_reference_inside_annotated_group_field() -> None:
    class LocalService:
        def __init__(self, session: Any) -> None:
            self.session = session

    Group = type(
        "Group",
        (ServiceGroup,),
        {
            "__annotations__": {
                "service": Annotated["LocalService", "member"],
                "marker": "Annotated[ClassVar[str], 'metadata']",
            },
            "marker": "ignored",
        },
    )

    assert dict(Group.service_fields()) == {"service": LocalService}


@pytest.mark.parametrize("managed", [False, True])
def test_group_passes_session_positionally_before_variadic_options(managed: bool) -> None:
    class PositionalService:
        def __init__(self, db_session: Session, **options: Any) -> None:
            self.session = db_session
            self.options = options

    class FactoryService(PositionalService):
        @classmethod
        @contextmanager
        def new(cls, db_session: Session, **options: Any) -> Iterator["FactoryService"]:
            yield cls(db_session, **options)

    class KeywordService:
        def __init__(self, **options: Any) -> None:
            self.session = options.pop("session")
            self.options = options

    class Group(ServiceGroup):
        positional: PositionalService
        factory: FactoryService
        keyword: KeywordService

    with Session() as session:
        if managed:
            with Group.new(session=session, auto_commit=False) as group:
                assert group.positional.session is group.factory.session is group.keyword.session is session
                assert (
                    group.positional.options == group.factory.options == group.keyword.options == {"auto_commit": False}
                )
        else:
            group = Group(session, auto_commit=False)
            assert group.positional.session is group.factory.session is group.keyword.session is session
            assert group.positional.options == group.factory.options == group.keyword.options == {"auto_commit": False}
