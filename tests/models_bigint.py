"""Example domain objects for testing."""

from __future__ import annotations

from datetime import date, datetime
from typing import List

from sqlalchemy import Column, FetchedValue, ForeignKey, String, Table, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from advanced_alchemy import (
    SQLAlchemyAsyncMockRepository,
    SQLAlchemyAsyncRepository,
    SQLAlchemyAsyncRepositoryService,
    SQLAlchemySyncMockRepository,
    SQLAlchemySyncRepository,
    SQLAlchemySyncRepositoryService,
)
from advanced_alchemy.base import BigIntAuditBase, BigIntBase
from advanced_alchemy.types import EncryptedString
from advanced_alchemy.types.encrypted_string import EncryptedText


class BigIntAuthor(BigIntAuditBase):
    """The Author domain object."""

    name: Mapped[str] = mapped_column(String(length=100))  # pyright: ignore
    dob: Mapped[date] = mapped_column(nullable=True)  # pyright: ignore
    books: Mapped[List[BigIntBook]] = relationship(
        lazy="selectin",
        back_populates="author",
        cascade="all, delete",
    )


class BigIntBook(BigIntBase):
    """The Book domain object."""

    title: Mapped[str] = mapped_column(String(length=250))  # pyright: ignore
    author_id: Mapped[int] = mapped_column(ForeignKey("big_int_author.id"))  # pyright: ignore
    author: Mapped[BigIntAuthor] = relationship(  # pyright: ignore
        lazy="joined",
        innerjoin=True,
        back_populates="books",
    )


class BigIntEventLog(BigIntAuditBase):
    """The event log domain object."""

    logged_at: Mapped[datetime] = mapped_column(default=datetime.now())  # pyright: ignore
    payload: Mapped[dict] = mapped_column(default=lambda: {})  # pyright: ignore


class BigIntModelWithFetchedValue(BigIntBase):
    """The ModelWithFetchedValue BigIntBase."""

    val: Mapped[int]  # pyright: ignore
    updated: Mapped[datetime] = mapped_column(  # pyright: ignore
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
        server_onupdate=FetchedValue(),
    )


bigint_item_tag = Table(
    "bigint_item_tag",
    BigIntBase.metadata,
    Column("item_id", ForeignKey("big_int_item.id"), primary_key=True),
    Column("tag_id", ForeignKey("big_int_tag.id"), primary_key=True),
)


class BigIntItem(BigIntBase):
    name: Mapped[str] = mapped_column(String(length=50))  # pyright: ignore
    description: Mapped[str] = mapped_column(String(length=100), nullable=True)  # pyright: ignore
    tags: Mapped[List[BigIntTag]] = relationship(secondary=lambda: bigint_item_tag, back_populates="items")


class BigIntTag(BigIntBase):
    """The event log domain object."""

    name: Mapped[str] = mapped_column(String(length=50))  # pyright: ignore
    items: Mapped[List[BigIntItem]] = relationship(secondary=lambda: bigint_item_tag, back_populates="tags")


class BigIntRule(BigIntAuditBase):
    """The rule domain object."""

    name: Mapped[str] = mapped_column(String(length=250))  # pyright: ignore
    config: Mapped[dict] = mapped_column(default=lambda: {})  # pyright: ignore


class BigIntSecret(BigIntBase):
    """The secret domain model."""

    secret: Mapped[str] = mapped_column(
        EncryptedString(key="super_secret"),
    )
    long_secret: Mapped[str] = mapped_column(
        EncryptedText(key="super_secret"),
    )


class RuleAsyncRepository(SQLAlchemyAsyncRepository[BigIntRule]):
    """Rule repository."""

    model_type = BigIntRule


class RuleAsyncMockRepository(SQLAlchemyAsyncMockRepository[BigIntRule]):
    """Rule repository."""

    model_type = BigIntRule


class RuleSyncMockRepository(SQLAlchemySyncMockRepository[BigIntRule]):
    """Rule repository."""

    model_type = BigIntRule


class AuthorAsyncRepository(SQLAlchemyAsyncRepository[BigIntAuthor]):
    """Author repository."""

    model_type = BigIntAuthor


