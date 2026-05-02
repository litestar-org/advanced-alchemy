"""Minimal FilterSet example: declare, parse, compile, run.

Run with::

    uv run python examples/filterset_basic.py
"""

import asyncio
import pprint
from typing import ClassVar

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import Mapped

from advanced_alchemy.base import BigIntBase
from advanced_alchemy.config import AsyncSessionConfig, SQLAlchemyAsyncConfig
from advanced_alchemy.filters import (
    FilterSet,
    NumberFilter,
    OrderingFilter,
    StringFilter,
)
from advanced_alchemy.repository import SQLAlchemyAsyncRepository


class Post(BigIntBase):
    title: Mapped[str]
    views: Mapped[int]


class PostRepository(SQLAlchemyAsyncRepository[Post]):
    """Post repository."""

    model_type = Post


class PostFilter(FilterSet):
    """Filter set declaring the public filter surface for ``Post``."""

    title = StringFilter(lookups=["exact", "icontains"])
    views = NumberFilter(type_=int, lookups=["gt", "lt", "between"])
    order_by = OrderingFilter(allowed=["views", "title"])

    class Meta:
        model = Post
        strict: ClassVar[bool] = True


alchemy_config = SQLAlchemyAsyncConfig(
    engine_instance=create_async_engine("sqlite+aiosqlite:///:memory:"),
    session_config=AsyncSessionConfig(expire_on_commit=False),
)


async def run_script() -> None:
    async with alchemy_config.get_engine().begin() as conn:
        await conn.run_sync(BigIntBase.metadata.create_all)
    async with alchemy_config.get_session() as db_session:
        repo = PostRepository(session=db_session)
        await repo.add_many(
            [
                Post(title="Why Python rocks", views=120),
                Post(title="Rust for Pythonistas", views=45),
                Post(title="Go vs the world", views=200),
            ],
            auto_commit=True,
        )

    async with alchemy_config.get_session() as db_session:
        repo = PostRepository(session=db_session)
        instance = PostFilter.from_query_params(
            {
                "title__icontains": "py",
                "views__gt": "50",
                "order_by": "-views",
            },
        )
        results = await repo.list(*instance.to_filters())
        pprint.pp([(post.title, post.views) for post in results])


if __name__ == "__main__":
    asyncio.run(run_script())
