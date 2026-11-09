=================
Sanic Integration
=================

Advanced Alchemy integrates with Sanic through ``sanic-ext``, managing engines on ``app.ctx``, creating lazy per-request sessions on ``request.ctx``, and injecting ``AsyncSession`` straight into route handlers.

What's Included for Sanic
-------------------------

.. list-table::
   :header-rows: 1
   :widths: 28 46 26

   * - Feature
     - What It Gives You
     - Reference
   * - **sanic-ext Injection**
     - Injects ``AsyncSession`` or ``Session`` directly into route parameters with ``add_session_dependency``.
     - :doc:`API </reference/extensions/sanic/index>`
   * - **Request Context Sessions**
     - Lazily opens one session per request on ``request.ctx`` and cleans it up when the response finishes.
     - :doc:`API </reference/extensions/sanic/index>`
   * - **Multiple Databases**
     - Supports multiple sync or async databases side by side using named ``bind_key`` configs.
     - :doc:`API </reference/extensions/sanic/index>`

Setup and Route Handlers
------------------------

.. tab-set::

    .. tab-item:: 1. Register Extension

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

    .. tab-item:: 2. Service & Route

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


            @app.get("/authors")
            async def list_authors(request: Request, db_session: AsyncSession) -> HTTPResponse:
                page = int(request.args.get("currentPage", 1))
                size = int(request.args.get("pageSize", 10))
                limit_offset = filters.LimitOffset(limit=size, offset=size * (page - 1))

                authors_service = AuthorService(session=db_session)
                results, total = await authors_service.get_many_and_count(limit_offset)
                payload = authors_service.to_schema(
                    results,
                    total,
                    filters=[limit_offset],
                    schema_type=AuthorSchema,
                )
                return raw(msgspec.json.encode(payload), content_type="application/json")

    .. tab-item:: 3. Multiple Databases

        .. code-block:: python

            from advanced_alchemy.extensions.sanic import SQLAlchemySyncConfig

            reporting_app = Sanic("AlchemySanicMultiBindApp")
            reporting_alchemy = AdvancedAlchemy(
                sqlalchemy_config=[
                    SQLAlchemyAsyncConfig(connection_string="sqlite+aiosqlite:///:memory:"),
                    SQLAlchemySyncConfig(connection_string="sqlite+pysqlite:///:memory:", bind_key="reporting"),
                ],
                sanic_app=reporting_app,
            )

            assert reporting_alchemy.get_config().bind_key == "default"
            assert reporting_alchemy.get_config("reporting").bind_key == "reporting"

See :doc:`/reference/extensions/sanic/index` for full API signatures.
