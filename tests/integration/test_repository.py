"""Integration tests for the SQLAlchemy Repository implementation using session-based fixtures."""

import datetime
from collections.abc import Generator
from typing import TYPE_CHECKING, Any, Literal, Optional, Union
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from time_machine import travel

from advanced_alchemy.exceptions import NotFoundError
from advanced_alchemy.filters import (
    BeforeAfter,
    OrderBy,
    SearchFilter,
)
from advanced_alchemy.repository import SQLAlchemyAsyncRepository
from advanced_alchemy.repository.memory import (
    SQLAlchemyAsyncMockRepository,
    SQLAlchemySyncMockRepository,
)
from advanced_alchemy.service import SQLAlchemyAsyncRepositoryService
from tests.helpers import maybe_async

# Python 3.9 compatibility for typing.TypeAlias
try:  # Python >= 3.10
    from typing import TypeAlias  # type: ignore[attr-defined]
except Exception:  # Python 3.9 fallback
    from typing_extensions import TypeAlias  # type: ignore[assignment]

if TYPE_CHECKING:
    from time_machine import Coordinates

pytestmark = [
    pytest.mark.integration,
    pytest.mark.xdist_group("repository"),
]
xfail = pytest.mark.xfail

# Type aliases for data and repository/service components
RawRecordData: TypeAlias = "list[dict[str, Any]]"
RepositoryPKType = Literal["uuid", "bigint"]
AnyRepository: TypeAlias = "Union[SQLAlchemyAsyncRepository[Any], SQLAlchemyAsyncMockRepository[Any]]"
AnyService: TypeAlias = "SQLAlchemyAsyncRepositoryService[Any, AnyRepository]"

mock_engines = {"mock_async_engine", "mock_sync_engine"}


# Helper functions for repository creation
def create_repository(
    session: "Union[Session, AsyncSession]", model_type: type, repository_class: "Optional[type]" = None
) -> "Any":
    """Create a repository instance for the given session and model type."""
    if repository_class is None:
        if isinstance(session, AsyncSession):
            base_repository_class = SQLAlchemyAsyncRepository  # type: ignore[assignment]
        else:
            from advanced_alchemy.repository import SQLAlchemySyncRepository

            base_repository_class = SQLAlchemySyncRepository  # type: ignore[assignment]
    else:
        base_repository_class = repository_class  # type: ignore[assignment]

    # Create a dynamic repository class with the model_type as a class attribute
    repository_class_name = f"DynamicRepository_{model_type.__name__}"

    # Add a create method that handles dict data and maps to add for test compatibility
    async def create(self: Any, data: Any, **kwargs: Any) -> Any:
        # If data is a dict, convert it to a model instance
        if isinstance(data, dict):
            model_instance = model_type(**data)
        else:
            model_instance = data
        return await self.add(model_instance, **kwargs)

    def create_sync(self: Any, data: Any, **kwargs: Any) -> Any:
        # Sync version for sync repositories
        if isinstance(data, dict):
            model_instance = model_type(**data)
        else:
            model_instance = data
        return self.add(model_instance, **kwargs)

    # Choose the right create method based on repository type
    create_method = create if isinstance(session, AsyncSession) else create_sync

    DynamicRepository = type(
        repository_class_name, (base_repository_class,), {"model_type": model_type, "create": create_method}
    )

    return DynamicRepository(session=session)


def create_service(
    session: "Union[Session, AsyncSession]", model_type: type, service_class: "Optional[type]" = None
) -> Any:
    """Create a service instance for the given session and model type."""
    # Create a repository first, since services operate on repositories
    repository = create_repository(session, model_type)

    if service_class is None:
        if isinstance(session, AsyncSession):
            from advanced_alchemy.service import SQLAlchemyAsyncRepositoryService

            base_service_class = SQLAlchemyAsyncRepositoryService
        else:
            from advanced_alchemy.service import SQLAlchemySyncRepositoryService

            base_service_class = SQLAlchemySyncRepositoryService  # type: ignore[assignment]
    else:
        base_service_class = service_class  # type: ignore[assignment]

    # Create a dynamic service class that knows about the repository
    service_class_name = f"DynamicService_{model_type.__name__}"

    # Set the repository_type to the same type as our dynamic repository
    repository_type = type(repository)
    DynamicService = type(service_class_name, (base_service_class,), {"repository_type": repository_type})

    # Initialize the service
    return DynamicService(session=session)


