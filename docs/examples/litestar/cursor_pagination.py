"""Litestar cursor pagination with Advanced Alchemy filter dependencies."""

import os
from http import HTTPStatus
from typing import Optional, Union

import msgspec
from litestar import Controller, Litestar, get, post
from litestar.di import NamedDependency
from litestar.params import JSONBody, SkipValidation
from litestar.testing import TestClient
from sqlalchemy.orm import Mapped

from advanced_alchemy.extensions.litestar import (
    SQLAlchemyAsyncConfig,
    SQLAlchemyPlugin,
    base,
    filters,
    providers,
    repository,
    service,
)

__all__ = (
    "ArticleController",
    "ArticleCreate",
    "ArticleModel",
    "ArticleRepository",
    "ArticleSchema",
    "ArticleService",
    "create_app",
    "main",
)

_ARTICLE_COUNT = 7
_PAGE_SIZE = 3


class ArticleModel(base.BigIntAuditBase):
    """Article database model."""

    __tablename__ = "litestar_cursor_article"
    title: Mapped[str]
    views: Mapped[int]


class ArticleCreate(msgspec.Struct):
    """Payload for creating an article."""

    title: str
    views: int


class ArticleSchema(msgspec.Struct):
    """Serialized article."""

    id: int
    title: str
    views: int


class ArticleRepository(repository.SQLAlchemyAsyncRepository[ArticleModel]):
    """Article async repository."""

    model_type = ArticleModel


class ArticleService(service.SQLAlchemyAsyncRepositoryService[ArticleModel, ArticleRepository]):
    """Article async repository service."""

    repository_type = ArticleRepository


class ArticleController(Controller):
    """Article HTTP endpoints."""

    path = "/articles"
    dependencies = providers.create_service_dependencies(
        ArticleService,
        "articles_service",
        filters={
            "pagination_type": "cursor",
            "pagination_size": 20,
            "pagination_max_size": 100,
            "sort_field": "views",
            "sort_order": "desc",
            "sort_fields": ["views", "title"],
        },
    )

    @post(path="/")
    async def create_article(
        self,
        articles_service: NamedDependency[ArticleService],
        data: JSONBody[ArticleCreate],
    ) -> ArticleSchema:
        """Create an article."""
        obj = await articles_service.create(data, auto_commit=True)
        return articles_service.to_schema(obj, schema_type=ArticleSchema)

    @get(path="/")
    async def list_articles(
        self,
        articles_service: NamedDependency[ArticleService],
        filters: NamedDependency[SkipValidation[list[filters.FilterTypes]]],
    ) -> service.CursorPagination[ArticleSchema]:
        """List articles one cursor page at a time."""
        results = await articles_service.get_many(*filters)
        return articles_service.to_schema(
            results,
            filters=filters,
            schema_type=ArticleSchema,
            pagination_type="cursor",
        )


def create_app() -> Litestar:
    """Construct the Litestar application with an in-memory SQLite database."""
    return Litestar(
        route_handlers=[ArticleController],
        plugins=[
            SQLAlchemyPlugin(
                config=SQLAlchemyAsyncConfig(
                    connection_string="sqlite+aiosqlite:///:memory:",
                    create_all=True,
                    pagination_cursor_secret=os.environ.get("CURSOR_SECRET", "development-only-secret"),
                ),
            ),
        ],
    )


def main() -> None:
    """Create articles, then walk every page forward and back."""
    app = create_app()
    with TestClient(app=app) as client:
        for index in range(_ARTICLE_COUNT):
            response = client.post("/articles/", json={"title": f"article {index}", "views": index % 3})
            if response.status_code != HTTPStatus.CREATED:
                msg = f"Unexpected create status: {response.status_code}"
                raise RuntimeError(msg)

        titles: list[str] = []
        cursor: Optional[str] = None
        pages = 0
        while True:
            params: dict[str, Union[str, int]] = {"pageSize": _PAGE_SIZE}
            if cursor:
                params["cursor"] = cursor
            page = client.get("/articles/", params=params).json()
            titles.extend(item["title"] for item in page["items"])
            pages += 1
            if not page["has_next"]:
                break
            cursor = page["next_cursor"]

        expected_pages = -(-_ARTICLE_COUNT // _PAGE_SIZE)
        if pages != expected_pages or len(titles) != len(set(titles)) or len(titles) != _ARTICLE_COUNT:
            msg = f"Unexpected walk: {pages} pages, {titles}"
            raise RuntimeError(msg)

        previous = client.get("/articles/", params={"pageSize": _PAGE_SIZE, "cursor": page["previous_cursor"]}).json()
        if [item["title"] for item in previous["items"]] != titles[_PAGE_SIZE : 2 * _PAGE_SIZE]:
            msg = f"Unexpected previous page: {previous}"
            raise RuntimeError(msg)

        tampered = client.get("/articles/", params={"cursor": f"{cursor}x"})
        if tampered.status_code != HTTPStatus.BAD_REQUEST:
            msg = f"Tampered cursor was not rejected: {tampered.status_code}"
            raise RuntimeError(msg)
