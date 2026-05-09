"""JSON-driven filtering with MultiFilter, including a relationship clause.

Run with::

    uv run python examples/multifilter_json.py
"""

import asyncio
import json
import pprint

from sqlalchemy import ForeignKey
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import Mapped, mapped_column, relationship

from advanced_alchemy.base import BigIntBase
from advanced_alchemy.config import AsyncSessionConfig, SQLAlchemyAsyncConfig
from advanced_alchemy.filters import MultiFilter
from advanced_alchemy.repository import SQLAlchemyAsyncRepository


class Author(BigIntBase):
    name: Mapped[str]


class Post(BigIntBase):
    title: Mapped[str]
    author_id: Mapped[int] = mapped_column(ForeignKey("author.id"))
    author: Mapped[Author] = relationship("Author", lazy="selectin")


class PostRepository(SQLAlchemyAsyncRepository[Post]):
    """Post repository."""

    model_type = Post


PAYLOAD = json.loads("""
{
    "and_": [
        {"type": "search", "field_name": "title", "value": "py", "ignore_case": true},
        {
            "type": "relationship",
            "relationship": "author",
            "negate": false,
            "filters": [
                {"type": "comparison", "field_name": "name", "operator": "eq", "value": "Ada"}
            ]
        }
    ]
}
""")


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
        db_session.add_all(
            [
                ada,
                grace,
                Post(title="Why Python rocks", author=ada),
                Post(title="Why Rust rocks", author=grace),
            ],
        )
        await db_session.commit()

    async with alchemy_config.get_session() as db_session:
        repo = PostRepository(session=db_session)
        results = await repo.list(MultiFilter(filters=PAYLOAD))
        pprint.pp([(post.title, post.author.name) for post in results])


if __name__ == "__main__":
    asyncio.run(run_script())
