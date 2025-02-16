# ruff: noqa: FA100
"""This example demonstrates how to use the FastAPI CLI to manage the database."""

# /// script
# dependencies = [
#   "advanced_alchemy",
#   "fastapi[standard]",
#   "orjson"
# ]
# ///
import datetime
from collections.abc import AsyncGenerator
from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, FastAPI
from pydantic import BaseModel
from sqlalchemy import ForeignKey
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column, relationship

from advanced_alchemy.extensions.fastapi import (
    AdvancedAlchemy,
    AsyncSessionConfig,
    SQLAlchemyAsyncConfig,
    base,
    filters,
    repository,
    service,
)

# Models
# #######################


class BookModel(base.UUIDAuditBase):
    __tablename__ = "book"
    title: Mapped[str]
    author_id: Mapped[UUID] = mapped_column(ForeignKey("author.id"))
    author: Mapped["AuthorModel"] = relationship(lazy="joined", innerjoin=True, viewonly=True)


# the SQLAlchemy base includes a declarative model for you to use in your models.
# The `Base` class includes a `UUID` based primary key (`id`)
class AuthorModel(base.UUIDBase):
    # we can optionally provide the table name instead of auto-generating it
    __tablename__ = "author"
    name: Mapped[str]
    dob: Mapped[Optional[datetime.date]]
    books: Mapped[list[BookModel]] = relationship(back_populates="author", lazy="selectin")


# The `AuditBase` class includes the same UUID` based primary key (`id`) and 2
# additional columns: `created` and `updated`. `created` is a timestamp of when the
# record created, and `updated` is the last time the record was modified.

# we will explicitly define the schema instead of using DTO objects for clarity.


class Author(BaseModel):
    id: Optional[UUID]
    name: str
    dob: Optional[datetime.date]


class AuthorCreate(BaseModel):
    name: str
    dob: Optional[datetime.date]


class AuthorUpdate(BaseModel):
    name: Optional[str]
    dob: Optional[datetime.date]


class AuthorService(service.SQLAlchemyAsyncRepositoryService[AuthorModel]):
    """Author repository."""

    class Repo(repository.SQLAlchemyAsyncRepository[AuthorModel]):
        """Author repository."""

        model_type = AuthorModel

    repository_type = Repo


# #######################
# Application
# #######################

sqlalchemy_config = SQLAlchemyAsyncConfig(
    connection_string="sqlite+aiosqlite:///test.sqlite",
    session_config=AsyncSessionConfig(expire_on_commit=False),
    create_all=True,
)
app = FastAPI()
alchemy = AdvancedAlchemy(config=sqlalchemy_config, app=app)
DatabaseSession = Annotated[AsyncSession, Depends(alchemy.provide_session())]

# #######################
# Dependencies
# #######################


async def provide_authors_service(db_session: DatabaseSession) -> AsyncGenerator[AuthorService, None]:
    """This provides the default Authors repository."""
    async with AuthorService.new(session=db_session) as service:
        yield service


# we can optionally override the default `select` used for the repository to pass in
# specific SQL options such as join details
async def provide_author_details_service(db_session: DatabaseSession) -> AsyncGenerator[AuthorService, None]:
    """This provides a simple example demonstrating how to override the join options for the repository."""
    async with AuthorService.new(load=[AuthorModel.books], session=db_session) as service:
        yield service


def provide_limit_offset_pagination(current_page: int = 1, page_size: int = 10) -> filters.LimitOffset:
    """Add offset/limit pagination.

    Return type consumed by `Repository.apply_limit_offset_pagination()`.

    Parameters
    ----------
    current_page : int
        LIMIT to apply to select.
    page_size : int
        OFFSET to apply to select.
    """
    return filters.LimitOffset(page_size, page_size * (current_page - 1))


# #######################
# Routes
# #######################
author_router = APIRouter()


@author_router.get(path="/authors", response_model=service.OffsetPagination[Author])
async def list_authors(
    authors_service: Annotated[AuthorService, Depends(provide_authors_service)],
    limit_offset: Annotated[filters.LimitOffset, Depends(provide_limit_offset_pagination)],
) -> service.OffsetPagination[AuthorModel]:
    """List authors."""
    results, total = await authors_service.list_and_count(limit_offset)
    return authors_service.to_schema(results, total, filters=[limit_offset])


@author_router.post(path="/authors", response_model=Author)
async def create_author(
    authors_service: Annotated[AuthorService, Depends(provide_authors_service)],
    data: AuthorCreate,
) -> AuthorModel:
    """Create a new author."""
    obj = await authors_service.create(data)
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
    obj = await authors_service.update(data, item_id=author_id)
    return authors_service.to_schema(obj)


@author_router.delete(path="/authors/{author_id}")
async def delete_author(
    authors_service: Annotated[AuthorService, Depends(provide_authors_service)],
    author_id: UUID,
) -> None:
    """Delete a author from the system."""
    _ = await authors_service.delete(author_id)


app.include_router(author_router)

if __name__ == "__main__":
    """Launches the FastAPI CLI with the database commands registered"""
    from fastapi_cli.cli import app as fastapi_cli_app  # pyright: ignore[reportUnknownVariableType]
    from typer.main import get_group

    from advanced_alchemy.extensions.fastapi.cli import register_database_commands

    click_app = get_group(fastapi_cli_app)  # pyright: ignore[reportUnknownArgumentType]
    click_app.add_command(register_database_commands(app))
    click_app()
