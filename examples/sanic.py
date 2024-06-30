from __future__ import annotations

from datetime import date  # noqa: TCH003
from typing import Any
from uuid import UUID  # noqa: TCH003

from sanic import Request, Sanic
from sanic_ext import Extend
from sqlalchemy import ForeignKey, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column, relationship, selectinload

from advanced_alchemy.base import UUIDAuditBase, UUIDBase
from advanced_alchemy.config import AsyncSessionConfig, SQLAlchemyAsyncConfig
from advanced_alchemy.extensions.sanic import SanicAdvancedAlchemy
from advanced_alchemy.filters import LimitOffset
from advanced_alchemy.repository import SQLAlchemyAsyncRepository


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


class AuthorRepository(SQLAlchemyAsyncRepository[AuthorModel]):
    """Author repository."""

    model_type = AuthorModel


# #######################
# Dependencies
# #######################


async def provide_db_session(request: Request) -> AsyncSession:
    """Provide a DB session."""
    return alchemy.get_session(request)


async def provide_authors_repo(db_session: AsyncSession) -> AuthorRepository:
    """This provides the default Authors repository."""
    return AuthorRepository(session=db_session)


# we can optionally override the default `select` used for the repository to pass in
# specific SQL options such as join details
async def provide_author_details_repo(
    db_session: AsyncSession,
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


# #######################
# Application
# #######################

session_config = AsyncSessionConfig(expire_on_commit=False)
sqlalchemy_config = SQLAlchemyAsyncConfig(
    connection_string="sqlite+aiosqlite:///test.sqlite",
    session_config=session_config,
)  # Create 'db_session' dependency.
app = Sanic("AlchemySanicApp")
alchemy = SanicAdvancedAlchemy(sqlalchemy_config=sqlalchemy_config)
Extend.register(alchemy)
app.ext.add_dependency(AsyncSession, provide_db_session)


@app.before_server_start
async def on_startup(app: Sanic, _: Any) -> None:  # noqa: ARG001
    """Initializes the database."""
    async with sqlalchemy_config.get_engine().begin() as conn:
        await conn.run_sync(UUIDBase.metadata.create_all)