# Helper functions for session-based testing
def get_model_from_session(
    session_data: "tuple[Union[Session, AsyncSession], dict[str, type]]", model_name: str
) -> type:
    """Extract a model type from session data tuple."""
    _, models = session_data
    return models[model_name]


def get_repository_from_session(
    session_data: "tuple[Union[Session, AsyncSession], dict[str, type]]", model_name: str
) -> Any:
    """Create a repository from session data tuple."""
    session, models = session_data
    model_type = models[model_name]
    return create_repository(session, model_type)


def get_service_from_session(
    session_data: "tuple[Union[Session, AsyncSession], dict[str, type]]", model_name: str
) -> Any:
    """Create a service from session data tuple."""
    session, models = session_data
    model_type = models[model_name]
    return create_service(session, model_type)


@pytest.fixture(autouse=True)
def _clear_in_memory_db() -> "Generator[None, None, None]":  # pyright: ignore[reportUnusedFunction]
    try:
        yield
    finally:
        SQLAlchemyAsyncMockRepository.__database_clear__()
        SQLAlchemySyncMockRepository.__database_clear__()


@pytest.fixture()
def frozen_datetime() -> "Generator[Coordinates, None, None]":
    with travel(lambda: datetime.datetime.now(datetime.timezone.utc), tick=False) as frozen:
        yield frozen


# Test functions using new session-based pattern
async def test_repo_count_method(seeded_test_session_async: "tuple[AsyncSession, dict[str, type]]") -> None:
    """Test SQLAlchemy count."""
    session, models = seeded_test_session_async
    author_repo = create_repository(session, models["author"])
    assert await maybe_async(author_repo.count()) == 2


async def test_repo_count_method_with_filters(
    seeded_test_session_async: "tuple[AsyncSession, dict[str, type]]",
) -> None:
    """Test SQLAlchemy count with filters."""
    session, models = seeded_test_session_async
    author_repo = create_repository(session, models["author"])

    # Get the first author name from seeded data
    if hasattr(session, "bind") and getattr(session.bind, "dialect", {}).name == "mock":
        # Mock repository handling
        assert (
            await maybe_async(
                author_repo.count(
                    **{author_repo.model_type.name.key: "Agatha Christie"},
                ),
            )
            == 1
        )
    else:
        # Real repository handling
        assert (
            await maybe_async(
                author_repo.count(
                    author_repo.model_type.name == "Agatha Christie",
                ),
            )
            == 1
        )


async def test_repo_list_and_count_method(seeded_test_session_async: "tuple[AsyncSession, dict[str, type]]") -> None:
    """Test SQLAlchemy list with count in asyncpg."""
    session, models = seeded_test_session_async
    author_repo = create_repository(session, models["author"])

    data, count = await maybe_async(author_repo.list_and_count())
    assert len(data) == 2
    assert count == 2


async def test_repo_list_and_count_basic_method(
    seeded_test_session_async: "tuple[AsyncSession, dict[str, type]]",
) -> None:
    """Test SQLAlchemy list and count."""
    session, models = seeded_test_session_async
    author_repo = create_repository(session, models["author"])

    data, count = await maybe_async(author_repo.list_and_count())
    assert len(data) == 2
    assert count == 2


async def test_repo_list_method_with_filters(seeded_test_session_async: "tuple[AsyncSession, dict[str, type]]") -> None:
    """Test SQLAlchemy list with filters."""
    session, models = seeded_test_session_async
    author_repo = create_repository(session, models["author"])

    # Test filtering by name
    if hasattr(session, "bind") and getattr(session.bind, "dialect", {}).name == "mock":
        # Mock repository handling
        data = await maybe_async(author_repo.list(**{author_repo.model_type.name.key: "Agatha Christie"}))
    else:
        # Real repository handling
        data = await maybe_async(author_repo.list(author_repo.model_type.name == "Agatha Christie"))

    assert len(data) == 1
    assert data[0].name == "Agatha Christie"


async def test_repo_exists_method(seeded_test_session_async: "tuple[AsyncSession, dict[str, type]]") -> None:
    """Test repository exists method."""
    session, models = seeded_test_session_async
    author_repo = create_repository(session, models["author"])

    # Get first author ID
    authors = await maybe_async(author_repo.list())
    first_author_id = authors[0].id

    assert await maybe_async(author_repo.exists(id=first_author_id)) is True

    # Test with non-existent ID
    non_existent_id = UUID("00000000-0000-0000-0000-000000000000") if hasattr(first_author_id, "hex") else 99999
    assert await maybe_async(author_repo.exists(id=non_existent_id)) is False


