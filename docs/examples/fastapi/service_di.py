"""FastAPI service and filter dependency injection example with Advanced Alchemy."""

import tempfile
from http import HTTPStatus
from pathlib import Path
from typing import Annotated
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

    @router.post("/authors", status_code=int(HTTPStatus.CREATED))
    async def create_author(
        data: AuthorCreate,
        authors_service: Annotated[AuthorService, Depends(alchemy.provide_service(AuthorService))],
    ) -> AuthorSchema:
        """Create a new author record."""
        obj = await authors_service.create(data)
        return authors_service.to_schema(obj, schema_type=AuthorSchema)

    @router.get("/authors")
    async def list_authors(
        authors_service: Annotated[AuthorService, Depends(alchemy.provide_service(AuthorService))],
        parsed_filters: Annotated[
            list[filters.FilterTypes],
            Depends(
                alchemy.provide_filters(
                    {
                        "id_filter": UUID,
                        "search": "name",
                        "pagination_type": "limit_offset",
                    },
                ),
            ),
        ],
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
            if create_res.status_code != HTTPStatus.CREATED:
                msg = f"Unexpected create status: {create_res.status_code}"
                raise RuntimeError(msg)
            created = create_res.json()
            if created["name"] != "Grace Hopper":
                msg = f"Unexpected created author name: {created['name']}"
                raise RuntimeError(msg)

            list_res = client.get("/authors?currentPage=1&pageSize=10")
            if list_res.status_code != HTTPStatus.OK:
                msg = f"Unexpected list status: {list_res.status_code}"
                raise RuntimeError(msg)
            payload = list_res.json()
            if payload["total"] != 1 or payload["items"][0]["name"] != "Grace Hopper":
                msg = f"Unexpected list payload: {payload}"
                raise RuntimeError(msg)
