"""Example domain objects for testing."""

from __future__ import annotations

from advanced_alchemy.service import (
    SQLAlchemyAsyncRepositoryService,
    SQLAlchemySyncRepositoryService,
)
from advanced_alchemy.service.typing import (
    ModelDictT,
    is_dict_with_field,
    is_dict_without_field,
    schema_dump,
)
from tests.fixtures.uuid.models import (
    UUIDAuthor,
    UUIDBook,
    UUIDEventLog,
    UUIDItem,
    UUIDModelWithFetchedValue,
    UUIDRule,
    UUIDSecret,
    UUIDSlugBook,
    UUIDTag,
)
from tests.fixtures.uuid.repositories import (
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


class SecretAsyncService(SQLAlchemyAsyncRepositoryService[UUIDSecret, SecretAsyncRepository]):
    """Rule repository."""

    repository_type = SecretAsyncRepository


class RuleAsyncService(SQLAlchemyAsyncRepositoryService[UUIDRule, RuleAsyncRepository]):
    """Rule repository."""

    repository_type = RuleAsyncRepository


class RuleAsyncMockService(SQLAlchemyAsyncRepositoryService[UUIDRule, RuleAsyncMockRepository]):
    """Rule repository."""

    repository_type = RuleAsyncMockRepository


class RuleSyncMockService(SQLAlchemySyncRepositoryService[UUIDRule, RuleSyncMockRepository]):
    """Rule repository."""

    repository_type = RuleSyncMockRepository


class AuthorAsyncService(SQLAlchemyAsyncRepositoryService[UUIDAuthor, AuthorAsyncRepository]):
    """Author repository."""

    repository_type = AuthorAsyncRepository


class AuthorAsyncMockService(SQLAlchemyAsyncRepositoryService[UUIDAuthor, AuthorAsyncMockRepository]):
    """Author repository."""

    repository_type = AuthorAsyncMockRepository


class AuthorSyncMockService(SQLAlchemySyncRepositoryService[UUIDAuthor, AuthorSyncMockRepository]):
    """Author repository."""

    repository_type = AuthorSyncMockRepository


class BookAsyncService(SQLAlchemyAsyncRepositoryService[UUIDBook, BookAsyncRepository]):
    """Book repository."""

    repository_type = BookAsyncRepository


class BookAsyncMockService(SQLAlchemyAsyncRepositoryService[UUIDBook, BookAsyncMockRepository]):
    """Book repository."""

    repository_type = BookAsyncMockRepository


class BookSyncMockService(SQLAlchemySyncRepositoryService[UUIDBook, BookSyncMockRepository]):
    """Book repository."""

    repository_type = BookSyncMockRepository


class EventLogAsyncService(SQLAlchemyAsyncRepositoryService[UUIDEventLog, EventLogAsyncRepository]):
    """Event log repository."""

    repository_type = EventLogAsyncRepository


class ModelWithFetchedValueAsyncService(
    SQLAlchemyAsyncRepositoryService[UUIDModelWithFetchedValue, ModelWithFetchedValueAsyncRepository]
):
    """UUIDModelWithFetchedValue repository."""

    repository_type = ModelWithFetchedValueAsyncRepository


class TagAsyncService(SQLAlchemyAsyncRepositoryService[UUIDTag, TagAsyncRepository]):
    """Tag repository."""

    repository_type = TagAsyncRepository


class TagAsyncMockService(SQLAlchemyAsyncRepositoryService[UUIDTag, TagAsyncMockRepository]):
    """Tag repository."""

    repository_type = TagAsyncMockRepository


class TagSyncMockService(SQLAlchemySyncRepositoryService[UUIDTag, TagSyncMockRepository]):
    """Tag repository."""

    repository_type = TagSyncMockRepository


class ItemAsyncService(SQLAlchemyAsyncRepositoryService[UUIDItem, ItemAsyncRepository]):
    """Item repository."""

    repository_type = ItemAsyncRepository


class ItemAsyncMockService(SQLAlchemyAsyncRepositoryService[UUIDItem, ItemAsyncMockRepository]):
    """Item repository."""

    repository_type = ItemAsyncMockRepository


class ItemSyncMockService(SQLAlchemySyncRepositoryService[UUIDItem, ItemSyncMockRepository]):
    """Item repository."""

    repository_type = ItemSyncMockRepository


class RuleSyncService(SQLAlchemySyncRepositoryService[UUIDRule, RuleSyncRepository]):
    """Rule repository."""

    repository_type = RuleSyncRepository


class AuthorSyncService(SQLAlchemySyncRepositoryService[UUIDAuthor, AuthorSyncRepository]):
    """Author repository."""

    repository_type = AuthorSyncRepository


class BookSyncService(SQLAlchemySyncRepositoryService[UUIDBook, BookSyncRepository]):
    """Book repository."""

    repository_type = BookSyncRepository


class EventLogSyncService(SQLAlchemySyncRepositoryService[UUIDEventLog, EventLogSyncRepository]):
    """Event log repository."""

    repository_type = EventLogSyncRepository


class ModelWithFetchedValueSyncService(
    SQLAlchemySyncRepositoryService[UUIDModelWithFetchedValue, ModelWithFetchedValueSyncRepository]
):
    """UUIDModelWithFetchedValue repository."""

    repository_type = ModelWithFetchedValueSyncRepository


class TagSyncService(SQLAlchemySyncRepositoryService[UUIDTag, TagSyncRepository]):
    """Tag repository."""

    repository_type = TagSyncRepository


class ItemSyncService(SQLAlchemySyncRepositoryService[UUIDItem, ItemSyncRepository]):
    """Item repository."""

    repository_type = ItemSyncRepository


class SecretSyncService(SQLAlchemySyncRepositoryService[UUIDSecret, SecretSyncRepository]):
    """Rule repository."""

    repository_type = SecretSyncRepository


class SlugBookAsyncService(SQLAlchemyAsyncRepositoryService[UUIDSlugBook, SlugBookAsyncRepository]):
    """Book repository."""

    repository_type = SlugBookAsyncRepository
    match_fields = ["title"]

    async def to_model(
        self,
        data: ModelDictT[UUIDSlugBook],
        operation: str | None = None,
    ) -> UUIDSlugBook:
        data = schema_dump(data)
        if is_dict_without_field(data, "slug") and operation == "create":
            data["slug"] = await self.repository.get_available_slug(data["title"])
        if is_dict_without_field(data, "slug") and is_dict_with_field(data, "title") and operation == "update":
            data["slug"] = await self.repository.get_available_slug(data["title"])
        return await super().to_model(data, operation)


class SlugBookSyncService(SQLAlchemySyncRepositoryService[UUIDSlugBook, SlugBookSyncRepository]):
    """Book repository."""

    repository_type = SlugBookSyncRepository

    def to_model(
        self,
        data: ModelDictT[UUIDSlugBook],
        operation: str | None = None,
    ) -> UUIDSlugBook:
        data = schema_dump(data)
        if is_dict_without_field(data, "slug") and operation == "create":
            data["slug"] = self.repository.get_available_slug(data["title"])
        if is_dict_without_field(data, "slug") and is_dict_with_field(data, "title") and operation == "update":
            data["slug"] = self.repository.get_available_slug(data["title"])
        return super().to_model(data, operation)


class SlugBookAsyncMockService(SQLAlchemyAsyncRepositoryService[UUIDSlugBook, SlugBookAsyncMockRepository]):
    """Book repository."""

    repository_type = SlugBookAsyncMockRepository
    match_fields = ["title"]

    async def to_model(
        self,
        data: ModelDictT[UUIDSlugBook],
        operation: str | None = None,
    ) -> UUIDSlugBook:
        data = schema_dump(data)
        if is_dict_without_field(data, "slug") and operation == "create":
            data["slug"] = await self.repository.get_available_slug(data["title"])
        if is_dict_without_field(data, "slug") and is_dict_with_field(data, "title") and operation == "update":
            data["slug"] = await self.repository.get_available_slug(data["title"])
        return await super().to_model(data, operation)


class SlugBookSyncMockService(SQLAlchemySyncRepositoryService[UUIDSlugBook, SlugBookSyncMockRepository]):
    """Book repository."""

    repository_type = SlugBookSyncMockRepository
    match_fields = ["title"]

    def to_model(
        self,
        data: ModelDictT[UUIDSlugBook],
        operation: str | None = None,
    ) -> UUIDSlugBook:
        data = schema_dump(data)
        if is_dict_without_field(data, "slug") and operation == "create":
            data["slug"] = self.repository.get_available_slug(data["title"])
        if is_dict_without_field(data, "slug") and is_dict_with_field(data, "title") and operation == "update":
            data["slug"] = self.repository.get_available_slug(data["title"])
        return super().to_model(data, operation)
