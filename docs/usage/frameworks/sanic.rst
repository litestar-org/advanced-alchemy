==================
Sanic Integration
==================

Advanced Alchemy integrates with Sanic through :class:`~advanced_alchemy.extensions.sanic.AdvancedAlchemy` (a ``sanic-ext`` ``Extension``), managing engines on ``app.ctx``, request-scoped sessions on ``request.ctx``, dependency injection via ``sanic-ext``, and bind-key lookups for both async and sync SQLAlchemy configurations.

Basic Setup
-----------

Configure a Sanic ``app`` with :class:`~advanced_alchemy.extensions.sanic.SQLAlchemyAsyncConfig` or :class:`~advanced_alchemy.extensions.sanic.SQLAlchemySyncConfig`, register the extension, and wire ``AsyncSession`` into Sanic's dependency injector:

.. code-block:: python

    from sanic import Sanic
    from sqlalchemy.ext.asyncio import AsyncSession

    from advanced_alchemy.extensions.sanic import (
        AdvancedAlchemy,
        AsyncSessionConfig,
        SQLAlchemyAsyncConfig,
    )

    alchemy_config = SQLAlchemyAsyncConfig(
        connection_string="sqlite+aiosqlite:///:memory:",
        session_config=AsyncSessionConfig(expire_on_commit=False),
        create_all=True,
    )

    app = Sanic("AlchemySanicApp")
    alchemy = AdvancedAlchemy(sqlalchemy_config=alchemy_config)
    alchemy.register(app)
    alchemy.add_session_dependency(AsyncSession)

Services, Dependencies, and Route Handlers
------------------------------------------

Register custom service or pagination dependency providers with ``app.ext.add_dependency(...)`` or access the request-scoped session directly with ``alchemy.get_async_session(request)``:

.. code-block:: python

    from uuid import UUID

    import msgspec
    from sanic import HTTPResponse, Request, raw
    from sqlalchemy.orm import Mapped

    from advanced_alchemy.extensions.sanic import base, filters, repository, service


    class AuthorModel(base.UUIDBase):
        __tablename__ = "sanic_author"

        name: Mapped[str]


    class AuthorSchema(msgspec.Struct):
        id: UUID
        name: str


    class AuthorService(service.SQLAlchemyAsyncRepositoryService[AuthorModel]):
        class Repo(repository.SQLAlchemyAsyncRepository[AuthorModel]):
            model_type = AuthorModel

        repository_type = Repo


    async def provide_authors_service(db_session: AsyncSession) -> AuthorService:
        return AuthorService(session=db_session)


    @app.get("/authors")
    async def list_authors(request: Request, db_session: AsyncSession) -> HTTPResponse:
        current_page = int(request.args.get("currentPage", 1))
        page_size = int(request.args.get("pageSize", 10))
        limit_offset = filters.LimitOffset(limit=page_size, offset=page_size * (current_page - 1))

        authors_service = await provide_authors_service(db_session)
        results, total = await authors_service.get_many_and_count(limit_offset)
        pagination = authors_service.to_schema(
            results,
            total,
            filters=[limit_offset],
            schema_type=AuthorSchema,
        )
        return raw(msgspec.json.encode(pagination), content_type="application/json")

Use ``alchemy.get_session(request)`` when you want the same code path to support either sync or async configurations.

Multiple Binds
--------------

Register more than one SQLAlchemy configuration and select them by bind key:

.. code-block:: python

    from advanced_alchemy.extensions.sanic import SQLAlchemySyncConfig

    multi_app = Sanic("AlchemySanicMultiBindApp")
    alchemy = AdvancedAlchemy(
        sqlalchemy_config=[
            SQLAlchemyAsyncConfig(connection_string="sqlite+aiosqlite:///:memory:"),
            SQLAlchemySyncConfig(connection_string="sqlite+pysqlite:///:memory:", bind_key="reporting"),
        ],
        sanic_app=multi_app,
    )

    default_config = alchemy.get_config()
    reporting_config = alchemy.get_config("reporting")

    assert default_config.bind_key == "default"
    assert reporting_config.bind_key == "reporting"

Notes
-----

- Register the extension once per application with ``alchemy.register(app)`` or by passing ``sanic_app=app``.
- Request sessions are created lazily through ``get_session()`` / ``get_async_session()`` or injected via ``add_session_dependency()`` and tracked on ``request.ctx``.
- Engine objects are stored on ``app.ctx`` using each config's ``engine_key``.
