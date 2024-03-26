from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, List, Union
from uuid import UUID

from litestar import Litestar
from litestar.controller import Controller
from litestar.di import Provide
from litestar.exceptions import NotFoundException as LiteStarNotFoundException
from litestar.handlers.http_handlers.decorators import delete, get, patch, post
from litestar.pagination import OffsetPagination
from litestar.params import Parameter
from sqlalchemy import ForeignKey, select
from sqlalchemy.orm import Mapped, mapped_column, relationship, selectinload
from typing_extensions import Annotated

from advanced_alchemy.base import UUIDAuditBase, UUIDBase
from advanced_alchemy.config import AsyncSessionConfig
from advanced_alchemy.exceptions import NotFoundError as AdvancedAlchemyNotFoundError
from advanced_alchemy.extensions.litestar.dto import SQLAlchemyDTO, SQLAlchemyDTOConfig
from advanced_alchemy.extensions.litestar.plugins import SQLAlchemyAsyncConfig, SQLAlchemyPlugin
from advanced_alchemy.filters import LimitOffset
from advanced_alchemy.repository import SQLAlchemyAsyncRepository

if TYPE_CHECKING:
    from litestar.dto import DTOData
    from sqlalchemy.ext.asyncio import AsyncSession


# The `Base` class includes a `UUID` based primary key (`id`)
class Author(UUIDBase):
    # we can optionally provide the table name instead of auto-generating it
    __tablename__ = "author"  #  type: ignore[assignment]
    name: Mapped[str]
    dob: Mapped[Union[date, None]]  # noqa: UP007 - needed for SQLAlchemy on older python versions
    books: Mapped[List[Book]] = relationship(back_populates="author", lazy="noload")  # noqa: UP006


# The `AuditBase` class includes the same UUID` based primary key (`id`) and 2
# additional columns: `created` and `updated`. `created` is a timestamp of when the
# record created, and `updated` is the last time the record was modified.
class Book(UUIDAuditBase):
    __tablename__ = "book"  #  type: ignore[assignment]
    title: Mapped[str]
    author_id: Mapped[UUID] = mapped_column(ForeignKey("author.id"))
    author: Mapped[Author] = relationship(lazy="joined", innerjoin=True, viewonly=True)


# DTO objects let us filter certain fields out of our request/response data
# without defining separate models
class AuthorDTO(SQLAlchemyDTO[Author]):
    config = SQLAlchemyDTOConfig(exclude={"books"})


class AuthorCreateUpdateDTO(SQLAlchemyDTO[Author]):
    config = SQLAlchemyDTOConfig(exclude={"id", "books"})


class AuthorRepository(SQLAlchemyAsyncRepository[Author]):
    """Author repository."""

    model_type = Author


async def provide_authors_repo(db_session: AsyncSession) -> AuthorRepository:
    """This provides the default Authors repository."""
    return AuthorRepository(session=db_session)


# we can optionally override the default `select` used for the repository to pass in
# specific SQL options such as join details
async def provide_author_details_repo(db_session: AsyncSession) -> AuthorRepository:
    """This provides a simple example demonstrating how to override the join options for the repository."""
    return AuthorRepository(
        statement=select(Author).options(selectinload(Author.books)),
        session=db_session,
    )


def provide_limit_offset_pagination(
    current_page: int = Parameter(ge=1, query="currentPage", default=1, required=False),
    page_size: int = Parameter(
        query="pageSize",
        ge=1,
        default=10,
        required=False,
    ),
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


class AuthorController(Controller):
    """Author CRUD"""

    dependencies = {"authors_repo": Provide(provide_authors_repo)}

    @get(path="/authors", return_dto=AuthorDTO)
    async def list_authors(
        self,
        authors_repo: AuthorRepository,
        limit_offset: LimitOffset,
    ) -> OffsetPagination[Author]:
        """List authors."""
        results, total = await authors_repo.list_and_count(limit_offset)
        return OffsetPagination[Author](
            items=results,
            total=total,
            limit=limit_offset.limit,
            offset=limit_offset.offset,
        )

    @post(path="/authors", dto=AuthorCreateUpdateDTO)
    async def create_author(self, authors_repo: AuthorRepository, data: DTOData[Author]) -> Author:
        """Create a new author."""

        # Turn the DTO object into an Author instance.
        author = data.create_instance()

        obj = await authors_repo.add(author)
        await authors_repo.session.commit()
        return obj

    # we override the authors_repo to use the version that joins the Books in
    @get(path="/authors/{author_id:uuid}", dependencies={"authors_repo": Provide(provide_author_details_repo)})
    async def get_author(
        self,
        authors_repo: AuthorRepository,
        author_id: Annotated[
            UUID,
            Parameter(
                title="Author ID",
                description="The author to retrieve.",
            ),
        ],
    ) -> Author:
        """Get an existing author."""
        try:
            return await authors_repo.get(author_id)
        except AdvancedAlchemyNotFoundError as e:
            msg = f"Author with id {author_id} not found."
            raise LiteStarNotFoundException(msg) from e

    @patch(
        path="/authors/{author_id:uuid}",
        dependencies={"authors_repo": Provide(provide_author_details_repo)},
        dto=AuthorCreateUpdateDTO,
    )
    async def update_author(
        self,
        authors_repo: AuthorRepository,
        data: DTOData[Author],
        author_id: Annotated[
            UUID,
            Parameter(
                title="Author ID",
                description="The author to update.",
            ),
        ],
    ) -> Author:
        """Update an author."""
        author = data.create_instance(id=author_id)
        obj = await authors_repo.update(author)
        await authors_repo.session.commit()
        return obj

    @delete(path="/authors/{author_id:uuid}")
    async def delete_author(
        self,
        authors_repo: AuthorRepository,
        author_id: UUID = Parameter(  # noqa: B008
            title="Author ID",
            description="The author to delete.",
        ),
    ) -> None:
        """Delete a author from the system."""
        _ = await authors_repo.delete(author_id)
        await authors_repo.session.commit()


def init_app(*, sqlalchemy_config: SQLAlchemyAsyncConfig | None = None) -> Litestar:
    if not sqlalchemy_config:
        # expire_on_commit=False prevents the sqlalchemy models from being invalidated on commit.
        session_config = AsyncSessionConfig(expire_on_commit=False)
        sqlalchemy_config = SQLAlchemyAsyncConfig(
            connection_string="sqlite+aiosqlite:///test.sqlite",
            create_all=True,
            session_config=session_config,
        )  # Create 'db_session' dependency.

    sqlalchemy_plugin = SQLAlchemyPlugin(config=sqlalchemy_config)

    return Litestar(
        route_handlers=[AuthorController],
        plugins=[sqlalchemy_plugin],
        dependencies={"limit_offset": Provide(provide_limit_offset_pagination, sync_to_thread=False)},
        signature_namespace={"date": date, "datetime": datetime, "UUID": UUID},
    )
