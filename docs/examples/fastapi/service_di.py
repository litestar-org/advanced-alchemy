"""FastAPI service and filter dependency injection example with Advanced Alchemy."""

from __future__ import annotations

from pathlib import Path
import tempfile
from uuid import UUID

from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy.orm import Mapped

from advanced_alchemy.extensions.fastapi import (
    AdvancedAlchemy,
    AsyncSessionConfig,
    SQLAlchemyAsyncConfig,
    base,
    filters,
    repository,
    service,
)

__all__ = (
    "AuthorCreate",
    "AuthorModel",
    "AuthorRepository",
    "AuthorSchema",
    "AuthorService",
    "create_app",
    "main",
)


class AuthorModel(base.UUIDBase):
    """Author database model for FastAPI example."""

    __tablename__ = "fastapi_basic_author"
    name: Mapped[str]


class AuthorCreate(BaseModel):
    """Request payload for creating an author."""

    name: str


class AuthorSchema(BaseModel):
    """Response schema for an author record."""

    model_config = {"from_attributes": True}

    id: UUID
    name: str


class AuthorRepository(repository.SQLAlchemyAsyncRepository[AuthorModel]):
    """Author async repository."""

    model_type = AuthorModel


class AuthorService(service.SQLAlchemyAsyncRepositoryService[AuthorModel, AuthorRepository]):
    """Author async repository service."""

    repository_type = AuthorRepository


def create_app(db_path: Path) -> FastAPI:
    """Create a FastAPI application wired with AdvancedAlchemy service and filter providers."""
    app = FastAPI()
    alchemy_config = SQLAlchemyAsyncConfig(
        connection_string=f"sqlite+aiosqlite:///{db_path}",
        session_config=AsyncSessionConfig(expire_on_commit=False),
        create_all=True,
        commit_mode="autocommit",
    )
    alchemy = AdvancedAlchemy(config=alchemy_config, app=app)
    router = APIRouter()

    @router.post("/authors", status_code=201)
    async def create_author(
        data: AuthorCreate,
        authors_service: AuthorService = Depends(alchemy.provide_service(AuthorService)),
    ) -> AuthorSchema:
        """Create a new author record."""
        obj = await authors_service.create(data)
        return authors_service.to_schema(obj, schema_type=AuthorSchema)

    @router.get("/authors")
    async def list_authors(
        authors_service: AuthorService = Depends(alchemy.provide_service(AuthorService)),
        parsed_filters: list[filters.FilterTypes] = Depends(
            alchemy.provide_filters(
                {
                    "id_filter": UUID,
                    "search": "name",
                    "pagination_type": "limit_offset",
                },
            ),
        ),
    ) -> service.OffsetPagination[AuthorSchema]:
        """List authors with limit/offset pagination and search filters."""
        results, total = await authors_service.get_many_and_count(*parsed_filters)
        return authors_service.to_schema(
            results,
            total,
            filters=parsed_filters,
            schema_type=AuthorSchema,
        )

    app.include_router(router)
    return app


def main() -> None:
    """Execute the FastAPI dependency injection example in-process."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_file = Path(tmp_dir) / "fastapi_example.sqlite"
        app = create_app(db_file)
        with TestClient(app=app) as client:
            create_res = client.post("/authors", json={"name": "Grace Hopper"})
            assert create_res.status_code == 201
            created = create_res.json()
            assert created["name"] == "Grace Hopper"

            list_res = client.get("/authors?currentPage=1&pageSize=10")
            assert list_res.status_code == 200
            payload = list_res.json()
            assert payload["total"] == 1
            assert payload["items"][0]["name"] == "Grace Hopper"
