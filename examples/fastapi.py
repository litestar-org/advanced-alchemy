from __future__ import annotations

from datetime import date  # noqa: TCH003
from typing import Annotated
from uuid import UUID  # noqa: TCH003

from fastapi import APIRouter, Depends, FastAPI, Request
from pydantic import BaseModel as _BaseModel
from pydantic import TypeAdapter
from sqlalchemy import ForeignKey, select
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: TCH002
from sqlalchemy.orm import Mapped, mapped_column, relationship, selectinload

from advanced_alchemy.base import UUIDAuditBase, UUIDBase
from advanced_alchemy.config import AsyncSessionConfig, SQLAlchemyAsyncConfig
from advanced_alchemy.extensions.starlette import StarletteAdvancedAlchemy
from advanced_alchemy.filters import LimitOffset
from advanced_alchemy.repository import SQLAlchemyAsyncRepository

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
    __tablename__ = "author"  #  type: ignore[assignment]
    name: Mapped[str]
    dob: Mapped[date | None]
    books: Mapped[list[BookModel]] = relationship(back_populates="author", lazy="noload")


# The `AuditBase` class includes the same UUID` based primary key (`id`) and 2
# additional columns: `created` and `updated`. `created` is a timestamp of when the
# record created, and `updated` is the last time the record was modified.
class BookModel(UUIDAuditBase):
    __tablename__ = "book"  #  type: ignore[assignment]
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


class AuthorPagination(BaseModel):
    """Container for data returned using limit/offset pagination."""

    items: list[Author]
    """List of data being sent as part of the response."""
    limit: int
    """Maximal number of items to send."""
    offset: int
    """Offset from the beginning of the query.

    Identical to an index.
    """
    total: int
    """Total number of items."""


class AuthorRepository(SQLAlchemyAsyncRepository[AuthorModel]):
    """Author repository."""

    model_type = AuthorModel


# #######################
# Dependencies
# #######################


async def provide_db_session(request: Request) -> AsyncSession:
    """Provide a DB session."""
    return alchemy.get_session(request)


async def provide_authors_repo(db_session: Annotated[AsyncSession, Depends(provide_db_session)]) -> AuthorRepository:
    """This provides the default Authors repository."""
    return AuthorRepository(session=db_session)


# we can optionally override the default `select` used for the repository to pass in
# specific SQL options such as join details
async def provide_author_details_repo(
    db_session: Annotated[AsyncSession, Depends(provide_db_session)],
) -> AuthorRepository:
    """This provides a simple example demonstrating how to override the join options for the repository."""
    return AuthorRepository(
        statement=select(AuthorModel).options(selectinload(AuthorModel.books)),
        session=db_session,
    )


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
    async with sqlalchemy_config.get_engine().begin() as conn:
        await conn.run_sync(UUIDBase.metadata.create_all)


# #######################
# Application
# #######################

session_config = AsyncSessionConfig(expire_on_commit=False)
sqlalchemy_config = SQLAlchemyAsyncConfig(
    connection_string="sqlite+aiosqlite:///test.sqlite",
    session_config=session_config,
)  # Create 'db_session' dependency.
app = FastAPI(on_startup=[on_startup])
alchemy = StarletteAdvancedAlchemy(config=sqlalchemy_config, app=app)

# #######################
# Routes
# #######################
author_router = APIRouter()


@author_router.get(path="/authors", response_model=AuthorPagination)
async def list_authors(
    authors_repo: Annotated[AuthorRepository, Depends(provide_authors_repo)],
    limit_offset: Annotated[LimitOffset, Depends(provide_limit_offset_pagination)],
) -> AuthorPagination:
    """List authors."""
    results, total = await authors_repo.list_and_count(limit_offset)
    type_adapter = TypeAdapter(list[Author])
    return AuthorPagination(
        items=type_adapter.validate_python(results),
        total=total,
        limit=limit_offset.limit,
        offset=limit_offset.offset,
    )


@author_router.post(path="/authors", response_model=Author)
async def create_author(
    authors_repo: Annotated[AuthorRepository, Depends(provide_authors_repo)],
    data: AuthorCreate,
) -> Author:
    """Create a new author."""
    obj = await authors_repo.add(
        AuthorModel(**data.model_dump(exclude_unset=True, exclude_none=True)),
    )
    await authors_repo.session.commit()
    return Author.model_validate(obj)


# we override the authors_repo to use the version that joins the Books in
@author_router.get(path="/authors/{author_id}", response_model=Author)
async def get_author(
    authors_repo: Annotated[AuthorRepository, Depends(provide_authors_repo)],
    author_id: UUID,
) -> Author:
    """Get an existing author."""
    obj = await authors_repo.get(author_id)
    return Author.model_validate(obj)


@author_router.patch(
    path="/authors/{author_id}",
    response_model=Author,
)
async def update_author(
    authors_repo: Annotated[AuthorRepository, Depends(provide_authors_repo)],
    data: AuthorUpdate,
    author_id: UUID,
) -> Author:
    """Update an author."""
    raw_obj = data.model_dump(exclude_unset=True, exclude_none=True)
    raw_obj.update({"id": author_id})
    obj = await authors_repo.update(AuthorModel(**raw_obj))
    await authors_repo.session.commit()
    return Author.model_validate(obj)


@author_router.delete(path="/authors/{author_id}")
async def delete_author(
    authors_repo: Annotated[AuthorRepository, Depends(provide_authors_repo)],
    author_id: UUID,
) -> None:
    """Delete a author from the system."""
    _ = await authors_repo.delete(author_id)
    await authors_repo.session.commit()


app.include_router(author_router)
