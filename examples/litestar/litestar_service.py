from __future__ import annotations

from typing import TYPE_CHECKING

from litestar import Litestar
from litestar.controller import Controller
from litestar.di import Provide
from litestar.handlers.http_handlers.decorators import delete, get, patch, post
from litestar.params import Parameter
from pydantic import BaseModel as _BaseModel
from sqlalchemy import ForeignKey, select
from sqlalchemy.orm import Mapped, mapped_column, relationship, selectinload

from advanced_alchemy.base import UUIDAuditBase, UUIDBase
from advanced_alchemy.extensions.litestar import (
    AsyncSessionConfig,
    SQLAlchemyAsyncConfig,
    SQLAlchemyPlugin,
    async_autocommit_before_send_handler,
)
from advanced_alchemy.filters import FilterTypes, LimitOffset
from advanced_alchemy.repository import SQLAlchemyAsyncRepository
from advanced_alchemy.service import OffsetPagination, SQLAlchemyAsyncRepositoryService

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from datetime import date
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession


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


async def provide_authors_service(db_session: AsyncSession) -> AsyncGenerator[AuthorService, None]:
    """This provides the default Authors repository."""
    async with AuthorService.new(
        session=db_session,
    ) as service:
        yield service


# we can optionally override the default `select` used for the repository to pass in
# specific SQL options such as join details
async def provide_author_details_service(db_session: AsyncSession) -> AsyncGenerator[AuthorService, None]:
    """This provides a simple example demonstrating how to override the join options for the repository."""
    async with AuthorService.new(
        statement=select(AuthorModel).options(selectinload(AuthorModel.books)),
        session=db_session,
    ) as service:
        yield service


def provide_limit_offset_pagination(
    current_page: int = Parameter(ge=1, query="currentPage", default=1, required=False),
    page_size: int = Parameter(
        query="pageSize",
        ge=1,
        default=10,
        required=False,
    ),
) -> FilterTypes:
    """Add offset/limit pagination.

    Parameters
    ----------
    current_page : int
        LIMIT to apply to select.
    page_size : int
        OFFSET to apply to select.
    """
    return LimitOffset(page_size, page_size * (current_page - 1))


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

    # we override the authors_repo to use the version that joins the Books in
    @get(path="/authors/{author_id:uuid}", dependencies={"authors_service": Provide(provide_author_details_service)})
    async def get_author(
        self,
        authors_service: AuthorService,
        author_id: UUID = Parameter(  # noqa: B008
            title="Author ID",
            description="The author to retrieve.",
        ),
    ) -> Author:
        """Get an existing author."""
        obj = await authors_service.get(author_id)
        return authors_service.to_schema(data=obj, schema_type=Author)

    @patch(
        path="/authors/{author_id:uuid}",
        dependencies={"authors_service": Provide(provide_author_details_service)},
    )
    async def update_author(
        self,
        authors_service: AuthorService,
        data: AuthorUpdate,
        author_id: UUID = Parameter(  # noqa: B008
            title="Author ID",
            description="The author to update.",
        ),
    ) -> Author:
        """Update an author."""
        obj = await authors_service.update(
            data.model_dump(exclude_unset=True, exclude_none=True),
            item_id=author_id,
            auto_commit=True,
        )
        return authors_service.to_schema(obj, schema_type=Author)

    @delete(path="/authors/{author_id:uuid}")
    async def delete_author(
        self,
        authors_service: AuthorService,
        author_id: UUID = Parameter(  # noqa: B008
            title="Author ID",
            description="The author to delete.",
        ),
    ) -> None:
        """Delete a author from the system."""
        _ = await authors_service.delete(author_id)


session_config = AsyncSessionConfig(expire_on_commit=False)
sqlalchemy_config = SQLAlchemyAsyncConfig(
    connection_string="sqlite+aiosqlite:///test.sqlite",
    before_send_handler=async_autocommit_before_send_handler,
    session_config=session_config,
    create_all=True,
)  # Create 'db_session' dependency.
sqlalchemy_plugin = SQLAlchemyPlugin(config=sqlalchemy_config)


app = Litestar(
    route_handlers=[AuthorController],
    plugins=[sqlalchemy_plugin],
    dependencies={"limit_offset": Provide(provide_limit_offset_pagination, sync_to_thread=False)},
)
