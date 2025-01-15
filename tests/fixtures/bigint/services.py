"""Example domain objects for testing."""

from __future__ import annotations

from advanced_alchemy.service import (
    SQLAlchemyAsyncRepositoryService,
    SQLAlchemySyncRepositoryService,
)
from advanced_alchemy.service.typing import ModelDictT, is_dict_with_field, is_dict_without_field, schema_dump
from tests.fixtures.bigint.models import (
    BigIntAuthor,
    BigIntBook,
    BigIntEventLog,
    BigIntItem,
    BigIntModelWithFetchedValue,
    BigIntRule,
    BigIntSecret,
    BigIntSlugBook,
    BigIntTag,
)
from tests.fixtures.bigint.repositories import (
    AuthorAsyncMockRepository,
    AuthorAsyncRepository,
    AuthorSyncMockRepository,
    AuthorSyncRepository,
    BookAsyncMockRepository,
    BookAsyncRepository,
    BookSyncMockRepository,
    BookSyncRepository,
    EventLogAsyncRepository,
    EventLogSyncRepository,
    ItemAsyncMockRepository,
    ItemAsyncRepository,
    ItemSyncMockRepository,
    ItemSyncRepository,
    ModelWithFetchedValueAsyncRepository,
    ModelWithFetchedValueSyncRepository,
    RuleAsyncMockRepository,
    RuleAsyncRepository,
    RuleSyncMockRepository,
    RuleSyncRepository,
    SecretAsyncRepository,
    SecretSyncRepository,
    SlugBookAsyncMockRepository,
    SlugBookAsyncRepository,
    SlugBookSyncMockRepository,
    SlugBookSyncRepository,
    TagAsyncMockRepository,
    TagAsyncRepository,
    TagSyncMockRepository,
    TagSyncRepository,
)


# Services
class SecretAsyncService(SQLAlchemyAsyncRepositoryService[BigIntSecret, SecretAsyncRepository]):
    """Rule repository."""

    repository_type = SecretAsyncRepository


class RuleAsyncService(SQLAlchemyAsyncRepositoryService[BigIntRule, RuleAsyncRepository]):
    """Rule repository."""

    repository_type = RuleAsyncRepository


class RuleAsyncMockService(SQLAlchemyAsyncRepositoryService[BigIntRule, RuleAsyncMockRepository]):
    """Rule repository."""

    repository_type = RuleAsyncMockRepository


class RuleSyncMockService(SQLAlchemySyncRepositoryService[BigIntRule, RuleSyncMockRepository]):
    """Rule repository."""

    repository_type = RuleSyncMockRepository


class AuthorAsyncService(SQLAlchemyAsyncRepositoryService[BigIntAuthor, AuthorAsyncRepository]):
    """Author repository."""

    repository_type = AuthorAsyncRepository


class AuthorAsyncMockService(SQLAlchemyAsyncRepositoryService[BigIntAuthor, AuthorAsyncMockRepository]):
    """Author repository."""

    repository_type = AuthorAsyncMockRepository


class AuthorSyncMockService(SQLAlchemySyncRepositoryService[BigIntAuthor, AuthorSyncMockRepository]):
    """Author repository."""

    repository_type = AuthorSyncMockRepository


class BookAsyncService(SQLAlchemyAsyncRepositoryService[BigIntBook, BookAsyncRepository]):
    """Book repository."""

    repository_type = BookAsyncRepository


class BookAsyncMockService(SQLAlchemyAsyncRepositoryService[BigIntBook, BookAsyncMockRepository]):
    """Book repository."""

    repository_type = BookAsyncMockRepository


class BookSyncMockService(SQLAlchemySyncRepositoryService[BigIntBook, BookSyncMockRepository]):
    """Book repository."""

    repository_type = BookSyncMockRepository


class EventLogAsyncService(SQLAlchemyAsyncRepositoryService[BigIntEventLog, EventLogAsyncRepository]):
    """Event log repository."""

    repository_type = EventLogAsyncRepository


class ModelWithFetchedValueAsyncService(
    SQLAlchemyAsyncRepositoryService[BigIntModelWithFetchedValue, ModelWithFetchedValueAsyncRepository]
):
    """BigIntModelWithFetchedValue repository."""

    repository_type = ModelWithFetchedValueAsyncRepository


class TagAsyncService(SQLAlchemyAsyncRepositoryService[BigIntTag, TagAsyncRepository]):
    """Tag repository."""

    repository_type = TagAsyncRepository


class TagAsyncMockService(SQLAlchemyAsyncRepositoryService[BigIntTag, TagAsyncMockRepository]):
    """Tag repository."""

    repository_type = TagAsyncMockRepository


class TagSyncMockService(SQLAlchemySyncRepositoryService[BigIntTag, TagSyncMockRepository]):
    """Tag repository."""

    repository_type = TagSyncMockRepository


class ItemAsyncService(SQLAlchemyAsyncRepositoryService[BigIntItem, ItemAsyncRepository]):
    """Item repository."""

    repository_type = ItemAsyncRepository


