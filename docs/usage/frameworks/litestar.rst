====================
Litestar Integration
====================

Advanced Alchemy provides first-class integration with Litestar through its SQLAlchemy plugin, repository, and service patterns.

Basic Setup
-----------

Configure the SQLAlchemy plugin with Litestar:

.. code-block:: python

    from litestar import Litestar
    from advanced_alchemy.extensions.litestar import (
        AsyncSessionConfig,
        SQLAlchemyAsyncConfig,
        SQLAlchemyPlugin,
    )

    session_config = AsyncSessionConfig(expire_on_commit=False)
    sqlalchemy_config = SQLAlchemyAsyncConfig(
        connection_string="sqlite+aiosqlite:///test.sqlite",
        before_send_handler="autocommit",
        session_config=session_config,
        create_all=True,
    )
    alchemy = SQLAlchemyPlugin(config=sqlalchemy_config)


SQLAlchemy Models
-----------------

Define your SQLAlchemy models:

.. code-block:: python

    from datetime import date
    from uuid import UUID
    from sqlalchemy import ForeignKey
    from sqlalchemy.orm import Mapped, mapped_column, relationship
    from litestar.plugins.sqlalchemy.base import UUIDAuditBase, UUIDBase


    class AuthorModel(UUIDBase):
        __tablename__ = "author"
        name: Mapped[str]
        dob: Mapped[date | None]
        books: Mapped[list[BookModel]] = relationship(back_populates="author", lazy="noload")

    class BookModel(UUIDAuditBase):
        __tablename__ = "book"
        title: Mapped[str]
        author_id: Mapped[UUID] = mapped_column(ForeignKey("author.id"))
        author: Mapped[AuthorModel] = relationship(lazy="joined", innerjoin=True, viewonly=True)

Pydantic Schemas
----------------

Define Pydantic schemas for your models:

.. code-block:: python

    from datetime import date
    from pydantic import BaseModel as _BaseModel
    from uuid import UUID


    class BaseModel(_BaseModel):
        """Extend Pydantic's BaseModel to enable ORM mode"""
        model_config = {"from_attributes": True}

    class Author(BaseModel):
        id: UUID | None
        name: str
        dob: date | None = None

    class AuthorCreate(BaseModel):
        name: str
        dob: date | None = None

    class AuthorUpdate(BaseModel):
        name: str | None = None
        dob: date | None = None

Repository and Service
----------------------

Create repository, service classes, and dependency injection provider function:

.. code-block:: python

    from sqlalchemy.ext.asyncio import AsyncSession
    from advanced_alchemy.repository import SQLAlchemyAsyncRepository
    from advanced_alchemy.service import SQLAlchemyAsyncRepositoryService
    from typing import AsyncGenerator

    class AuthorRepository(SQLAlchemyAsyncRepository[AuthorModel]):
        """Author repository."""
        model_type = AuthorModel

    class AuthorService(SQLAlchemyAsyncRepositoryService[AuthorModel]):
        """Author service."""
        repository_type = AuthorRepository

    async def provide_authors_service(db_session: AsyncSession) -> AsyncGenerator[AuthorService, None]:
        """This provides the default Authors repository."""
        async with AuthorService.new(session=db_session) as service:
            yield service

Controllers
-----------

Create controllers using the service:

.. code-block:: python

    from litestar.controller import Controller
    from litestar.handlers.http_handlers.decorators import get, post, patch, delete
    from litestar.params import Parameter
    from litestar.plugins.sqlalchemy.filters import LimitOffset
    from litestar.plugins.sqlalchemy.service import OffsetPagination

    from uuid import UUID

    class AuthorController(Controller):
        """Author CRUD"""

        dependencies = {"authors_service": Provide(provide_authors_service)}

        @get(path="/authors")
        async def list_authors(
            self,
            authors_service: AuthorService,
            limit_offset: LimitOffset,
        ) -> OffsetPagination[Author]:
            """List authors."""
            results, total = await authors_service.list_and_count(limit_offset)
            return authors_service.to_schema(
                data=results,
                total=total,
                filters=[limit_offset],
                schema_type=Author,
            )

        @post(path="/authors")
        async def create_author(
            self,
            authors_service: AuthorService,
            data: AuthorCreate,
        ) -> Author:
            """Create a new author."""
            obj = await authors_service.create(
                data.model_dump(exclude_unset=True, exclude_none=True),
            )
            return authors_service.to_schema(data=obj, schema_type=Author)

        @get(path="/authors/{author_id:uuid}")
        async def get_author(
            self,
            authors_service: AuthorService,
            author_id: UUID = Parameter(
                title="Author ID",
                description="The author to retrieve.",
            ),
        ) -> Author:
            """Get an existing author."""
            obj = await authors_service.get(author_id)
            return authors_service.to_schema(data=obj, schema_type=Author)

        @patch(path="/authors/{author_id:uuid}")
        async def update_author(
            self,
            authors_service: AuthorService,
            data: AuthorUpdate,
            author_id: UUID = Parameter(
                title="Author ID",
                description="The author to update.",
            ),
        ) -> Author:
            """Update an author."""
            obj = await authors_service.update(data=data, item_id=author_id)
            return authors_service.to_schema(obj, schema_type=Author)

        @delete(path="/authors/{author_id:uuid}")
        async def delete_author(
            self,
            authors_service: AuthorService,
            author_id: UUID = Parameter(
                title="Author ID",
                description="The author to delete.",
            ),
        ) -> None:
            """Delete an author from the system."""
            _ = await authors_service.delete(author_id)

Application Configuration
-------------------------

Finally, configure your Litestar application with the plugin and dependencies:

.. code-block:: python

    from litestar import Litestar
    from litestar.plugins.sqlalchemy.filters import FilterTypes, LimitOffset
    from litestar.plugins.sqlalchemy import (
        AsyncSessionConfig,
        SQLAlchemyAsyncConfig,
        SQLAlchemyPlugin,
    )

    session_config = AsyncSessionConfig(expire_on_commit=False)
    sqlalchemy_config = SQLAlchemyAsyncConfig(
        connection_string="sqlite+aiosqlite:///test.sqlite",
        before_send_handler="autocommit",
        session_config=session_config,
        create_all=True,
    )
    alchemy = SQLAlchemyPlugin(config=sqlalchemy_config)


    def provide_limit_offset_pagination(
        current_page: int = Parameter(ge=1, query="currentPage", default=1, required=False),
        page_size: int = Parameter(
            query="pageSize",
            ge=1,
            default=10,
            required=False,
        ),
    ) -> FilterTypes:
        """Add offset/limit pagination."""
        return LimitOffset(page_size, page_size * (current_page - 1))

    app = Litestar(
        route_handlers=[AuthorController],
        plugins=[alchemy],
        dependencies={"limit_offset": Provide(provide_limit_offset_pagination, sync_to_thread=False)},
    )


Litestar CLI & Alembic
----------------------

Advanced Alchemy provides a CLI for creating migrations and alembic configuration.

.. code-block:: bash

    litestar database init ./migrations # this should match the folder you use in your configuration
    litestar database make-migrations
    litestar database upgrade
    litestar run
