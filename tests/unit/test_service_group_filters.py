"""Service groups share SQL and mock field-filter behavior."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest
from litestar import Litestar, get
from litestar.di import NamedDependency
from litestar.params import SkipValidation
from litestar.testing import TestClient
from sqlalchemy import ForeignKey, create_engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship

from advanced_alchemy.extensions.litestar import SQLAlchemyPlugin, SQLAlchemySyncConfig
from advanced_alchemy.extensions.litestar.providers import create_service_dependencies
from advanced_alchemy.filters import FilterTypes, LimitOffsetFilter, StatementFilter
from advanced_alchemy.repository.memory import SQLAlchemyAsyncMockRepository, SQLAlchemySyncMockRepository
from advanced_alchemy.service import ServiceGroup, SQLAlchemyAsyncRepositoryService, SQLAlchemySyncRepositoryService
from advanced_alchemy.utils.dependencies import (
    build_field_filters,
    build_order_by_filters,
    resolve_filter_fields,
)

pytestmark = pytest.mark.unit


class FieldBase(DeclarativeBase):
    pass


class FieldAuthor(FieldBase):
    __tablename__ = "group_field_author"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]


class FieldArticle(FieldBase):
    __tablename__ = "group_field_article"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str]
    author_id: Mapped[int] = mapped_column(ForeignKey(FieldAuthor.id))
    author: Mapped[FieldAuthor] = relationship(lazy="joined")


def field_filters() -> Sequence[StatementFilter]:
    specs = resolve_filter_fields({"author.name": {"eq"}}, FieldArticle)
    author_filter = build_field_filters(specs, {specs[0].param_name: "Ada"}, rel_path=("author",))
    assert isinstance(author_filter, StatementFilter)
    return [
        author_filter,
        *build_order_by_filters(["author.name", "-title"], None, allowed_fields={"author.name", "title"}),
        LimitOffsetFilter(limit=1, offset=1),
    ]


def articles(authors: Sequence[FieldAuthor]) -> list[FieldArticle]:
    return [
        FieldArticle(id=1, title="Alpha", author=authors[0]),
        FieldArticle(id=2, title="Zulu", author=authors[0]),
        FieldArticle(id=3, title="Other", author=authors[1]),
        FieldArticle(id=4, title="Middle", author=authors[0]),
    ]


@pytest.mark.parametrize("use_mock", [False, True])
def test_sync_service_group_field_filter_parity(use_mock: bool) -> None:
    """Related field filtering preserves ordering and totals in a shared group."""

    class AuthorService(SQLAlchemySyncRepositoryService[FieldAuthor]):
        pass

    class ArticleService(SQLAlchemySyncRepositoryService[FieldArticle]):
        pass

    class AuthorRepo(SQLAlchemySyncMockRepository[FieldAuthor]):
        pass

    class ArticleRepo(SQLAlchemySyncMockRepository[FieldArticle]):
        pass

    if use_mock:
        AuthorRepo.__database_clear__()
        ArticleRepo.__database_clear__()
        setattr(AuthorService, "repository_type", AuthorRepo)
        setattr(ArticleService, "repository_type", ArticleRepo)

    class Group(ServiceGroup):
        authors: AuthorService
        articles: ArticleService

    engine = create_engine("sqlite://")
    try:
        FieldBase.metadata.create_all(engine)
        with Session(engine) as session, Group.new(session=session) as group:
            assert group.authors.repository.session is group.articles.repository.session is session
            authors = group.authors.create_many([FieldAuthor(id=1, name="Ada"), FieldAuthor(id=2, name="Bob")])
            group.articles.create_many(articles(authors))
            items, total = group.articles.get_many_and_count(*field_filters())
            assert ([item.id for item in items], total) == ([4], 3)
            assert group.authors.count() == 2
    finally:
        engine.dispose()
        if use_mock:
            AuthorRepo.__database_clear__()
            ArticleRepo.__database_clear__()


def test_litestar_group_member_field_filters(tmp_path: Path) -> None:
    """HTTP field filters infer a group's member model and retain query aliases."""

    class ArticleService(SQLAlchemySyncRepositoryService[FieldArticle]):
        pass

    class Group(ServiceGroup):
        articles: ArticleService

    engine = create_engine(f"sqlite:///{tmp_path / 'group-filters.sqlite'}")
    try:
        FieldBase.metadata.create_all(engine)
        with Session(engine) as session:
            session.add_all(articles([FieldAuthor(id=1, name="Ada"), FieldAuthor(id=2, name="Bob")]))
            session.commit()

        @get("/articles", sync_to_thread=False)
        def list_articles(
            services: NamedDependency[Group], articles_filters: NamedDependency[SkipValidation[list[FilterTypes]]]
        ) -> dict[str, list[int] | int]:
            items, total = services.articles.get_many_and_count(*articles_filters)
            return {"ids": [item.id for item in items], "total": total}

        dependencies = create_service_dependencies(
            Group,
            key="services",
            filters={
                "articles": {
                    "filter_fields": {"author.name": {"eq"}},
                    "sort_fields": {"author.name", "title"},
                    "pagination_type": "limit_offset",
                }
            },
        )
        app = Litestar(
            [list_articles],
            debug=True,
            dependencies=dependencies,
            plugins=[SQLAlchemyPlugin(SQLAlchemySyncConfig(engine_instance=engine))],
            signature_namespace={"Group": Group},
        )
        with TestClient(app) as client:
            response = client.get(
                "/articles",
                params={
                    "articlesAuthorNameEq": "Ada",
                    "articlesOrderBy": "-title",
                    "articlesPageSize": "1",
                    "articlesCurrentPage": "2",
                },
            )
            assert response.status_code == 200, response.text
            assert response.json() == {"ids": [4], "total": 3}
    finally:
        engine.dispose()


@pytest.mark.parametrize("use_mock", [False, True])
async def test_async_service_group_field_filter_parity(use_mock: bool) -> None:
    """Async groups preserve the same related field results as SQL and sync groups."""

    class AuthorService(SQLAlchemyAsyncRepositoryService[FieldAuthor]):
        pass

    class ArticleService(SQLAlchemyAsyncRepositoryService[FieldArticle]):
        pass

    class AuthorRepo(SQLAlchemyAsyncMockRepository[FieldAuthor]):
        pass

    class ArticleRepo(SQLAlchemyAsyncMockRepository[FieldArticle]):
        pass

    if use_mock:
        AuthorRepo.__database_clear__()
        ArticleRepo.__database_clear__()
        setattr(AuthorService, "repository_type", AuthorRepo)
        setattr(ArticleService, "repository_type", ArticleRepo)

    class Group(ServiceGroup):
        authors: AuthorService
        articles: ArticleService

    engine = create_async_engine("sqlite+aiosqlite://")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(FieldBase.metadata.create_all)
        async with AsyncSession(engine) as session, Group.new(session=session) as group:
            assert group.authors.repository.session is group.articles.repository.session is session
            authors = await group.authors.create_many([FieldAuthor(id=1, name="Ada"), FieldAuthor(id=2, name="Bob")])
            await group.articles.create_many(articles(authors))
            items, total = await group.articles.get_many_and_count(*field_filters())
            assert ([item.id for item in items], total) == ([4], 3)
            assert await group.authors.count() == 2
    finally:
        await engine.dispose()
        if use_mock:
            AuthorRepo.__database_clear__()
            ArticleRepo.__database_clear__()
