===================
Service Composition
===================

``ServiceGroup`` coordinates multiple services on one shared SQLAlchemy session so multi-model workflows commit or roll back as a single unit of work.

Defining a ServiceGroup
-----------------------

Declare a subclass of :class:`~advanced_alchemy.service.ServiceGroup` with type annotations for each member service:

.. code-block:: python

    import asyncio

    from sqlalchemy import ForeignKey, String
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

    from advanced_alchemy.config import SQLAlchemyAsyncConfig
    from advanced_alchemy.repository import SQLAlchemyAsyncRepository
    from advanced_alchemy.service import ServiceGroup, SQLAlchemyAsyncRepositoryService


    class Base(DeclarativeBase):
        pass


    class Role(Base):
        __tablename__ = "comp_role"
        id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
        name: Mapped[str] = mapped_column(String(50))


    class User(Base):
        __tablename__ = "comp_user"
        id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
        name: Mapped[str] = mapped_column(String(50))
        role_id: Mapped[int] = mapped_column(ForeignKey("comp_role.id"))


    class RoleRepo(SQLAlchemyAsyncRepository[Role]):
        model_type = Role


    class UserRepo(SQLAlchemyAsyncRepository[User]):
        model_type = User


    class RoleService(SQLAlchemyAsyncRepositoryService[Role, RoleRepo]):
        repository_type = RoleRepo


    class UserService(SQLAlchemyAsyncRepositoryService[User, UserRepo]):
        repository_type = UserRepo


    class AuthServices(ServiceGroup):
        session: AsyncSession
        roles: RoleService
        users: UserService

        async def provision_member(self, role_name: str, user_name: str) -> User:
            role = await self.roles.create({"name": role_name})
            return await self.users.create({"name": user_name, "role_id": role.id})


    async def main() -> None:
        config = SQLAlchemyAsyncConfig(connection_string="sqlite+aiosqlite:///:memory:")
        async with config.get_engine().begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with AuthServices.new(config=config) as services:
            await services.provision_member("admin", "ada")
            await services.session.commit()
            assert services.roles.repository.session is services.users.repository.session

        await config.get_engine().dispose()


    asyncio.run(main())

Every group must declare either asynchronous or synchronous services consistently. Non-service class attributes should use ``typing.ClassVar``. Annotating ``session`` refines editor typing without registering a service attribute.

Binding an Existing Session
---------------------------

When calling code already owns a session, instantiate ``AuthServices(session)`` or use ``AuthServices.new(session=session)``:

.. code-block:: python

    from sqlalchemy import String
    from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

    from advanced_alchemy.config import SQLAlchemySyncConfig
    from advanced_alchemy.repository import SQLAlchemySyncRepository
    from advanced_alchemy.service import ServiceGroup, SQLAlchemySyncRepositoryService


    class SyncBase(DeclarativeBase):
        pass


    class Account(SyncBase):
        __tablename__ = "comp_account"
        id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
        name: Mapped[str] = mapped_column(String(50))


    class AccountRepo(SQLAlchemySyncRepository[Account]):
        model_type = Account


    class AccountService(SQLAlchemySyncRepositoryService[Account, AccountRepo]):
        repository_type = AccountRepo


    class BillingServices(ServiceGroup):
        accounts: AccountService


    sync_config = SQLAlchemySyncConfig(connection_string="sqlite:///:memory:")
    with sync_config.get_engine().begin() as conn:
        SyncBase.metadata.create_all(conn)

    with sync_config.get_session() as session:
        billing = BillingServices(session)
        billing.accounts.create({"name": "acme"}, auto_commit=True)
        assert billing.accounts.repository.session is billing.session

    sync_config.get_engine().dispose()

Managed Member Lifetimes
------------------------

``Group.new(...)`` enters custom member ``.new()`` contexts and nested groups on the same session. Group options are forwarded when the factory accepts them, including explicit ``False`` values. Members close in reverse acquisition order; acquisition failures and cancellation reach previously entered contexts before propagating.

Direct ``Group(session, ...)`` construction calls member constructors only. Use ``.new()`` when members require managed setup or cleanup. A supplied session remains owned by the caller. Group acquisition shares a session but does not commit it automatically; commit explicitly or configure the session owner to manage transactions.

Litestar Integration
--------------------

Pass a ``ServiceGroup`` subclass to :func:`~advanced_alchemy.extensions.litestar.providers.create_service_dependencies` or :func:`~advanced_alchemy.extensions.litestar.providers.create_service_provider`, with optional per-attribute ``filters={attr_name: FilterConfig(...)}``:

.. code-block:: python

    from litestar import Controller, get
    from litestar.di import NamedDependency
    from litestar.params import SkipValidation
    from advanced_alchemy.extensions.litestar.providers import FilterConfig, create_service_dependencies
    from advanced_alchemy.filters import FilterTypes


    class AuthController(Controller):
        path = "/auth"
        dependencies = create_service_dependencies(
            AuthServices,
            key="auth",
            filters={"roles": FilterConfig(search="name"), "users": FilterConfig(search="name")},
        )

        @get("/")
        async def search(
            self,
            auth: AuthServices,
            roles_filters: NamedDependency[SkipValidation[list[FilterTypes]]],
            users_filters: NamedDependency[SkipValidation[list[FilterTypes]]],
        ) -> dict[str, int]:
            return {
                "roles": await auth.roles.count(*roles_filters),
                "users": await auth.users.count(*users_filters),
            }

FastAPI Integration
-------------------

Pass any ``ServiceGroup`` subclass directly to :meth:`~advanced_alchemy.extensions.fastapi.AdvancedAlchemy.provide_service`:

.. code-block:: python

    from typing import Annotated

    from fastapi import Depends, FastAPI
    from advanced_alchemy.extensions.fastapi import AdvancedAlchemy, SQLAlchemyAsyncConfig

    fastapi_app = FastAPI()
    async_cfg = SQLAlchemyAsyncConfig(connection_string="sqlite+aiosqlite:///:memory:", commit_mode="autocommit")
    alchemy = AdvancedAlchemy(config=async_cfg, app=fastapi_app)
    AuthDep = Annotated[AuthServices, Depends(alchemy.provide_service(AuthServices))]


    @fastapi_app.get("/users/count")
    async def user_count(auth: AuthDep) -> int:
        return await auth.users.count()
