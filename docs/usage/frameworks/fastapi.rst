===================
FastAPI Integration
===================

Advanced Alchemy's repository and service patterns work well within FastAPI applications.

Basic Setup
-----------

Configure SQLAlchemy with FastAPI:

.. code-block:: python

    from typing import AsyncGenerator

    from fastapi import FastAPI

    from advanced_alchemy.extensions.fastapi import AdvancedAlchemy, AsyncSessionConfig, SQLAlchemyAsyncConfig

    sqlalchemy_config = SQLAlchemyAsyncConfig(
        connection_string="sqlite+aiosqlite:///test.sqlite",
        session_config=AsyncSessionConfig(expire_on_commit=False),
        create_all=True,
        commit_mode="autocommit",
    )

    app = FastAPI()
    alchemy = AdvancedAlchemy(config=sqlalchemy_config, app=app)

Models and Schemas
------------------

Define your SQLAlchemy models and Pydantic schemas:

.. code-block:: python

    import datetime
    from uuid import UUID
    from sqlalchemy import ForeignKey
    from sqlalchemy.orm import Mapped, mapped_column, relationship
    from pydantic import BaseModel as _BaseModel
    from advanced_alchemy.base import UUIDAuditBase, UUIDBase

    class BaseModel(_BaseModel):
        """Extend Pydantic's BaseModel to enable ORM mode"""
        model_config = {"from_attributes": True}

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

    class Author(BaseModel):
        id: UUID | None
        name: str
        dob: datetime.date | None = None

    class AuthorCreate(BaseModel):
        name: str
        dob: datetime.date | None = None

    class AuthorUpdate(BaseModel):
        name: str | None = None
        dob: datetime.date | None = None

Repository and Service
----------------------

Create repository and service classes:

.. code-block:: python

    from typing import Annotated, AsyncGenerator, Optional

    from advanced_alchemy.extensions.fastapi import repository, service
    from fastapi import Depends
    from sqlalchemy.ext.asyncio import AsyncSession


    class AuthorService(service.SQLAlchemyAsyncRepositoryService[AuthorModel]):
        """Author service."""

        class Repo(repository.SQLAlchemyAsyncRepository[AuthorModel]):
            """Author repository."""
            model_type = AuthorModel

        repository_type = Repo


Dependency Injection
--------------------

Set up dependency injected into the request context.

.. code-block:: python

    from fastapi import Request

    DatabaseSession = Annotated[AsyncSession, Depends(alchemy.provide_session())]
    Authors = Annotated[AuthorService, Depends(provide_authors_service)]

    async def provide_authors_service(db_session: DatabaseSession) -> AsyncGenerator[AuthorService, None]:
        """This provides the default Authors repository."""
        async with AuthorService.new(session=db_session) as service:
            yield service


Controllers
-----------

Create controllers using the service:

.. code-block:: python

    from fastapi import APIRouter, Depends
    from uuid import UUID
    from advanced_alchemy.extensions.fastapi import filters

    author_router = APIRouter()

    @author_router.get(path="/authors", response_model=filters.OffsetPagination[Author])
    async def list_authors(
        authors_service: Authors,
        limit_offset: Annotated[filters.LimitOffset, Depends(provide_limit_offset_pagination)],
    ) -> filters.OffsetPagination[AuthorModel]:
        """List authors."""
        results, total = await authors_service.list_and_count(limit_offset)
        return authors_service.to_schema(results, total, filters=[limit_offset])

    @author_router.post(path="/authors", response_model=Author)
    async def create_author(
        authors_service: Authors,
        data: AuthorCreate,
    ) -> AuthorModel:
        """Create a new author."""
        obj = await authors_service.create(data)
        return authors_service.to_schema(obj)

    @author_router.get(path="/authors/{author_id}", response_model=Author)
    async def get_author(
        authors_service: Authors,
        author_id: UUID,
    ) -> AuthorModel:
        """Get an existing author."""
        obj = await authors_service.get(author_id)
        return authors_service.to_schema(obj)

    @author_router.patch(path="/authors/{author_id}", response_model=Author)
    async def update_author(
        authors_service: Authors,
        data: AuthorUpdate,
        author_id: UUID,
    ) -> AuthorModel:
        """Update an author."""
        obj = await authors_service.update(data, item_id=author_id)
        return authors_service.to_schema(obj)

    @author_router.delete(path="/authors/{author_id}")
    async def delete_author(
        authors_service: Authors,
        author_id: UUID,
    ) -> None:
        """Delete an author from the system."""
        _ = await authors_service.delete(author_id)

Application Configuration
-------------------------

Finally, configure your FastAPI application with the router:

.. code-block:: python

    app.include_router(author_router)
