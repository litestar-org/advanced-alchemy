from __future__ import annotations

import datetime  # noqa: TC003
from uuid import UUID  # noqa: TC003

from sanic import Sanic
from sqlalchemy import ForeignKey
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column, relationship

from advanced_alchemy.extensions.sanic import (
    AdvancedAlchemy,
    AsyncSessionConfig,
    SQLAlchemyAsyncConfig,
    base,
    filters,
    repository,
    service,
)


# the SQLAlchemy base includes a declarative model for you to use in your models.
# The `Base` class includes a `UUID` based primary key (`id`)
class AuthorModel(base.UUIDBase):
    # we can optionally provide the table name instead of auto-generating it
    __tablename__ = "author"
    name: Mapped[str]
    dob: Mapped[datetime.date | None]
    books: Mapped[list[BookModel]] = relationship(back_populates="author", lazy="noload")


# The `AuditBase` class includes the same UUID` based primary key (`id`) and 2
# additional columns: `created` and `updated`. `created` is a timestamp of when the
# record created, and `updated` is the last time the record was modified.
class BookModel(base.UUIDAuditBase):
    __tablename__ = "book"
    title: Mapped[str]
    author_id: Mapped[UUID] = mapped_column(ForeignKey("author.id"))
    author: Mapped[AuthorModel] = relationship(lazy="joined", innerjoin=True, viewonly=True)


class AuthorService(service.SQLAlchemyAsyncRepositoryService[AuthorModel]):
    """Author service."""

    class Repo(repository.SQLAlchemyAsyncRepository[AuthorModel]):
        """Author repository."""

        model_type = AuthorModel

    repository_type = Repo


# #######################
# Dependencies
# #######################


async def provide_authors_service(db_session: AsyncSession) -> AuthorService:
    """This provides the default Authors repository."""
    return AuthorService(session=db_session)


# we can optionally override the default `select` used for the repository to pass in
# specific SQL options such as join details
async def provide_author_details_service(
    db_session: AsyncSession,
) -> AuthorService:
    """This provides a simple example demonstrating how to override the join options for the repository."""
    return AuthorService(load=[AuthorModel.books], session=db_session)


def provide_limit_offset_pagination(
    current_page: int = 1,
    page_size: int = 10,
) -> filters.LimitOffset:
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
# Application
# #######################

session_config = AsyncSessionConfig(expire_on_commit=False)
sqlalchemy_config = SQLAlchemyAsyncConfig(
    connection_string="sqlite+aiosqlite:///test.sqlite",
    session_config=session_config,
)  # Create 'db_session' dependency.
app = Sanic("AlchemySanicApp")
alchemy = AdvancedAlchemy(sqlalchemy_config=sqlalchemy_config)
alchemy.register(app)
alchemy.add_session_dependency(AsyncSession)
