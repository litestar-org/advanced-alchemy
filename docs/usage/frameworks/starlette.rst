======================
Starlette Integration
======================

Advanced Alchemy integrates with Starlette through :class:`~advanced_alchemy.extensions.starlette.AdvancedAlchemy`, which initializes SQLAlchemy configurations, manages request-scoped sessions on ``request.state``, and exposes engine and session accessors for route handlers.

Basic Setup
-----------

Initialize the extension with a Starlette ``app`` and one or more SQLAlchemy configurations:

.. code-block:: python

    from starlette.applications import Starlette

    from advanced_alchemy.extensions.starlette import (
        AdvancedAlchemy,
        AsyncSessionConfig,
        SQLAlchemyAsyncConfig,
    )

    alchemy_config = SQLAlchemyAsyncConfig(
        connection_string="sqlite+aiosqlite:///:memory:",
        session_config=AsyncSessionConfig(expire_on_commit=False),
        commit_mode="autocommit",
        create_all=True,
    )

    app = Starlette()
    alchemy = AdvancedAlchemy(config=alchemy_config, app=app)

Working with Services, Filters, and Sessions in Routes
------------------------------------------------------

Use ``alchemy.get_async_session(request)`` (or ``alchemy.get_sync_session(request)``) inside Starlette route handlers to instantiate repository services, apply filters, and return serialized schemas:

.. code-block:: python

    from uuid import UUID

    import msgspec
    from sqlalchemy.orm import Mapped
    from starlette.requests import Request
    from starlette.responses import JSONResponse, Response
    from starlette.routing import Route

    from advanced_alchemy.extensions.starlette import base, filters, repository, service


    class AuthorModel(base.UUIDBase):
        __tablename__ = "starlette_author"

        name: Mapped[str]


    class AuthorSchema(msgspec.Struct):
        id: UUID
        name: str


    class AuthorService(service.SQLAlchemyAsyncRepositoryService[AuthorModel]):
        class Repo(repository.SQLAlchemyAsyncRepository[AuthorModel]):
            model_type = AuthorModel

        repository_type = Repo


    async def list_authors(request: Request) -> Response:
        current_page = int(request.query_params.get("currentPage", 1))
        page_size = int(request.query_params.get("pageSize", 10))
        limit_offset = filters.LimitOffset(limit=page_size, offset=page_size * (current_page - 1))

        authors_service = AuthorService(session=alchemy.get_async_session(request))
        results, total = await authors_service.get_many_and_count(limit_offset)
        pagination = authors_service.to_schema(
            results,
            total,
            filters=[limit_offset],
            schema_type=AuthorSchema,
        )
        return Response(content=msgspec.json.encode(pagination), media_type="application/json")


    async def healthcheck(request: Request) -> JSONResponse:
        db_session = alchemy.get_async_session(request)
        engine = alchemy.get_async_engine()
        assert db_session is not None
        return JSONResponse({"dialect": engine.dialect.name, "status": "ok"})


    app.router.routes.extend(
        [
            Route("/authors", endpoint=list_authors, methods=["GET"]),
            Route("/health", endpoint=healthcheck, methods=["GET"]),
        ]
    )

Commit Modes
------------

Starlette integration supports the same commit strategies as the core SQLAlchemy configurations:

.. code-block:: python

    alchemy_config = SQLAlchemyAsyncConfig(
        connection_string="sqlite+aiosqlite:///:memory:",
        commit_mode="autocommit_include_redirect",
    )

    app = Starlette()
    alchemy = AdvancedAlchemy(config=alchemy_config, app=app)

Multiple Binds
--------------

Provide a sequence of configurations when you need more than one bind key:

.. code-block:: python

    from advanced_alchemy.extensions.starlette import SQLAlchemySyncConfig

    app = Starlette()
    alchemy = AdvancedAlchemy(
        config=[
            SQLAlchemyAsyncConfig(connection_string="sqlite+aiosqlite:///:memory:"),
            SQLAlchemySyncConfig(connection_string="sqlite+pysqlite:///:memory:", bind_key="reporting"),
        ],
        app=app,
    )

    default_config = alchemy.get_async_config()
    reporting_config = alchemy.get_sync_config("reporting")
    assert default_config.bind_key == "default"
    assert reporting_config.bind_key == "reporting"

Notes
-----

- ``AdvancedAlchemy(config=..., app=app)`` calls ``init_app()`` for you.
- Sessions are stored on ``request.state`` and are reused within the same request.
- Use ``alchemy.get_session(request)`` when your code should support either sync or async configurations.
