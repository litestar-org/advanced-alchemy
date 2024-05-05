from __future__ import annotations

from datetime import date  # noqa: TCH003
from typing import TYPE_CHECKING
from uuid import UUID  # noqa: TCH003

from fastapi import APIRouter, Depends, FastAPI, Request
from pydantic import BaseModel as _BaseModel
from sqlalchemy import ForeignKey, select
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: TCH002
from sqlalchemy.orm import Mapped, mapped_column, relationship, selectinload
from typing_extensions import Annotated

from advanced_alchemy.base import UUIDAuditBase, UUIDBase
from advanced_alchemy.config import AsyncSessionConfig, SQLAlchemyAsyncConfig
from advanced_alchemy.extensions.starlette import StarletteAdvancedAlchemy
from advanced_alchemy.filters import LimitOffset
from advanced_alchemy.repository import SQLAlchemyAsyncRepository
from advanced_alchemy.service import OffsetPagination, SQLAlchemyAsyncRepositoryService

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

# #######################
# Models
# #######################


class BaseModel(_BaseModel):
    """Extend Pydantic's BaseModel to enable ORM mode"""

    model_config = {"from_attributes": True}


# the SQLAlchemy base includes a declarative model for you to use in your models.
# The `Base` class includes a `UUID` based primary key (`id`)
class AuthorModel(UUIDBase):
    # we can optionally provide the table name instead of auto-generating it
    __tablename__ = "author"
    name: Mapped[str]
    dob: Mapped[date | None]
    books: Mapped[list[BookModel]] = relationship(back_populates="author", lazy="noload")


# The `AuditBase` class includes the same UUID` based primary key (`id`) and 2
# additional columns: `created` and `updated`. `created` is a timestamp of when the
# record created, and `updated` is the last time the record was modified.
class BookModel(UUIDAuditBase):
    __tablename__ = "book"
    title: Mapped[str]
    author_id: Mapped[UUID] = mapped_column(ForeignKey("author.id"))
    author: Mapped[AuthorModel] = relationship(lazy="joined", innerjoin=True, viewonly=True)


# we will explicitly define the schema instead of using DTO objects for clarity.


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


class AuthorRepository(SQLAlchemyAsyncRepository[AuthorModel]):
    """Author repository."""

    model_type = AuthorModel


class AuthorService(SQLAlchemyAsyncRepositoryService[AuthorModel]):
    """Author repository."""

    repository_type = AuthorRepository


# #######################
# Dependencies
# #######################


async def provide_db_session(request: Request) -> AsyncSession:
    """Provide a DB session."""
    return alchemy.get_session(request)


async def provide_authors_service(
    db_session: Annotated[AsyncSession, Depends(provide_db_session)],
) -> AsyncGenerator[AuthorService, None]:
    """This provides the default Authors repository."""
    async with AuthorService.new(
        session=db_session,
    ) as service:
        yield service


# we can optionally override the default `select` used for the repository to pass in
# specific SQL options such as join details
async def provide_author_details_service(
    db_session: Annotated[AsyncSession, Depends(provide_db_session)],
) -> AsyncGenerator[AuthorService, None]:
    """This provides a simple example demonstrating how to override the join options for the repository."""
    async with AuthorService.new(
        statement=select(AuthorModel).options(selectinload(AuthorModel.books)),
        session=db_session,
    ) as service:
        yield service


def provide_limit_offset_pagination(
    current_page: int = 1,
    page_size: int = 10,
) -> LimitOffset:
    """Add offset/limit pagination.

    Return type consumed by `Repository.apply_limit_offset_pagination()`.

    Parameters
    ----------
    current_page : int
        LIMIT to apply to select.
    page_size : int
        OFFSET to apply to select.
    """
    return LimitOffset(page_size, page_size * (current_page - 1))


async def on_startup() -> None:
    """Initializes the database."""
    if sqlalchemy_config.create_all:
        async with sqlalchemy_config.get_engine().begin() as conn:
            await conn.run_sync(UUIDBase.metadata.create_all)


# #######################
# Application
# #######################

session_config = AsyncSessionConfig(expire_on_commit=False)
sqlalchemy_config = SQLAlchemyAsyncConfig(
    connection_string="sqlite+aiosqlite:///test.sqlite",
    session_config=session_config,
    create_all=True,
)  # Create 'db_session' dependency.
app = FastAPI(on_startup=[on_startup])
alchemy = StarletteAdvancedAlchemy(config=sqlalchemy_config, app=app)

# #######################
# Routes
# #######################
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


# we override the authors_repo to use the version that joins the Books in
@author_router.get(path="/authors/{author_id}", response_model=Author)
async def get_author(
    authors_service: Annotated[AuthorService, Depends(provide_authors_service)],
    author_id: UUID,
) -> AuthorModel:
    """Get an existing author."""
    obj = await authors_service.get(author_id)
    return authors_service.to_schema(obj)


@author_router.patch(
    path="/authors/{author_id}",
    response_model=Author,
)
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
    """Delete a author from the system."""
    _ = await authors_service.delete(author_id, auto_commit=True)


app.include_router(author_router)
