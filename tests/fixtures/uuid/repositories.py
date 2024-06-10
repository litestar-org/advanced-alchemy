"""Example domain objects for testing."""

from __future__ import annotations

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

    _uniquify_results = True
    model_type = UUIDSlugBook


class SlugBookSyncRepository(SQLAlchemySyncSlugRepository[UUIDSlugBook]):
    """Slug Book repository."""

    _uniquify_results = True
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