async def test_repo_get_method(seeded_test_session_async: "tuple[AsyncSession, dict[str, type]]") -> None:
    """Test repository get method."""
    session, models = seeded_test_session_async
    author_repo = create_repository(session, models["author"])

    # Get first author ID
    authors = await maybe_async(author_repo.list())
    first_author_id = authors[0].id

    author = await maybe_async(author_repo.get(first_author_id))
    assert author.id == first_author_id


async def test_repo_get_one_or_none_method(seeded_test_session_async: "tuple[AsyncSession, dict[str, type]]") -> None:
    """Test repository get_one_or_none method."""
    session, models = seeded_test_session_async
    author_repo = create_repository(session, models["author"])

    # Get first author ID
    authors = await maybe_async(author_repo.list())
    first_author_id = authors[0].id

    author = await maybe_async(author_repo.get_one_or_none(id=first_author_id))
    assert author is not None
    assert author.id == first_author_id

    # Test with non-existent ID
    non_existent_id = UUID("00000000-0000-0000-0000-000000000000") if hasattr(first_author_id, "hex") else 99999
    author = await maybe_async(author_repo.get_one_or_none(id=non_existent_id))
    assert author is None


async def test_repo_create_method(seeded_test_session_async: "tuple[AsyncSession, dict[str, type]]") -> None:
    """Test repository create method."""
    session, models = seeded_test_session_async
    author_repo = create_repository(session, models["author"])

    new_author_data = {"name": "Test Author", "dob": datetime.datetime.now(datetime.timezone.utc).date()}

    new_author = await maybe_async(author_repo.create(new_author_data))
    assert new_author.name == "Test Author"
    assert new_author.id is not None

    # Verify it was actually created
    total_count = await maybe_async(author_repo.count())
    assert total_count == 3


async def test_repo_update_method(seeded_test_session_async: "tuple[AsyncSession, dict[str, type]]") -> None:
    """Test repository update method."""
    session, models = seeded_test_session_async
    author_repo = create_repository(session, models["author"])

    # Get first author
    authors = await maybe_async(author_repo.list())
    author = authors[0]
    original_name = author.name

    # Update the author
    author.name = "Updated Name"
    updated_author = await maybe_async(author_repo.update(author))

    assert updated_author.name == "Updated Name"
    assert updated_author.name != original_name


async def test_repo_delete_method(seeded_test_session_async: "tuple[AsyncSession, dict[str, type]]") -> None:
    """Test repository delete method."""
    session, models = seeded_test_session_async
    author_repo = create_repository(session, models["author"])

    # Get first author
    authors = await maybe_async(author_repo.list())
    author = authors[0]
    author_id = author.id

    # Delete the author
    deleted_author = await maybe_async(author_repo.delete(author_id))
    assert deleted_author.id == author_id

    # Verify it was deleted
    remaining_authors = await maybe_async(author_repo.list())
    assert len(remaining_authors) == 1

    remaining_ids = [a.id for a in remaining_authors]
    assert author_id not in remaining_ids


async def test_repo_health_check(seeded_test_session_async: "tuple[AsyncSession, dict[str, type]]") -> None:
    """Test repository health check."""
    session, models = seeded_test_session_async
    author_repo = create_repository(session, models["author"])

    # Health check should not raise an exception - it's a class method that needs session
    assert await maybe_async(author_repo.check_health(session)) is True


# Service tests using new session-based pattern
async def test_service_count_method(seeded_test_session_async: "tuple[AsyncSession, dict[str, type]]") -> None:
    """Test service count method."""
    session, models = seeded_test_session_async
    author_service = get_service_from_session(seeded_test_session_async, "author")

    count = await maybe_async(author_service.count())
    assert count == 2


async def test_service_list_method(seeded_test_session_async: "tuple[AsyncSession, dict[str, type]]") -> None:
    """Test service list method."""
    session, models = seeded_test_session_async
    author_service = get_service_from_session(seeded_test_session_async, "author")

    authors = await maybe_async(author_service.list())
    assert len(authors) == 2


async def test_service_get_method(seeded_test_session_async: "tuple[AsyncSession, dict[str, type]]") -> None:
    """Test service get method."""
    session, models = seeded_test_session_async
    author_service = get_service_from_session(seeded_test_session_async, "author")

    # Get first author ID
    authors = await maybe_async(author_service.list())
    first_author_id = authors[0].id

    author = await maybe_async(author_service.get(first_author_id))
    assert author.id == first_author_id


