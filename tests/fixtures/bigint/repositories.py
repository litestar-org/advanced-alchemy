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


class SlugBookAsyncRepository(SQLAlchemyAsyncSlugRepository[BigIntSlugBook]):
    """Slug Book repository."""

    _uniquify_results = True
    model_type = BigIntSlugBook


class SlugBookSyncRepository(SQLAlchemySyncSlugRepository[BigIntSlugBook]):
    """Slug Book repository."""

    _uniquify_results = True
    model_type = BigIntSlugBook


class SlugBookAsyncMockRepository(SQLAlchemyAsyncMockSlugRepository[BigIntSlugBook]):
    """Book repository."""

    model_type = BigIntSlugBook


class SlugBookSyncMockRepository(SQLAlchemySyncMockSlugRepository[BigIntSlugBook]):
    """Book repository."""

    model_type = BigIntSlugBook