class ItemAsyncMockService(SQLAlchemyAsyncRepositoryService[BigIntItem, ItemAsyncMockRepository]):
    """Item repository."""

    repository_type = ItemAsyncMockRepository


class ItemSyncMockService(SQLAlchemySyncRepositoryService[BigIntItem, ItemSyncMockRepository]):
    """Item repository."""

    repository_type = ItemSyncMockRepository


class RuleSyncService(SQLAlchemySyncRepositoryService[BigIntRule, RuleSyncRepository]):
    """Rule repository."""

    repository_type = RuleSyncRepository


class AuthorSyncService(SQLAlchemySyncRepositoryService[BigIntAuthor, AuthorSyncRepository]):
    """Author repository."""

    repository_type = AuthorSyncRepository


class BookSyncService(SQLAlchemySyncRepositoryService[BigIntBook, BookSyncRepository]):
    """Book repository."""

    repository_type = BookSyncRepository


class EventLogSyncService(SQLAlchemySyncRepositoryService[BigIntEventLog, EventLogSyncRepository]):
    """Event log repository."""

    repository_type = EventLogSyncRepository


class ModelWithFetchedValueSyncService(
    SQLAlchemySyncRepositoryService[BigIntModelWithFetchedValue, ModelWithFetchedValueSyncRepository]
):
    """BigIntModelWithFetchedValue repository."""

    repository_type = ModelWithFetchedValueSyncRepository


class SecretSyncService(SQLAlchemySyncRepositoryService[BigIntSecret, SecretSyncRepository]):
    """Rule repository."""

    repository_type = SecretSyncRepository


class TagSyncService(SQLAlchemySyncRepositoryService[BigIntTag, TagSyncRepository]):
    """Tag repository."""

    repository_type = TagSyncRepository


class ItemSyncService(SQLAlchemySyncRepositoryService[BigIntItem, ItemSyncRepository]):
    """Item repository."""

    repository_type = ItemSyncRepository


# Slug book


class SlugBookAsyncService(SQLAlchemyAsyncRepositoryService[BigIntSlugBook]):
    """Book repository."""

    repository_type = SlugBookAsyncRepository
    match_fields = ["title"]

    async def to_model(self, data: ModelDictT[BigIntSlugBook], operation: str | None = None) -> BigIntSlugBook:
        data = schema_dump(data)
        if is_dict_without_field(data, "slug") and operation == "create":
            data["slug"] = await self.repository.get_available_slug(data["title"])
        if is_dict_without_field(data, "slug") and is_dict_with_field(data, "title") and operation == "update":
            data["slug"] = await self.repository.get_available_slug(data["title"])
        return await super().to_model(data, operation)


class SlugBookSyncService(SQLAlchemySyncRepositoryService[BigIntSlugBook, SlugBookSyncRepository]):
    """Book repository."""

    repository_type = SlugBookSyncRepository
    match_fields = ["title"]

    def to_model(
        self,
        data: ModelDictT[BigIntSlugBook],
        operation: str | None = None,
    ) -> BigIntSlugBook:
        data = schema_dump(data)
        if is_dict_without_field(data, "slug") and operation == "create":
            data["slug"] = self.repository.get_available_slug(data["title"])
        if is_dict_without_field(data, "slug") and is_dict_with_field(data, "title") and operation == "update":
            data["slug"] = self.repository.get_available_slug(data["title"])
        return super().to_model(data, operation)


class SlugBookAsyncMockService(SQLAlchemyAsyncRepositoryService[BigIntSlugBook, SlugBookAsyncMockRepository]):
    """Book repository."""

    repository_type = SlugBookAsyncMockRepository
    match_fields = ["title"]

    async def to_model(
        self,
        data: ModelDictT[BigIntSlugBook],
        operation: str | None = None,
    ) -> BigIntSlugBook:
        data = schema_dump(data)
        if is_dict_without_field(data, "slug") and operation == "create":
            data["slug"] = await self.repository.get_available_slug(data["title"])
        if is_dict_without_field(data, "slug") and is_dict_with_field(data, "title") and operation == "update":
            data["slug"] = await self.repository.get_available_slug(data["title"])
        return await super().to_model(data, operation)


class SlugBookSyncMockService(SQLAlchemySyncRepositoryService[BigIntSlugBook, SlugBookSyncMockRepository]):
    """Book repository."""

    repository_type = SlugBookSyncMockRepository
    match_fields = ["title"]

    def to_model(
        self,
        data: ModelDictT[BigIntSlugBook],
        operation: str | None = None,
    ) -> BigIntSlugBook:
        data = schema_dump(data)
        if is_dict_without_field(data, "slug") and operation == "create":
            data["slug"] = self.repository.get_available_slug(data["title"])
        if is_dict_without_field(data, "slug") and is_dict_with_field(data, "title") and operation == "update":
            data["slug"] = self.repository.get_available_slug(data["title"])
        return super().to_model(data, operation)
