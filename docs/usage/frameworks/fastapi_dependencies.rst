===================================
FastAPI Services and Filter Depends
===================================

FastAPI routes use ``Depends(...)`` to inject database sessions, services, and query parameters. Advanced Alchemy's ``AdvancedAlchemy`` extension builds these ``Depends`` callables for you and adds pagination, search, sorting, and date-range parameters straight into FastAPI's Swagger UI.

Injecting Sessions and Services
-------------------------------

Use ``alchemy.provide_session()`` when a route needs a raw SQLAlchemy session, or ``alchemy.provide_service(ServiceClass)`` when you want a ready-to-use service:

.. tab-set::

    .. tab-item:: Built-In Service Provider

        .. code-block:: python

            from typing import Annotated
            from fastapi import Depends, FastAPI
            from sqlalchemy.orm import Mapped
            from advanced_alchemy.extensions.fastapi import (
                AdvancedAlchemy,
                AsyncSessionConfig,
                SQLAlchemyAsyncConfig,
                base,
                repository,
                service,
            )


            class AuthorModel(base.UUIDBase):
                __tablename__ = "fastapi_dep_author"
                name: Mapped[str]


            class AuthorRepository(repository.SQLAlchemyAsyncRepository[AuthorModel]):
                model_type = AuthorModel


            class AuthorService(service.SQLAlchemyAsyncRepositoryService[AuthorModel, AuthorRepository]):
                repository_type = AuthorRepository


            app = FastAPI()
            alchemy = AdvancedAlchemy(
                config=SQLAlchemyAsyncConfig(
                    connection_string="sqlite+aiosqlite:///:memory:",
                    session_config=AsyncSessionConfig(expire_on_commit=False),
                    commit_mode="autocommit",
                    create_all=True,
                ),
                app=app,
            )

            AuthorsServiceDep = Annotated[AuthorService, Depends(alchemy.provide_service(AuthorService))]

    .. tab-item:: Custom Session Dependency

        .. code-block:: python

            from collections.abc import AsyncGenerator
            from sqlalchemy.ext.asyncio import AsyncSession


            async def provide_custom_authors(
                db_session: Annotated[AsyncSession, Depends(alchemy.provide_session())],
            ) -> AsyncGenerator[AuthorService, None]:
                async with AuthorService.new(session=db_session) as authors_service:
                    yield authors_service

Adding Search and Pagination to Swagger UI
------------------------------------------

Pass a ``FilterConfig`` dictionary to ``alchemy.provide_filters(...)`` to generate FastAPI ``Depends`` parameters for pagination, text search, sorting, and date filters:

.. code-block:: python

    from uuid import UUID
    from advanced_alchemy.extensions.fastapi import filters

    AuthorFiltersDep = Annotated[
        list[filters.FilterTypes],
        Depends(
            alchemy.provide_filters(
                {
                    "id_filter": UUID,
                    "search": "name",
                    "search_ignore_case": True,
                    "pagination_type": "limit_offset",
                    "pagination_size": 20,
                    "sort_field": "name",
                    "created_at": True,
                }
            )
        ),
    ]


    @app.get("/authors")
    async def list_authors(
        authors_service: AuthorsServiceDep,
        filters: AuthorFiltersDep,
    ) -> dict[str, int]:
        _, total = await authors_service.get_many_and_count(*filters)
        return {"total": total}

Related Guides
--------------

* :doc:`/usage/frameworks/fastapi` — FastAPI extension setup and complete runnable example.
* :doc:`/usage/frameworks/fastapi_storage` — Uploading files and connecting multiple databases.
* :doc:`/reference/extensions/fastapi/index` — FastAPI extension API reference.