class AuthorAsyncMockRepository(SQLAlchemyAsyncMockRepository[BigIntAuthor]):
    model_type = BigIntAuthor


class AuthorSyncMockRepository(SQLAlchemySyncMockRepository[BigIntAuthor]):
    model_type = BigIntAuthor


class BookAsyncRepository(SQLAlchemyAsyncRepository[BigIntBook]):
    """Book repository."""

    model_type = BigIntBook


class BookAsyncMockRepository(SQLAlchemyAsyncMockRepository[BigIntBook]):
    """Book repository."""

    model_type = BigIntBook


class BookSyncMockRepository(SQLAlchemySyncMockRepository[BigIntBook]):
    """Book repository."""

    model_type = BigIntBook


class EventLogAsyncRepository(SQLAlchemyAsyncRepository[BigIntEventLog]):
    """Event log repository."""

    model_type = BigIntEventLog


class ModelWithFetchedValueAsyncRepository(SQLAlchemyAsyncRepository[BigIntModelWithFetchedValue]):
    """BigIntModelWithFetchedValue repository."""

    model_type = BigIntModelWithFetchedValue


class SecretAsyncRepository(SQLAlchemyAsyncRepository[BigIntSecret]):
    """Secret repository."""

    model_type = BigIntSecret


class TagAsyncRepository(SQLAlchemyAsyncRepository[BigIntTag]):
    """Tag repository."""

    model_type = BigIntTag


class TagAsyncMockRepository(SQLAlchemyAsyncMockRepository[BigIntTag]):
    """Tag repository."""

    model_type = BigIntTag


class TagSyncMockRepository(SQLAlchemySyncMockRepository[BigIntTag]):
    """Tag repository."""

    model_type = BigIntTag


class SecretSyncRepository(SQLAlchemySyncRepository[BigIntSecret]):
    """Secret repository."""

    model_type = BigIntSecret


class ItemAsyncRepository(SQLAlchemyAsyncRepository[BigIntItem]):
    """Item repository."""

    model_type = BigIntItem


class ItemAsyncMockRepository(SQLAlchemyAsyncMockRepository[BigIntItem]):
    """Item repository."""

    model_type = BigIntItem


class ItemSyncMockRepository(SQLAlchemySyncMockRepository[BigIntItem]):
    """Item repository."""

    model_type = BigIntItem


class SecretAsyncMockRepository(SQLAlchemyAsyncMockRepository[BigIntSecret]):
    """Secret repository."""

    model_type = BigIntSecret


class SecretSyncMockRepository(SQLAlchemySyncMockRepository[BigIntSecret]):
    """Secret repository."""

    model_type = BigIntSecret


class AuthorSyncRepository(SQLAlchemySyncRepository[BigIntAuthor]):
    """Author repository."""

    model_type = BigIntAuthor


class BookSyncRepository(SQLAlchemySyncRepository[BigIntBook]):
    """Book repository."""

    model_type = BigIntBook


class EventLogSyncRepository(SQLAlchemySyncRepository[BigIntEventLog]):
    """Event log repository."""

    model_type = BigIntEventLog


class RuleSyncRepository(SQLAlchemySyncRepository[BigIntRule]):
    """Rule repository."""

    model_type = BigIntRule


class ModelWithFetchedValueSyncRepository(SQLAlchemySyncRepository[BigIntModelWithFetchedValue]):
    """ModelWithFetchedValue repository."""

    model_type = BigIntModelWithFetchedValue


class TagSyncRepository(SQLAlchemySyncRepository[BigIntTag]):
    """Tag repository."""

    model_type = BigIntTag


class ItemSyncRepository(SQLAlchemySyncRepository[BigIntItem]):
    """Item repository."""

    model_type = BigIntItem


# Services
class SecretAsyncService(SQLAlchemyAsyncRepositoryService[BigIntSecret]):
    """Rule repository."""

    repository_type = SecretAsyncRepository


class RuleAsyncService(SQLAlchemyAsyncRepositoryService[BigIntRule]):
    """Rule repository."""

    repository_type = RuleAsyncRepository


