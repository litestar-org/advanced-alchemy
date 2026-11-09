import datetime
from typing import Annotated
from uuid import UUID

from litestar import Controller, Litestar, delete, get, patch, post
from litestar.di import NamedDependency
from litestar.params import PathParameter, SkipValidation
from pydantic import BaseModel
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from advanced_alchemy.extensions.litestar import (
    AsyncSessionConfig,
    SQLAlchemyAsyncConfig,
    SQLAlchemyPlugin,
    base,
    filters,
    providers,
    repository,
    service,
)


class BookModel(base.UUIDAuditBase):
    __tablename__ = "book"
    title: Mapped[str]
    author_id: Mapped[UUID] = mapped_column(ForeignKey("author.id"))
    author: Mapped["AuthorModel"] = relationship(lazy="joined", innerjoin=True, viewonly=True)


class AuthorModel(base.UUIDBase):
    __tablename__ = "author"
    name: Mapped[str]
    dob: Mapped[datetime.date | None]
    books: Mapped[list[BookModel]] = relationship(back_populates="author", lazy="selectin")


class Author(BaseModel):
    id: UUID | None = None
    name: str
    dob: datetime.date | None = None


class AuthorCreate(BaseModel):
    name: str
    dob: datetime.date | None = None


class AuthorUpdate(BaseModel):
    name: str | None = None
    dob: datetime.date | None = None


class AuthorService(service.SQLAlchemyAsyncRepositoryService[AuthorModel]):
    """Author repository."""

    class Repo(repository.SQLAlchemyAsyncRepository[AuthorModel]):
        """Author repository."""

        model_type = AuthorModel

    repository_type = Repo


class AuthorController(Controller):
    """Author CRUD"""

    dependencies = providers.create_service_dependencies(
        AuthorService,
        "authors_service",
        load=[AuthorModel.books],
        filters={"pagination_type": "limit_offset", "id_filter": UUID, "search": "name", "search_ignore_case": True},
    )

    @get(path="/authors")
    async def list_authors(
        self,
        authors_service: NamedDependency[AuthorService],
        filters: NamedDependency[SkipValidation[list[filters.FilterTypes]]],
    ) -> service.OffsetPagination[Author]:
        """List authors."""
        results, total = await authors_service.get_many_and_count(*filters)
        return authors_service.to_schema(results, total, filters=filters, schema_type=Author)

    @post(path="/authors")
    async def create_author(
        self,
        authors_service: NamedDependency[AuthorService],
        data: AuthorCreate,
    ) -> Author:
        """Create a new author."""
        obj = await authors_service.create(data)
        return authors_service.to_schema(obj, schema_type=Author)

    @get(path="/authors/{author_id:uuid}")
    async def get_author(
        self,
        authors_service: NamedDependency[AuthorService],
        author_id: Annotated[
            UUID,
            PathParameter(
                title="Author ID",
                description="The author to retrieve.",
            ),
        ],
    ) -> Author:
        """Get an existing author."""
        obj = await authors_service.get(author_id)
        return authors_service.to_schema(obj, schema_type=Author)

    @patch(path="/authors/{author_id:uuid}")
    async def update_author(
        self,
        authors_service: NamedDependency[AuthorService],
        data: AuthorUpdate,
        author_id: Annotated[
            UUID,
            PathParameter(
                title="Author ID",
                description="The author to update.",
            ),
        ],
    ) -> Author:
        """Update an author."""
        obj = await authors_service.update(data, item_id=author_id, auto_commit=True)
        return authors_service.to_schema(obj, schema_type=Author)

    @delete(path="/authors/{author_id:uuid}")
    async def delete_author(
        self,
        authors_service: NamedDependency[AuthorService],
        author_id: Annotated[
            UUID,
            PathParameter(
                title="Author ID",
                description="The author to delete.",
            ),
        ],
    ) -> None:
        """Delete a author from the system."""
        _ = await authors_service.delete(author_id)


alchemy_config = SQLAlchemyAsyncConfig(
    connection_string="sqlite+aiosqlite:///test.sqlite",
    before_send_handler="autocommit",
    session_config=AsyncSessionConfig(expire_on_commit=False),
    create_all=True,
)

app = Litestar(
    route_handlers=[AuthorController],
    plugins=[SQLAlchemyPlugin(config=alchemy_config)],
)
