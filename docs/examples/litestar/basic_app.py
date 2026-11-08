"""Basic Litestar application with Advanced Alchemy service, DTO, and controller integration."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from litestar import Controller, Litestar, get, post
from litestar.params import Dependency
from litestar.testing import TestClient
import msgspec
from sqlalchemy.orm import Mapped

from advanced_alchemy.extensions.litestar import (
    SQLAlchemyAsyncConfig,
    SQLAlchemyDTO,
    SQLAlchemyDTOConfig,
    SQLAlchemyPlugin,
    base,
    filters,
    providers,
    repository,
    service,
)

__all__ = (
    "AuthorController",
    "AuthorCreate",
    "AuthorDTO",
    "AuthorModel",
    "AuthorRepository",
    "AuthorSchema",
    "AuthorService",
    "AuthorWriteDTO",
    "create_app",
    "main",
)


class AuthorModel(base.UUIDBase):
    """Author database model."""

    __tablename__ = "litestar_basic_author"
    name: Mapped[str]


class AuthorCreate(msgspec.Struct):
    """Payload for creating an author."""

    name: str


class AuthorSchema(msgspec.Struct):
    """Serialized author schema."""

    id: UUID
    name: str


AuthorDTO = SQLAlchemyDTO[AuthorModel]
AuthorWriteDTO = SQLAlchemyDTO[
    Annotated[
        AuthorModel,
        SQLAlchemyDTOConfig(exclude={"id"}),
    ]
]


class AuthorRepository(repository.SQLAlchemyAsyncRepository[AuthorModel]):
    """Author async repository."""

    model_type = AuthorModel


class AuthorService(service.SQLAlchemyAsyncRepositoryService[AuthorModel, AuthorRepository]):
    """Author async repository service."""

    repository_type = AuthorRepository


class AuthorController(Controller):
    """Author HTTP endpoints."""

    path = "/authors"
    dependencies = providers.create_service_dependencies(
        AuthorService,
        "authors_service",
        filters={"id_filter": UUID, "search": "name", "pagination_type": "limit_offset"},
    )

    @post(path="/")
    async def create_author(
        self,
        authors_service: AuthorService,
        data: AuthorCreate,
    ) -> AuthorSchema:
        """Create a new author record."""
        obj = await authors_service.create(data, auto_commit=True)
        return authors_service.to_schema(obj, schema_type=AuthorSchema)

    @get(path="/")
    async def list_authors(
        self,
        authors_service: AuthorService,
        filters: Annotated[list[filters.FilterTypes], Dependency(skip_validation=True)],
    ) -> service.OffsetPagination[AuthorSchema]:
        """List authors with standard pagination and filtering."""
        results, total = await authors_service.get_many_and_count(*filters)
        return authors_service.to_schema(
            results,
            total,
            filters=filters,
            schema_type=AuthorSchema,
        )


def create_app() -> Litestar:
    """Construct the Litestar application with an in-memory SQLite database."""
    return Litestar(
        route_handlers=[AuthorController],
        plugins=[
            SQLAlchemyPlugin(
                config=SQLAlchemyAsyncConfig(
                    connection_string="sqlite+aiosqlite:///:memory:",
                    create_all=True,
                ),
            ),
        ],
    )


def main() -> None:
    """Execute the basic Litestar application example in-process."""
    app = create_app()
    with TestClient(app=app) as client:
        create_response = client.post("/authors/", json={"name": "Ada Lovelace"})
        assert create_response.status_code == 201
        created = create_response.json()
        assert created["name"] == "Ada Lovelace"

        list_response = client.get("/authors/?currentPage=1&pageSize=10")
        assert list_response.status_code == 200
        payload = list_response.json()
        assert payload["total"] == 1
        assert payload["items"][0]["name"] == "Ada Lovelace"
