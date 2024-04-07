"""Example domain objects for testing."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, List
from uuid import UUID

from sqlalchemy import Column, FetchedValue, ForeignKey, String, Table, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from advanced_alchemy.base import SlugKey, UUIDAuditBase, UUIDBase, UUIDv6Base, UUIDv7Base
from advanced_alchemy.repository import (
    SQLAlchemyAsyncRepository,
    SQLAlchemyAsyncSlugRepository,
    SQLAlchemySyncRepository,
    SQLAlchemySyncSlugRepository,
)
from advanced_alchemy.repository.memory import (
    SQLAlchemyAsyncMockRepository,
    SQLAlchemyAsyncMockSlugRepository,
    SQLAlchemySyncMockRepository,
    SQLAlchemySyncMockSlugRepository,
)
from advanced_alchemy.service import (
    SQLAlchemyAsyncRepositoryService,
    SQLAlchemySyncRepositoryService,
)
from advanced_alchemy.types.encrypted_string import EncryptedString, EncryptedText


class UUIDAuthor(UUIDAuditBase):
    """The UUIDAuthor domain object."""

    name: Mapped[str] = mapped_column(String(length=100))  # pyright: ignore
    dob: Mapped[date] = mapped_column(nullable=True)  # pyright: ignore
    books: Mapped[List[UUIDBook]] = relationship(
        lazy="selectin",
        back_populates="author",
        cascade="all, delete",
    )


class UUIDBook(UUIDBase):
    """The Book domain object."""

    title: Mapped[str] = mapped_column(String(length=250))  # pyright: ignore
    author_id: Mapped[UUID] = mapped_column(ForeignKey("uuid_author.id"))  # pyright: ignore
    author: Mapped[UUIDAuthor] = relationship(lazy="joined", innerjoin=True, back_populates="books")  # pyright: ignore


class UUIDSlugBook(UUIDBase, SlugKey):
    """The Book domain object with a slug key."""

    title: Mapped[str] = mapped_column(String(length=250))  # pyright: ignore
    author_id: Mapped[str] = mapped_column(String(length=250))  # pyright: ignore


class UUIDEventLog(UUIDAuditBase):
    """The event log domain object."""

    logged_at: Mapped[datetime] = mapped_column(default=datetime.now())  # pyright: ignore
    payload: Mapped[dict] = mapped_column(default={})  # pyright: ignore


class UUIDSecret(UUIDv7Base):
    """The secret domain model."""

    secret: Mapped[str] = mapped_column(
        EncryptedString(key="super_secret"),
    )
    long_secret: Mapped[str] = mapped_column(
        EncryptedText(key="super_secret"),
    )


class UUIDModelWithFetchedValue(UUIDv6Base):
    """The ModelWithFetchedValue UUIDBase."""

    val: Mapped[int]  # pyright: ignore
    updated: Mapped[datetime] = mapped_column(  # pyright: ignore
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
        server_onupdate=FetchedValue(),
    )


uuid_item_tag = Table(
    "uuid_item_tag",
    UUIDBase.metadata,
    Column("item_id", ForeignKey("uuid_item.id"), primary_key=True),
    Column("tag_id", ForeignKey("uuid_tag.id"), primary_key=True),
)


class UUIDItem(UUIDBase):
    name: Mapped[str] = mapped_column(String(length=50))  # pyright: ignore
    description: Mapped[str] = mapped_column(String(length=100), nullable=True)  # pyright: ignore
    tags: Mapped[List[UUIDTag]] = relationship(secondary=lambda: uuid_item_tag, back_populates="items")


class UUIDTag(UUIDAuditBase):
    """The event log domain object."""

    name: Mapped[str] = mapped_column(String(length=50))  # pyright: ignore
    items: Mapped[List[UUIDItem]] = relationship(secondary=lambda: uuid_item_tag, back_populates="tags")


class UUIDRule(UUIDAuditBase):
    """The rule domain object."""

    name: Mapped[str] = mapped_column(String(length=250))  # pyright: ignore
    config: Mapped[dict] = mapped_column(default=lambda: {})  # pyright: ignore


class SecretAsyncRepository(SQLAlchemyAsyncRepository[UUIDSecret]):
    """Secret repository."""

    model_type = UUIDSecret


class RuleAsyncRepository(SQLAlchemyAsyncRepository[UUIDRule]):
    """Rule repository."""

    model_type = UUIDRule


class RuleAsyncMockRepository(SQLAlchemyAsyncMockRepository[UUIDRule]):
    """Rule repository."""

    model_type = UUIDRule


class RuleSyncMockRepository(SQLAlchemySyncMockRepository[UUIDRule]):
    """Rule repository."""

    model_type = UUIDRule


class AuthorAsyncRepository(SQLAlchemyAsyncRepository[UUIDAuthor]):
    """Author repository."""

    model_type = UUIDAuthor


class AuthorAsyncMockRepository(SQLAlchemyAsyncMockRepository[UUIDAuthor]):
    model_type = UUIDAuthor


class AuthorSyncMockRepository(SQLAlchemySyncMockRepository[UUIDAuthor]):
    model_type = UUIDAuthor


class BookAsyncRepository(SQLAlchemyAsyncRepository[UUIDBook]):
    """Book repository."""

    model_type = UUIDBook


class BookAsyncMockRepository(SQLAlchemyAsyncMockRepository[UUIDBook]):
    """Book repository."""

    model_type = UUIDBook


class BookSyncMockRepository(SQLAlchemySyncMockRepository[UUIDBook]):
    """Book repository."""

    model_type = UUIDBook


class SlugBookAsyncRepository(SQLAlchemyAsyncSlugRepository[UUIDSlugBook]):
    """Book repository."""

    model_type = UUIDSlugBook


class SlugBookSyncRepository(SQLAlchemySyncSlugRepository[UUIDSlugBook]):
    """Slug Book repository."""

    model_type = UUIDSlugBook


class SlugBookAsyncMockRepository(SQLAlchemyAsyncMockSlugRepository[UUIDSlugBook]):
    """Book repository."""

    model_type = UUIDSlugBook


class SlugBookSyncMockRepository(SQLAlchemySyncMockSlugRepository[UUIDSlugBook]):
    """Book repository."""

    model_type = UUIDSlugBook


class EventLogAsyncRepository(SQLAlchemyAsyncRepository[UUIDEventLog]):
    """Event log repository."""

    model_type = UUIDEventLog


class ModelWithFetchedValueAsyncRepository(SQLAlchemyAsyncRepository[UUIDModelWithFetchedValue]):
    """ModelWithFetchedValue repository."""

    model_type = UUIDModelWithFetchedValue


class TagAsyncRepository(SQLAlchemyAsyncRepository[UUIDTag]):
    """Tag repository."""

    model_type = UUIDTag


class TagAsyncMockRepository(SQLAlchemyAsyncMockRepository[UUIDTag]):
    """Tag repository."""

    model_type = UUIDTag


class TagSyncMockRepository(SQLAlchemySyncMockRepository[UUIDTag]):
    """Tag repository."""

    model_type = UUIDTag


class ItemAsyncRepository(SQLAlchemyAsyncRepository[UUIDItem]):
    """Item repository."""

    model_type = UUIDItem


class ItemAsyncMockRepository(SQLAlchemyAsyncMockRepository[UUIDItem]):
    """Item repository."""

    model_type = UUIDItem


class ItemSyncMockRepository(SQLAlchemySyncMockRepository[UUIDItem]):
    """Item repository."""

    model_type = UUIDItem


class SecretAsyncMockRepository(SQLAlchemyAsyncMockRepository[UUIDSecret]):
    """Secret repository."""

    model_type = UUIDSecret


class SecretSyncMockRepository(SQLAlchemySyncMockRepository[UUIDSecret]):
    """Secret repository."""

    model_type = UUIDSecret


class AuthorSyncRepository(SQLAlchemySyncRepository[UUIDAuthor]):
    """Author repository."""

    model_type = UUIDAuthor


class BookSyncRepository(SQLAlchemySyncRepository[UUIDBook]):
    """Book repository."""

    model_type = UUIDBook


class SecretSyncRepository(SQLAlchemySyncRepository[UUIDSecret]):
    """Secret repository."""

    model_type = UUIDSecret


class EventLogSyncRepository(SQLAlchemySyncRepository[UUIDEventLog]):
    """Event log repository."""

    model_type = UUIDEventLog


class RuleSyncRepository(SQLAlchemySyncRepository[UUIDRule]):
    """Rule repository."""

    model_type = UUIDRule


class ModelWithFetchedValueSyncRepository(SQLAlchemySyncRepository[UUIDModelWithFetchedValue]):
    """ModelWithFetchedValue repository."""

    model_type = UUIDModelWithFetchedValue


class TagSyncRepository(SQLAlchemySyncRepository[UUIDTag]):
    """Tag repository."""

    model_type = UUIDTag


class ItemSyncRepository(SQLAlchemySyncRepository[UUIDItem]):
    """Item repository."""

    model_type = UUIDItem


# Services


class SecretAsyncService(SQLAlchemyAsyncRepositoryService[UUIDSecret]):
    """Rule repository."""

    repository_type = SecretAsyncRepository


class RuleAsyncService(SQLAlchemyAsyncRepositoryService[UUIDRule]):
    """Rule repository."""

    repository_type = RuleAsyncRepository


class RuleAsyncMockService(SQLAlchemyAsyncRepositoryService[UUIDRule]):
    """Rule repository."""

    repository_type = RuleAsyncMockRepository


class RuleSyncMockService(SQLAlchemySyncRepositoryService[UUIDRule]):
    """Rule repository."""

    repository_type = RuleSyncMockRepository


class AuthorAsyncService(SQLAlchemyAsyncRepositoryService[UUIDAuthor]):
    """Author repository."""

    repository_type = AuthorAsyncRepository


class AuthorAsyncMockService(SQLAlchemyAsyncRepositoryService[UUIDAuthor]):
    """Author repository."""

    repository_type = AuthorAsyncMockRepository


class AuthorSyncMockService(SQLAlchemySyncRepositoryService[UUIDAuthor]):
    """Author repository."""

    repository_type = AuthorSyncMockRepository


class BookAsyncService(SQLAlchemyAsyncRepositoryService[UUIDBook]):
    """Book repository."""

    repository_type = BookAsyncRepository


class BookAsyncMockService(SQLAlchemyAsyncRepositoryService[UUIDBook]):
    """Book repository."""

    repository_type = BookAsyncMockRepository


class BookSyncMockService(SQLAlchemySyncRepositoryService[UUIDBook]):
    """Book repository."""

    repository_type = BookSyncMockRepository


class EventLogAsyncService(SQLAlchemyAsyncRepositoryService[UUIDEventLog]):
    """Event log repository."""

    repository_type = EventLogAsyncRepository


class ModelWithFetchedValueAsyncService(SQLAlchemyAsyncRepositoryService[UUIDModelWithFetchedValue]):
    """UUIDModelWithFetchedValue repository."""

    repository_type = ModelWithFetchedValueAsyncRepository


class TagAsyncService(SQLAlchemyAsyncRepositoryService[UUIDTag]):
    """Tag repository."""

    repository_type = TagAsyncRepository


class TagAsyncMockService(SQLAlchemyAsyncRepositoryService[UUIDTag]):
    """Tag repository."""

    repository_type = TagAsyncMockRepository


class TagSyncMockService(SQLAlchemySyncRepositoryService[UUIDTag]):
    """Tag repository."""

    repository_type = TagSyncMockRepository


class ItemAsyncService(SQLAlchemyAsyncRepositoryService[UUIDItem]):
    """Item repository."""

    repository_type = ItemAsyncRepository


class ItemAsyncMockService(SQLAlchemyAsyncRepositoryService[UUIDItem]):
    """Item repository."""

    repository_type = ItemAsyncMockRepository


class ItemSyncMockService(SQLAlchemySyncRepositoryService[UUIDItem]):
    """Item repository."""

    repository_type = ItemSyncMockRepository


class RuleSyncService(SQLAlchemySyncRepositoryService[UUIDRule]):
    """Rule repository."""

    repository_type = RuleSyncRepository


class AuthorSyncService(SQLAlchemySyncRepositoryService[UUIDAuthor]):
    """Author repository."""

    repository_type = AuthorSyncRepository


class BookSyncService(SQLAlchemySyncRepositoryService[UUIDBook]):
    """Book repository."""

    repository_type = BookSyncRepository


class EventLogSyncService(SQLAlchemySyncRepositoryService[UUIDEventLog]):
    """Event log repository."""

    repository_type = EventLogSyncRepository


class ModelWithFetchedValueSyncService(SQLAlchemySyncRepositoryService[UUIDModelWithFetchedValue]):
    """UUIDModelWithFetchedValue repository."""

    repository_type = ModelWithFetchedValueSyncRepository


class TagSyncService(SQLAlchemySyncRepositoryService[UUIDTag]):
    """Tag repository."""

    repository_type = TagSyncRepository


class ItemSyncService(SQLAlchemySyncRepositoryService[UUIDItem]):
    """Item repository."""

    repository_type = ItemSyncRepository


class SecretSyncService(SQLAlchemySyncRepositoryService[UUIDSecret]):
    """Rule repository."""

    repository_type = SecretSyncRepository


class SlugBookAsyncService(SQLAlchemyAsyncRepositoryService[UUIDSlugBook]):
    """Book repository."""

    repository_type = SlugBookAsyncRepository
    match_fields = ["title"]

    def __init__(self, **repo_kwargs: Any) -> None:
        self.repository: SlugBookAsyncRepository = self.repository_type(**repo_kwargs)

    async def to_model(self, data: UUIDSlugBook | dict[str, Any], operation: str | None = None) -> UUIDSlugBook:
        if isinstance(data, dict) and "slug" not in data and operation == "create":
            data["slug"] = await self.repository.get_available_slug(data["title"])
        if isinstance(data, dict) and "slug" not in data and "title" in data and operation == "update":
            data["slug"] = await self.repository.get_available_slug(data["title"])
        return await super().to_model(data, operation)


class SlugBookSyncService(SQLAlchemySyncRepositoryService[UUIDSlugBook]):
    """Book repository."""

    repository_type = SlugBookSyncRepository

    def __init__(self, **repo_kwargs: Any) -> None:
        self.repository: SlugBookSyncRepository = self.repository_type(**repo_kwargs)

    def to_model(self, data: UUIDSlugBook | dict[str, Any], operation: str | None = None) -> UUIDSlugBook:
        if isinstance(data, dict) and "slug" not in data and operation == "create":
            data["slug"] = self.repository.get_available_slug(data["title"])
        if isinstance(data, dict) and "slug" not in data and "title" in data and operation == "update":
            data["slug"] = self.repository.get_available_slug(data["title"])
        return super().to_model(data, operation)


class SlugBookAsyncMockService(SQLAlchemyAsyncRepositoryService[UUIDSlugBook]):
    """Book repository."""

    repository_type = SlugBookAsyncMockRepository
    match_fields = ["title"]

    def __init__(self, **repo_kwargs: Any) -> None:
        self.repository: SlugBookAsyncMockRepository = self.repository_type(**repo_kwargs)

    async def to_model(self, data: UUIDSlugBook | dict[str, Any], operation: str | None = None) -> UUIDSlugBook:
        if isinstance(data, dict) and "slug" not in data and operation == "create":
            data["slug"] = await self.repository.get_available_slug(data["title"])
        if isinstance(data, dict) and "slug" not in data and "title" in data and operation == "update":
            data["slug"] = await self.repository.get_available_slug(data["title"])
        return await super().to_model(data, operation)


class SlugBookSyncMockService(SQLAlchemySyncRepositoryService[UUIDSlugBook]):
    """Book repository."""

    repository_type = SlugBookSyncMockRepository
    match_fields = ["title"]

    def __init__(self, **repo_kwargs: Any) -> None:
        self.repository: SlugBookSyncMockRepository = self.repository_type(**repo_kwargs)

    def to_model(self, data: UUIDSlugBook | dict[str, Any], operation: str | None = None) -> UUIDSlugBook:
        if isinstance(data, dict) and "slug" not in data and operation == "create":
            data["slug"] = self.repository.get_available_slug(data["title"])
        if isinstance(data, dict) and "slug" not in data and "title" in data and operation == "update":
            data["slug"] = self.repository.get_available_slug(data["title"])
        return super().to_model(data, operation)
