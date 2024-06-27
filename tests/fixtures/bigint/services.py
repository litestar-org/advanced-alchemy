"""Example domain objects for testing."""

from __future__ import annotations

from typing import Any

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


# Slug book


class SlugBookAsyncService(SQLAlchemyAsyncRepositoryService[BigIntSlugBook]):
    """Book repository."""

    repository_type = SlugBookAsyncRepository
    match_fields = ["title"]

    def __init__(self, **repo_kwargs: Any) -> None:
        self.repository: SlugBookAsyncRepository = self.repository_type(**repo_kwargs)  # pyright: ignore

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


class SlugBookSyncService(SQLAlchemySyncRepositoryService[BigIntSlugBook]):
    """Book repository."""

    repository_type = SlugBookSyncRepository
    match_fields = ["title"]

    def __init__(self, **repo_kwargs: Any) -> None:
        self.repository: SlugBookSyncRepository = self.repository_type(**repo_kwargs)  # pyright: ignore

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


class SlugBookAsyncMockService(SQLAlchemyAsyncRepositoryService[BigIntSlugBook]):
    """Book repository."""

    repository_type = SlugBookAsyncMockRepository
    match_fields = ["title"]

    def __init__(self, **repo_kwargs: Any) -> None:
        self.repository: SlugBookAsyncMockRepository = self.repository_type(**repo_kwargs)  # pyright: ignore

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


class SlugBookSyncMockService(SQLAlchemySyncRepositoryService[BigIntSlugBook]):
    """Book repository."""

    repository_type = SlugBookSyncMockRepository
    match_fields = ["title"]

    def __init__(self, **repo_kwargs: Any) -> None:
        self.repository: SlugBookSyncMockRepository = self.repository_type(**repo_kwargs)  # pyright: ignore

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
