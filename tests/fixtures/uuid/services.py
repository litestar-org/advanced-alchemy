"""Example domain objects for testing."""

from __future__ import annotations

from typing import Any

from advanced_alchemy.service import (
    SQLAlchemyAsyncRepositoryService,
    SQLAlchemySyncRepositoryService,
)
from advanced_alchemy.service.typing import (
    PydanticOrMsgspecT,
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
        self.repository: SlugBookAsyncRepository = self.repository_type(**repo_kwargs)  # pyright: ignore

    async def to_model(
        self,
        data: UUIDSlugBook | dict[str, Any] | PydanticOrMsgspecT,
        operation: str | None = None,
    ) -> UUIDSlugBook:
        data = schema_dump(data)
        if is_dict_without_field(data, "slug") and operation == "create":
            data["slug"] = await self.repository.get_available_slug(data["title"])
        if is_dict_without_field(data, "slug") and is_dict_with_field(data, "title") and operation == "update":
            data["slug"] = await self.repository.get_available_slug(data["title"])
        return await super().to_model(data, operation)


class SlugBookSyncService(SQLAlchemySyncRepositoryService[UUIDSlugBook]):
    """Book repository."""

    repository_type = SlugBookSyncRepository

    def __init__(self, **repo_kwargs: Any) -> None:
        self.repository: SlugBookSyncRepository = self.repository_type(**repo_kwargs)  # pyright: ignore

    def to_model(
        self,
        data: UUIDSlugBook | dict[str, Any] | PydanticOrMsgspecT,
        operation: str | None = None,
    ) -> UUIDSlugBook:
        data = schema_dump(data)
        if is_dict_without_field(data, "slug") and operation == "create":
            data["slug"] = self.repository.get_available_slug(data["title"])
        if is_dict_without_field(data, "slug") and is_dict_with_field(data, "title") and operation == "update":
            data["slug"] = self.repository.get_available_slug(data["title"])
        return super().to_model(data, operation)


class SlugBookAsyncMockService(SQLAlchemyAsyncRepositoryService[UUIDSlugBook]):
    """Book repository."""

    repository_type = SlugBookAsyncMockRepository
    match_fields = ["title"]

    def __init__(self, **repo_kwargs: Any) -> None:
        self.repository: SlugBookAsyncMockRepository = self.repository_type(**repo_kwargs)  # pyright: ignore

    async def to_model(
        self,
        data: UUIDSlugBook | dict[str, Any] | PydanticOrMsgspecT,
        operation: str | None = None,
    ) -> UUIDSlugBook:
        data = schema_dump(data)
        if is_dict_without_field(data, "slug") and operation == "create":
            data["slug"] = await self.repository.get_available_slug(data["title"])
        if is_dict_without_field(data, "slug") and is_dict_with_field(data, "title") and operation == "update":
            data["slug"] = await self.repository.get_available_slug(data["title"])
        return await super().to_model(data, operation)


class SlugBookSyncMockService(SQLAlchemySyncRepositoryService[UUIDSlugBook]):
    """Book repository."""

    repository_type = SlugBookSyncMockRepository
    match_fields = ["title"]

    def __init__(self, **repo_kwargs: Any) -> None:
        self.repository: SlugBookSyncMockRepository = self.repository_type(**repo_kwargs)  # pyright: ignore

    def to_model(
        self,
        data: UUIDSlugBook | dict[str, Any] | PydanticOrMsgspecT,
        operation: str | None = None,
    ) -> UUIDSlugBook:
        data = schema_dump(data)
        if is_dict_without_field(data, "slug") and operation == "create":
            data["slug"] = self.repository.get_available_slug(data["title"])
        if is_dict_without_field(data, "slug") and is_dict_with_field(data, "title") and operation == "update":
            data["slug"] = self.repository.get_available_slug(data["title"])
        return super().to_model(data, operation)
