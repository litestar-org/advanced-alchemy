=====================
Starlette Integration
=====================

For lightweight ASGI services built on Starlette, ``AdvancedAlchemy`` manages engine startup/shutdown and attaches a request-scoped database session to ``request.state`` automatically.

What's Included for Starlette
-----------------------------

.. list-table::
   :header-rows: 1
   :widths: 28 46 26

   * - Feature
     - What It Gives You
     - Reference
   * - **Session Middleware**
     - Opens and cleans up a SQLAlchemy session on ``request.state`` for every HTTP request.
     - :doc:`API </reference/extensions/starlette/index>`
   * - **Commit Modes**
     - Supports manual commits, ``"autocommit"`` on ``2xx``, and ``"autocommit_include_redirect"``.
     - :doc:`API </reference/extensions/starlette/index>`
   * - **Multi-Database Binds**
     - Connects multiple sync or async databases in a single Starlette app via ``bind_key``.
     - :doc:`API </reference/extensions/starlette/index>`

Setup and Route Usage
---------------------

Attach ``AdvancedAlchemy`` to your ``Starlette`` app and grab the current request's session with ``alchemy.get_async_session(request)``:

.. tab-set::

    .. tab-item:: 1. App Setup

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

    .. tab-item:: 2. Models, Service & Routes

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
                page = int(request.query_params.get("currentPage", 1))
                size = int(request.query_params.get("pageSize", 10))
                limit_offset = filters.LimitOffset(limit=size, offset=size * (page - 1))

                authors_service = AuthorService(session=alchemy.get_async_session(request))
                results, total = await authors_service.get_many_and_count(limit_offset)
                payload = authors_service.to_schema(
                    results,
                    total,
                    filters=[limit_offset],
                    schema_type=AuthorSchema,
                )
                return Response(content=msgspec.json.encode(payload), media_type="application/json")


            async def healthcheck(request: Request) -> JSONResponse:
                db_session = alchemy.get_async_session(request)
                assert db_session is not None
                return JSONResponse({"dialect": alchemy.get_async_engine().dialect.name, "status": "ok"})


            app.router.routes.extend(
                [
                    Route("/authors", endpoint=list_authors, methods=["GET"]),
                    Route("/health", endpoint=healthcheck, methods=["GET"]),
                ],
            )

Commit Modes and Multiple Databases
-----------------------------------

.. tab-set::

    .. tab-item:: Commit on Redirects

        .. code-block:: python

            redirect_config = SQLAlchemyAsyncConfig(
                connection_string="sqlite+aiosqlite:///:memory:",
                commit_mode="autocommit_include_redirect",
            )
            redirect_app = Starlette()
            redirect_alchemy = AdvancedAlchemy(config=redirect_config, app=redirect_app)

    .. tab-item:: Multiple Databases

        .. code-block:: python

            from advanced_alchemy.extensions.starlette import SQLAlchemySyncConfig

            multi_db_app = Starlette()
            multi_alchemy = AdvancedAlchemy(
                config=[
                    SQLAlchemyAsyncConfig(connection_string="sqlite+aiosqlite:///:memory:"),
                    SQLAlchemySyncConfig(connection_string="sqlite+pysqlite:///:memory:", bind_key="reporting"),
                ],
                app=multi_db_app,
            )
            assert multi_alchemy.get_async_config().bind_key == "default"
            assert multi_alchemy.get_sync_config("reporting").bind_key == "reporting"

See :doc:`/reference/extensions/starlette/index` for full API signatures.
