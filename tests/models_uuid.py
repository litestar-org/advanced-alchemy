"""Example domain objects for testing."""

from __future__ import annotations

from datetime import date, datetime
from typing import List
from uuid import UUID

from sqlalchemy import Column, FetchedValue, ForeignKey, String, Table, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from advanced_alchemy import (
    SQLAlchemyAsyncRepository,
    SQLAlchemyAsyncRepositoryService,
    SQLAlchemySyncRepository,
    SQLAlchemySyncRepositoryService,
)
from advanced_alchemy.base import UUIDAuditBase, UUIDBase


class UUIDPublisher(UUIDBase):
    name: Mapped[str] = mapped_column(String(length=100))  # pyright: ignore
    books: Mapped[List[UUIDBook]] = relationship(
        lazy="selectin",
        back_populates="publisher",
        cascade="all, delete",
    )


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
    publisher_id: Mapped[int] = mapped_column(ForeignKey("uuid_publisher.id"))
    author: Mapped[UUIDAuthor] = relationship(lazy="joined", innerjoin=True, back_populates="books")  # pyright: ignore
    publisher: Mapped[UUIDPublisher] = relationship(UUIDPublisher)


class UUIDEventLog(UUIDAuditBase):
    """The event log domain object."""

    logged_at: Mapped[datetime] = mapped_column(default=datetime.now())  # pyright: ignore
    payload: Mapped[dict] = mapped_column(default={})  # pyright: ignore


class UUIDModelWithFetchedValue(UUIDBase):
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


class RuleAsyncRepository(SQLAlchemyAsyncRepository[UUIDRule]):
    """Rule repository."""

    model_type = UUIDRule


class AuthorAsyncRepository(SQLAlchemyAsyncRepository[UUIDAuthor]):
    """Author repository."""

    model_type = UUIDAuthor


class PublisherAsyncRepository(SQLAlchemyAsyncRepository[UUIDPublisher]):
    """Publisher repository."""

    model_type = UUIDPublisher


class BookAsyncRepository(SQLAlchemyAsyncRepository[UUIDBook]):
    """Book repository."""

    model_type = UUIDBook


class EventLogAsyncRepository(SQLAlchemyAsyncRepository[UUIDEventLog]):
    """Event log repository."""

    model_type = UUIDEventLog


class ModelWithFetchedValueAsyncRepository(SQLAlchemyAsyncRepository[UUIDModelWithFetchedValue]):
    """ModelWithFetchedValue repository."""

    model_type = UUIDModelWithFetchedValue


class TagAsyncRepository(SQLAlchemyAsyncRepository[UUIDTag]):
    """Tag repository."""

    model_type = UUIDTag


class ItemAsyncRepository(SQLAlchemyAsyncRepository[UUIDItem]):
    """Item repository."""

    model_type = UUIDItem


class AuthorSyncRepository(SQLAlchemySyncRepository[UUIDAuthor]):
    """Author repository."""

    model_type = UUIDAuthor


class PublisherSyncRepository(SQLAlchemySyncRepository[UUIDPublisher]):
    """Publisher repository."""

    model_type = UUIDPublisher


class BookSyncRepository(SQLAlchemySyncRepository[UUIDBook]):
    """Book repository."""

    model_type = UUIDBook


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


class RuleAsyncService(SQLAlchemyAsyncRepositoryService[UUIDRule]):
    """Rule repository."""

    repository_type = RuleAsyncRepository


class AuthorAsyncService(SQLAlchemyAsyncRepositoryService[UUIDAuthor]):
    """Author repository."""

    repository_type = AuthorAsyncRepository


class BookAsyncService(SQLAlchemyAsyncRepositoryService[UUIDBook]):
    """Book repository."""

    repository_type = BookAsyncRepository


class EventLogAsyncService(SQLAlchemyAsyncRepositoryService[UUIDEventLog]):
    """Event log repository."""

    repository_type = EventLogAsyncRepository


class ModelWithFetchedValueAsyncService(SQLAlchemyAsyncRepositoryService[UUIDModelWithFetchedValue]):
    """UUIDModelWithFetchedValue repository."""

    repository_type = ModelWithFetchedValueAsyncRepository


class TagAsyncService(SQLAlchemyAsyncRepositoryService[UUIDTag]):
    """Tag repository."""

    repository_type = TagAsyncRepository


class ItemAsyncService(SQLAlchemyAsyncRepositoryService[UUIDItem]):
    """Item repository."""

    repository_type = ItemAsyncRepository


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
