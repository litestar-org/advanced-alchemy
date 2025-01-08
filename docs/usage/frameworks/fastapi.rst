===================
FastAPI Integration
===================

Advanced Alchemy provides integration with FastAPI through its repository and service patterns.

Basic Setup
-----------

Configure SQLAlchemy with FastAPI:

.. code-block:: python

    from contextlib import asynccontextmanager
    from typing import AsyncGenerator

    from fastapi import FastAPI

    from advanced_alchemy.config import AsyncSessionConfig, SQLAlchemyAsyncConfig
    from advanced_alchemy.base import metadata_registry
    from advanced_alchemy.extensions.starlette import StarletteAdvancedAlchemy

    session_config = AsyncSessionConfig(expire_on_commit=False)
    sqlalchemy_config = SQLAlchemyAsyncConfig(
        connection_string="sqlite+aiosqlite:///test.sqlite",
        session_config=session_config
    )

    @asynccontextmanager
    async def on_lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        """Initializes the database."""
        metadata = metadata_registry.get(sqlalchemy_config.bind_key)
        if sqlalchemy_config.create_all:
            async with sqlalchemy_config.get_engine().begin() as conn:
                await conn.run_sync(metadata.create_all)
        yield

    app = FastAPI(lifespan=on_lifespan)
    alchemy = StarletteAdvancedAlchemy(config=sqlalchemy_config, app=app)

Models and Schemas
------------------

Define your SQLAlchemy models and Pydantic schemas:

.. code-block:: python

    from datetime import date
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
        dob: date | None = None

    class AuthorCreate(BaseModel):
        name: str
        dob: date | None = None

    class AuthorUpdate(BaseModel):
        name: str | None = None
        dob: date | None = None

Repository and Service
----------------------

Create repository and service classes:

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

    async def provide_authors_service(
        db_session: Annotated[AsyncSession, Depends(provide_db_session)],
    ) -> AsyncGenerator[AuthorService, None]:
        """This provides the default Authors repository."""
        async with AuthorService.new(session=db_session) as service:
            yield service

Dependency Injection
--------------------

Set up dependency injection for the database session:

.. code-block:: python

    from fastapi import Request

    async def provide_db_session(request: Request) -> AsyncSession:
        """Provide a DB session."""
        return alchemy.get_session(request) # this is the `StarletteAdvancedAlchemy` object

Controllers
-----------

Create controllers using the service:

.. code-block:: python

    from fastapi import APIRouter, Depends
    from uuid import UUID
    from advanced_alchemy.filters import LimitOffset
    from advanced_alchemy.service import OffsetPagination

    author_router = APIRouter()

    @author_router.get(path="/authors", response_model=OffsetPagination[Author])
    async def list_authors(
        authors_service: Annotated[AuthorService, Depends(provide_authors_service)],
        limit_offset: Annotated[LimitOffset, Depends(provide_limit_offset_pagination)],
    ) -> OffsetPagination[AuthorModel]:
        """List authors."""
        results, total = await authors_service.list_and_count(limit_offset)
        return authors_service.to_schema(results, total, filters=[limit_offset])

    @author_router.post(path="/authors", response_model=Author)
    async def create_author(
        authors_service: Annotated[AuthorService, Depends(provide_authors_service)],
        data: AuthorCreate,
    ) -> AuthorModel:
        """Create a new author."""
        obj = await authors_service.create(data.model_dump(exclude_unset=True, exclude_none=True), auto_commit=True)
        return authors_service.to_schema(obj)

    @author_router.get(path="/authors/{author_id}", response_model=Author)
    async def get_author(
        authors_service: Annotated[AuthorService, Depends(provide_authors_service)],
        author_id: UUID,
    ) -> AuthorModel:
        """Get an existing author."""
        obj = await authors_service.get(author_id)
        return authors_service.to_schema(obj)

    @author_router.patch(path="/authors/{author_id}", response_model=Author)
    async def update_author(
        authors_service: Annotated[AuthorService, Depends(provide_authors_service)],
        data: AuthorUpdate,
        author_id: UUID,
    ) -> AuthorModel:
        """Update an author."""
        obj = await authors_service.update(
            data.model_dump(exclude_unset=True, exclude_none=True),
            item_id=author_id,
            auto_commit=True,
        )
        return authors_service.to_schema(obj)

    @author_router.delete(path="/authors/{author_id}")
    async def delete_author(
        authors_service: Annotated[AuthorService, Depends(provide_authors_service)],
        author_id: UUID,
    ) -> None:
        """Delete an author from the system."""
        _ = await authors_service.delete(author_id, auto_commit=True)

Application Configuration
-------------------------

Finally, configure your FastAPI application with the router:

.. code-block:: python

    app.include_router(author_router)