async def test_service_create_method(seeded_test_session_async: "tuple[AsyncSession, dict[str, type]]") -> None:
    """Test service create method."""
    session, models = seeded_test_session_async
    author_service = get_service_from_session(seeded_test_session_async, "author")

    new_author_data = {"name": "Service Test Author", "dob": datetime.datetime.now(datetime.timezone.utc).date()}

    new_author = await maybe_async(author_service.create(new_author_data))
    assert new_author.name == "Service Test Author"
    assert new_author.id is not None


async def test_service_update_method(seeded_test_session_async: "tuple[AsyncSession, dict[str, type]]") -> None:
    """Test service update method."""
    session, models = seeded_test_session_async
    author_service = get_service_from_session(seeded_test_session_async, "author")

    # Get first author
    authors = await maybe_async(author_service.list())
    author = authors[0]
    author_id = author.id

    # Update via service - correct parameter order is (data, item_id)
    update_data = {"name": "Service Updated Name"}
    updated_author = await maybe_async(author_service.update(update_data, item_id=author_id))

    assert updated_author.name == "Service Updated Name"


async def test_service_delete_method(seeded_test_session_async: "tuple[AsyncSession, dict[str, type]]") -> None:
    """Test service delete method."""
    session, models = seeded_test_session_async
    author_service = get_service_from_session(seeded_test_session_async, "author")

    # Get first author
    authors = await maybe_async(author_service.list())
    author_id = authors[0].id

    # Delete via service
    deleted_author = await maybe_async(author_service.delete(author_id))
    assert deleted_author.id == author_id

    # Verify deletion
    remaining_authors = await maybe_async(author_service.list())
    assert len(remaining_authors) == 1


# Additional filter tests
async def test_repo_filter_before_after(seeded_test_session_async: "tuple[AsyncSession, dict[str, type]]") -> None:
    """Test repository with BeforeAfter filter."""
    session, models = seeded_test_session_async
    author_repo = create_repository(session, models["author"])

    # Test date filtering
    cutoff_date = datetime.datetime(2023, 4, 1, tzinfo=datetime.timezone.utc)
    filter_obj = BeforeAfter(field_name="created_at", before=cutoff_date, after=None)

    authors = await maybe_async(author_repo.list(filter_obj))
    # Should get authors created before April 1, 2023
    assert len(authors) >= 1  # At least one author should match


async def test_repo_filter_search(seeded_test_session_async: "tuple[AsyncSession, dict[str, type]]") -> None:
    """Test repository with SearchFilter."""
    session, models = seeded_test_session_async
    author_repo = create_repository(session, models["author"])

    # Search for 'Christie' in name
    search_filter = SearchFilter(field_name="name", value="Christie")

    authors = await maybe_async(author_repo.list(search_filter))
    assert len(authors) == 1
    assert "Christie" in authors[0].name


async def test_repo_filter_order_by(seeded_test_session_async: "tuple[AsyncSession, dict[str, type]]") -> None:
    """Test repository with OrderBy filter."""
    session, models = seeded_test_session_async
    author_repo = create_repository(session, models["author"])

    # Order by name ascending
    order_filter = OrderBy(field_name="name")

    authors = await maybe_async(author_repo.list(order_filter))
    assert len(authors) == 2

    # Verify ordering
    names = [author.name for author in authors]
    assert names == sorted(names)


# Pagination tests
async def test_service_paginated_list(seeded_test_session_async: "tuple[AsyncSession, dict[str, type]]") -> None:
    """Test service paginated list."""
    from advanced_alchemy.filters import LimitOffset

    session, models = seeded_test_session_async
    author_service = get_service_from_session(seeded_test_session_async, "author")

    # Test pagination using LimitOffset filter with consistent ordering
    paginated = await maybe_async(author_service.list(LimitOffset(limit=1, offset=0), OrderBy(field_name="name")))

    assert len(paginated) == 1


# Error handling tests
async def test_repo_error_messages(seeded_test_session_async: "tuple[AsyncSession, dict[str, type]]") -> None:
    """Test repository error handling."""
    session, models = seeded_test_session_async
    author_repo = create_repository(session, models["author"])

    # Test NotFoundError for non-existent ID
    non_existent_id = (
        UUID("00000000-0000-0000-0000-000000000000")
        if hasattr(author_repo.model_type.id.type, "python_type") and author_repo.model_type.id.type.python_type == UUID
        else 99999
    )

    with pytest.raises(NotFoundError):
        await maybe_async(author_repo.get(non_existent_id))
