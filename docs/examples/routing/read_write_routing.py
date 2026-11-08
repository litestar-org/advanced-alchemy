"""Runnable read/write replica routing example for Advanced Alchemy."""

from __future__ import annotations

from pathlib import Path
import shutil
import tempfile

from sqlalchemy import create_engine
from sqlalchemy.orm import Mapped

from advanced_alchemy.base import BigIntAuditBase
from advanced_alchemy.config import SQLAlchemySyncConfig
from advanced_alchemy.config.routing import EngineConfig, RoutingConfig, RoutingStrategy
from advanced_alchemy.repository import SQLAlchemySyncRepository
from advanced_alchemy.routing import primary_context, replica_context, reset_routing_context

__all__ = (
    "Article",
    "ArticleRepository",
    "main",
)


class Article(BigIntAuditBase):
    """Article model used to verify read/write replica routing."""

    __tablename__ = "routing_example_article"

    title: Mapped[str]


class ArticleRepository(SQLAlchemySyncRepository[Article]):
    """Synchronous repository for routed Article persistence."""

    model_type = Article


def main() -> None:
    """Execute a complete primary-write and replica-read routing workflow."""
    reset_routing_context()
    with tempfile.TemporaryDirectory() as tmp_dir:
        primary_db = Path(tmp_dir) / "primary.sqlite"
        replica_db = Path(tmp_dir) / "replica.sqlite"
        primary_url = f"sqlite:///{primary_db}"
        replica_url = f"sqlite:///{replica_db}"

        primary_init_engine = create_engine(primary_url)
        Article.metadata.create_all(primary_init_engine)
        primary_init_engine.dispose()
        shutil.copyfile(primary_db, replica_db)

        config = SQLAlchemySyncConfig(
            routing_config=RoutingConfig(
                engines={
                    "default": [EngineConfig(connection_string=primary_url, name="writer")],
                    "read": [EngineConfig(connection_string=replica_url, weight=2, name="reader-1")],
                },
                routing_strategy=RoutingStrategy.ROUND_ROBIN,
                sticky_after_write=True,
            ),
        )

        with config.get_session() as session:
            repo = ArticleRepository(session=session)
            created = repo.add(Article(title="Primary Write"))
            created_id = created.id
            sticky_read = repo.get(created_id)
            assert sticky_read.title == "Primary Write"
            session.commit()

        shutil.copyfile(primary_db, replica_db)

        with config.get_session() as session:
            repo = ArticleRepository(session=session)
            with replica_context():
                replica_articles = repo.get_many()
                assert len(replica_articles) == 1
                assert replica_articles[0].title == "Primary Write"

            with primary_context():
                primary_article = repo.get_one(title="Primary Write")
                assert primary_article.id == created_id
