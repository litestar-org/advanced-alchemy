"""Relationship-traversal example: FilterSet across one-to-many and M2M edges.

Run with::

    uv run python examples/filterset_relationships.py
"""

import asyncio
import pprint
from typing import ClassVar

from sqlalchemy import Column, ForeignKey, Table
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import Mapped, mapped_column, relationship

from advanced_alchemy.base import BigIntBase
from advanced_alchemy.config import AsyncSessionConfig, SQLAlchemyAsyncConfig
from advanced_alchemy.filters import FilterSet, OrderingFilter, StringFilter
from advanced_alchemy.repository import SQLAlchemyAsyncRepository

post_tag = Table(
    "post_tag",
    BigIntBase.metadata,
    Column("post_id", ForeignKey("post.id"), primary_key=True),
    Column("tag_id", ForeignKey("tag.id"), primary_key=True),
)


class Author(BigIntBase):
    name: Mapped[str]


class Tag(BigIntBase):
    slug: Mapped[str] = mapped_column(unique=True)


class Post(BigIntBase):
    title: Mapped[str]
    author_id: Mapped[int] = mapped_column(ForeignKey("author.id"))
    author: Mapped[Author] = relationship("Author", lazy="selectin")
    tags: Mapped[list[Tag]] = relationship("Tag", secondary=post_tag, lazy="selectin")


class PostRepository(SQLAlchemyAsyncRepository[Post]):
    """Post repository."""

    model_type = Post


class PostFilter(FilterSet):
    """Declares filter paths through ``author`` (O2M) and ``tags`` (M2M)."""

    title = StringFilter(lookups=["icontains"])
    author__name = StringFilter(lookups=["iexact"])
    tags__slug = StringFilter(lookups=["in"])
    order_by = OrderingFilter(allowed=["title"])

    class Meta:
        model = Post
        allowed_relationships: ClassVar = ["author", "tags"]
        max_relationship_depth: ClassVar[int] = 1


alchemy_config = SQLAlchemyAsyncConfig(
    engine_instance=create_async_engine("sqlite+aiosqlite:///:memory:"),
    session_config=AsyncSessionConfig(expire_on_commit=False),
)


async def run_script() -> None:
    async with alchemy_config.get_engine().begin() as conn:
        await conn.run_sync(BigIntBase.metadata.create_all)
    async with alchemy_config.get_session() as db_session:
        ada = Author(name="Ada")
        grace = Author(name="Grace")
        py = Tag(slug="python")
        rs = Tag(slug="rust")
        db_session.add_all(
            [
                ada,
                grace,
                py,
                rs,
                Post(title="Why Python rocks", author=ada, tags=[py]),
                Post(title="Hello Rust", author=grace, tags=[rs]),
                Post(title="Polyglot programming", author=ada, tags=[py, rs]),
            ],
        )
        await db_session.commit()

    async with alchemy_config.get_session() as db_session:
        repo = PostRepository(session=db_session)
        instance = PostFilter.from_query_params(
            {"author__name__iexact": "ada", "tags__slug__in": "python"},
        )
        results = await repo.list(*instance.to_filters())
        pprint.pp([post.title for post in results])


if __name__ == "__main__":
    asyncio.run(run_script())