class RuleAsyncMockService(SQLAlchemyAsyncRepositoryService[BigIntRule]):
    """Rule repository."""

    repository_type = RuleAsyncMockRepository


class RuleSyncMockService(SQLAlchemySyncRepositoryService[BigIntRule]):
    """Rule repository."""

    repository_type = RuleSyncMockRepository


class AuthorAsyncService(SQLAlchemyAsyncRepositoryService[BigIntAuthor]):
    """Author repository."""

    repository_type = AuthorAsyncRepository


class AuthorAsyncMockService(SQLAlchemyAsyncRepositoryService[BigIntAuthor]):
    """Author repository."""

    repository_type = AuthorAsyncMockRepository


class AuthorSyncMockService(SQLAlchemySyncRepositoryService[BigIntAuthor]):
    """Author repository."""

    repository_type = AuthorSyncMockRepository


class BookAsyncService(SQLAlchemyAsyncRepositoryService[BigIntBook]):
    """Book repository."""

    repository_type = BookAsyncRepository


class BookAsyncMockService(SQLAlchemyAsyncRepositoryService[BigIntBook]):
    """Book repository."""

    repository_type = BookAsyncMockRepository


class BookSyncMockService(SQLAlchemySyncRepositoryService[BigIntBook]):
    """Book repository."""

    repository_type = BookSyncMockRepository


class EventLogAsyncService(SQLAlchemyAsyncRepositoryService[BigIntEventLog]):
    """Event log repository."""

    repository_type = EventLogAsyncRepository


class ModelWithFetchedValueAsyncService(SQLAlchemyAsyncRepositoryService[BigIntModelWithFetchedValue]):
    """BigIntModelWithFetchedValue repository."""

    repository_type = ModelWithFetchedValueAsyncRepository


class TagAsyncService(SQLAlchemyAsyncRepositoryService[BigIntTag]):
    """Tag repository."""

    repository_type = TagAsyncRepository


class TagAsyncMockService(SQLAlchemyAsyncRepositoryService[BigIntTag]):
    """Tag repository."""

    repository_type = TagAsyncMockRepository


class TagSyncMockService(SQLAlchemySyncRepositoryService[BigIntTag]):
    """Tag repository."""

    repository_type = TagSyncMockRepository


class ItemAsyncService(SQLAlchemyAsyncRepositoryService[BigIntItem]):
    """Item repository."""

    repository_type = ItemAsyncRepository


class ItemAsyncMockService(SQLAlchemyAsyncRepositoryService[BigIntItem]):
    """Item repository."""

    repository_type = ItemAsyncMockRepository


class ItemSyncMockService(SQLAlchemySyncRepositoryService[BigIntItem]):
    """Item repository."""

    repository_type = ItemSyncMockRepository


class RuleSyncService(SQLAlchemySyncRepositoryService[BigIntRule]):
    """Rule repository."""

    repository_type = RuleSyncRepository


class AuthorSyncService(SQLAlchemySyncRepositoryService[BigIntAuthor]):
    """Author repository."""

    repository_type = AuthorSyncRepository


class BookSyncService(SQLAlchemySyncRepositoryService[BigIntBook]):
    """Book repository."""

    repository_type = BookSyncRepository


class EventLogSyncService(SQLAlchemySyncRepositoryService[BigIntEventLog]):
    """Event log repository."""

    repository_type = EventLogSyncRepository


class ModelWithFetchedValueSyncService(SQLAlchemySyncRepositoryService[BigIntModelWithFetchedValue]):
    """BigIntModelWithFetchedValue repository."""

    repository_type = ModelWithFetchedValueSyncRepository


class SecretSyncService(SQLAlchemySyncRepositoryService[BigIntSecret]):
    """Rule repository."""

    repository_type = SecretSyncRepository


class TagSyncService(SQLAlchemySyncRepositoryService[BigIntTag]):
    """Tag repository."""

    repository_type = TagSyncRepository


class ItemSyncService(SQLAlchemySyncRepositoryService[BigIntItem]):
    """Item repository."""

    repository_type = ItemSyncRepository
