"""Integration tests for repository caching with dogpile.cache."""

from __future__ import annotations

import asyncio
from collections.abc import Generator
from typing import TYPE_CHECKING, Any, Optional, cast

import pytest
from sqlalchemy import Engine, String, event
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from advanced_alchemy.base import UUIDBase
from advanced_alchemy.cache import setup_cache_listeners
from advanced_alchemy.cache.config import CacheConfig
from advanced_alchemy.cache.manager import DOGPILE_CACHE_INSTALLED, CacheManager
from advanced_alchemy.repository import SQLAlchemyAsyncRepository, SQLAlchemySyncRepository

if TYPE_CHECKING:
    pass

pytestmark = [
    pytest.mark.integration,
    pytest.mark.xdist_group("cache"),
]


@pytest.fixture(scope="module", autouse=True)
def _setup_cache_listeners() -> Generator[None, None, None]:
    """Set up global cache listeners for all tests in this module."""
    setup_cache_listeners()
    yield


# Module-level cache for model and counter for unique names
_model_cache: dict[str, type] = {}
_class_counter = 0


def get_cached_author_model(engine_dialect_name: str, worker_id: str) -> type[DeclarativeBase]:
    """Create appropriate CachedAuthor model based on engine dialect."""
    global _class_counter
    cache_key = f"cached_author_{worker_id}_{engine_dialect_name}"

    if cache_key not in _model_cache:

        class TestBase(DeclarativeBase):
            pass

        _class_counter += 1
        unique_suffix = f"{_class_counter}_{worker_id}_{engine_dialect_name}"

        class_name = f"CachedAuthor_{unique_suffix}"

        CachedAuthor = type(
            class_name,
            (UUIDBase, TestBase),
            {
                "__tablename__": f"test_cached_authors_{worker_id}_{engine_dialect_name}",
                "__mapper_args__": {"concrete": True},
                "__module__": __name__,
                "name": mapped_column(String(length=100)),
                "bio": mapped_column(String(length=500), nullable=True),
                "__annotations__": {"name": Mapped[str], "bio": Mapped[Optional[str]]},
            },
        )

        _model_cache[cache_key] = CachedAuthor

    return _model_cache[cache_key]


def get_worker_id(request: pytest.FixtureRequest) -> str:
    """Get worker ID for pytest-xdist or 'master' for single process."""
    workerinput = getattr(request.config, "workerinput", None)
    if isinstance(workerinput, dict):
        return cast("str", workerinput.get("workerid", "master"))
    return "master"


@pytest.fixture
def memory_cache_manager() -> CacheManager:
    """Create a CacheManager with memory backend for testing."""
    config = CacheConfig(
        backend="dogpile.cache.memory",
        expiration_time=300,
        key_prefix="test:",
    )
    return CacheManager(config)


@pytest.fixture
def disabled_cache_manager() -> CacheManager:
    """Create a CacheManager with caching disabled."""
    config = CacheConfig(enabled=False)
    return CacheManager(config)


# Async repository tests


@pytest.mark.asyncio
@pytest.mark.aiosqlite
@pytest.mark.skipif(not DOGPILE_CACHE_INSTALLED, reason="dogpile.cache not installed")
async def test_async_repository_get_uses_cache(
    aiosqlite_engine: AsyncEngine,
    memory_cache_manager: CacheManager,
    request: pytest.FixtureRequest,
) -> None:
    """Test async repository get() uses cache on second call."""
    from sqlalchemy.ext.asyncio import AsyncSession as AS
    from sqlalchemy.ext.asyncio import async_sessionmaker

    worker_id = get_worker_id(request)
    CachedAuthor = get_cached_author_model("aiosqlite", worker_id)

    # Create tables
    async with aiosqlite_engine.begin() as conn:
        await conn.run_sync(CachedAuthor.metadata.create_all)

    try:
        async_session_factory = async_sessionmaker(aiosqlite_engine, class_=AS, expire_on_commit=False)
        async with async_session_factory() as session:

            class CachedAuthorRepository(SQLAlchemyAsyncRepository[Any]):
                model_type = CachedAuthor

            repo = CachedAuthorRepository(session=session, cache_manager=memory_cache_manager, auto_expunge=True)

            # Create an author
            author = CachedAuthor(name="John Doe", bio="Author bio")
            await repo.add(author)
            await session.commit()

            author_id = author.id

            # First get - should hit database and populate cache
            author1 = await repo.get(author_id)
            assert author1.name == "John Doe"

            # Verify cache was populated
            table_name = CachedAuthor.__tablename__
            cached = memory_cache_manager.get_entity_sync(table_name, author_id, CachedAuthor)
            assert cached is not None
            assert cached.name == "John Doe"

            # Get again - should use cache
            author2 = await repo.get(author_id)
            assert author2.name == "John Doe"

    finally:
        async with aiosqlite_engine.begin() as conn:
            await conn.run_sync(CachedAuthor.metadata.drop_all)


@pytest.mark.asyncio
@pytest.mark.aiosqlite
@pytest.mark.skipif(not DOGPILE_CACHE_INSTALLED, reason="dogpile.cache not installed")
async def test_async_repository_get_use_cache_false_bypasses_cache(
    aiosqlite_engine: AsyncEngine,
    memory_cache_manager: CacheManager,
    request: pytest.FixtureRequest,
) -> None:
    """Test async repository get() with use_cache=False bypasses cache."""
    from sqlalchemy.ext.asyncio import AsyncSession as AS
    from sqlalchemy.ext.asyncio import async_sessionmaker

    worker_id = get_worker_id(request)
    CachedAuthor = get_cached_author_model("aiosqlite_bypass", worker_id)

    async with aiosqlite_engine.begin() as conn:
        await conn.run_sync(CachedAuthor.metadata.create_all)

    try:
        async_session_factory = async_sessionmaker(aiosqlite_engine, class_=AS, expire_on_commit=False)
        async with async_session_factory() as session:

            class CachedAuthorRepository(SQLAlchemyAsyncRepository[Any]):
                model_type = CachedAuthor

            repo = CachedAuthorRepository(session=session, cache_manager=memory_cache_manager, auto_expunge=True)

            # Create an author
            author = CachedAuthor(name="Jane Doe")
            await repo.add(author)
            await session.commit()

            author_id = author.id

            # Get with cache disabled
            author1 = await repo.get(author_id, use_cache=False)
            assert author1.name == "Jane Doe"

            # Cache should be empty since we used use_cache=False
            table_name = CachedAuthor.__tablename__
            cached = memory_cache_manager.get_entity_sync(table_name, author_id, CachedAuthor)
            assert cached is None

    finally:
        async with aiosqlite_engine.begin() as conn:
            await conn.run_sync(CachedAuthor.metadata.drop_all)


@pytest.mark.asyncio
@pytest.mark.aiosqlite
async def test_async_repository_without_cache_manager_works(
    aiosqlite_engine: AsyncEngine,
    request: pytest.FixtureRequest,
) -> None:
    """Test async repository works without cache_manager (cache disabled)."""
    from sqlalchemy.ext.asyncio import AsyncSession as AS
    from sqlalchemy.ext.asyncio import async_sessionmaker

    worker_id = get_worker_id(request)
    CachedAuthor = get_cached_author_model("aiosqlite_nocache", worker_id)

    async with aiosqlite_engine.begin() as conn:
        await conn.run_sync(CachedAuthor.metadata.create_all)

    try:
        async_session_factory = async_sessionmaker(aiosqlite_engine, class_=AS, expire_on_commit=False)
        async with async_session_factory() as session:

            class CachedAuthorRepository(SQLAlchemyAsyncRepository[Any]):
                model_type = CachedAuthor

            repo = CachedAuthorRepository(session=session)  # No cache_manager

            # Should work normally
            author = CachedAuthor(name="No Cache")
            await repo.add(author)
            await session.commit()

            retrieved = await repo.get(author.id)
            assert retrieved.name == "No Cache"

    finally:
        async with aiosqlite_engine.begin() as conn:
            await conn.run_sync(CachedAuthor.metadata.drop_all)


@pytest.mark.asyncio
@pytest.mark.aiosqlite
async def test_async_repository_cache_disabled_config(
    aiosqlite_engine: AsyncEngine,
    disabled_cache_manager: CacheManager,
    request: pytest.FixtureRequest,
) -> None:
    """Test async repository with disabled cache config."""
    from sqlalchemy.ext.asyncio import AsyncSession as AS
    from sqlalchemy.ext.asyncio import async_sessionmaker

    worker_id = get_worker_id(request)
    CachedAuthor = get_cached_author_model("aiosqlite_disabled", worker_id)

    async with aiosqlite_engine.begin() as conn:
        await conn.run_sync(CachedAuthor.metadata.create_all)

    try:
        async_session_factory = async_sessionmaker(aiosqlite_engine, class_=AS, expire_on_commit=False)
        async with async_session_factory() as session:

            class CachedAuthorRepository(SQLAlchemyAsyncRepository[Any]):
                model_type = CachedAuthor

            repo = CachedAuthorRepository(session=session, cache_manager=disabled_cache_manager, auto_expunge=True)

            # Should work but not cache anything
            author = CachedAuthor(name="Test")
            await repo.add(author)
            await session.commit()

            retrieved = await repo.get(author.id)
            assert retrieved.name == "Test"

    finally:
        async with aiosqlite_engine.begin() as conn:
            await conn.run_sync(CachedAuthor.metadata.drop_all)


@pytest.mark.asyncio
@pytest.mark.aiosqlite
@pytest.mark.skipif(not DOGPILE_CACHE_INSTALLED, reason="dogpile.cache not installed")
async def test_async_repository_list_uses_cache_and_invalidates_on_commit(
    aiosqlite_engine: AsyncEngine,
    memory_cache_manager: CacheManager,
    request: pytest.FixtureRequest,
) -> None:
    """Test async repository list() caching and version-token invalidation."""
    from sqlalchemy.ext.asyncio import AsyncSession as AS
    from sqlalchemy.ext.asyncio import async_sessionmaker

    worker_id = get_worker_id(request)
    CachedAuthor = get_cached_author_model("aiosqlite_list", worker_id)

    async with aiosqlite_engine.begin() as conn:
        await conn.run_sync(CachedAuthor.metadata.create_all)

    query_count = 0

    def before_cursor_execute(_conn: object, _cursor: object, statement: str, *_: object) -> None:
        nonlocal query_count
        if statement.lstrip().upper().startswith("SELECT"):
            query_count += 1

    event.listen(aiosqlite_engine.sync_engine, "before_cursor_execute", before_cursor_execute)

    try:
        async_session_factory = async_sessionmaker(aiosqlite_engine, class_=AS, expire_on_commit=False)
        async with async_session_factory() as session:

            class CachedAuthorRepository(SQLAlchemyAsyncRepository[Any]):
                model_type = CachedAuthor

            repo = CachedAuthorRepository(session=session, cache_manager=memory_cache_manager, auto_expunge=True)

            author = CachedAuthor(name="List Test", bio="Bio")
            await repo.add(author)
            await session.commit()

            # Ensure we start from a known version token
            model_name = CachedAuthor.__tablename__
            version_before = memory_cache_manager.get_model_version_sync(model_name)

            query_count = 0
            authors_1 = await repo.list()
            assert len(authors_1) == 1
            assert query_count > 0

            query_count = 0
            authors_2 = await repo.list()
            assert len(authors_2) == 1
            assert query_count == 0

            # Mutate + commit should bump model version token (invalidating list caches)
            author = await repo.get(author.id, use_cache=False)
            author.bio = "Updated"
            await repo.update(author)
            await session.commit()

            # Wait for eventual async invalidation tasks to complete
            import advanced_alchemy._listeners as listeners

            if listeners._active_cache_operations:
                await asyncio.gather(*list(listeners._active_cache_operations))

            version_after = memory_cache_manager.get_model_version_sync(model_name)
            assert version_after != version_before

            query_count = 0
            authors_3 = await repo.list()
            assert len(authors_3) == 1
            assert query_count > 0

    finally:
        event.remove(aiosqlite_engine.sync_engine, "before_cursor_execute", before_cursor_execute)
        async with aiosqlite_engine.begin() as conn:
            await conn.run_sync(CachedAuthor.metadata.drop_all)


@pytest.mark.asyncio
@pytest.mark.aiosqlite
@pytest.mark.skipif(not DOGPILE_CACHE_INSTALLED, reason="dogpile.cache not installed")
async def test_async_repository_list_and_count_uses_cache(
    aiosqlite_engine: AsyncEngine,
    memory_cache_manager: CacheManager,
    request: pytest.FixtureRequest,
) -> None:
    """Test async repository list_and_count() caching."""
    from sqlalchemy.ext.asyncio import AsyncSession as AS
    from sqlalchemy.ext.asyncio import async_sessionmaker

    worker_id = get_worker_id(request)
    CachedAuthor = get_cached_author_model("aiosqlite_list_and_count", worker_id)

    async with aiosqlite_engine.begin() as conn:
        await conn.run_sync(CachedAuthor.metadata.create_all)

    query_count = 0

    def before_cursor_execute(_conn: object, _cursor: object, statement: str, *_: object) -> None:
        nonlocal query_count
        if statement.lstrip().upper().startswith("SELECT"):
            query_count += 1

    event.listen(aiosqlite_engine.sync_engine, "before_cursor_execute", before_cursor_execute)

    try:
        async_session_factory = async_sessionmaker(aiosqlite_engine, class_=AS, expire_on_commit=False)
        async with async_session_factory() as session:

            class CachedAuthorRepository(SQLAlchemyAsyncRepository[Any]):
                model_type = CachedAuthor

            repo = CachedAuthorRepository(session=session, cache_manager=memory_cache_manager, auto_expunge=True)

            await repo.add(CachedAuthor(name="A1"))
            await repo.add(CachedAuthor(name="A2"))
            await session.commit()

            query_count = 0
            items_1, count_1 = await repo.list_and_count()
            assert count_1 == 2
            assert len(items_1) == 2
            assert query_count > 0

            query_count = 0
            items_2, count_2 = await repo.list_and_count()
            assert count_2 == 2
            assert len(items_2) == 2
            assert query_count == 0

    finally:
        event.remove(aiosqlite_engine.sync_engine, "before_cursor_execute", before_cursor_execute)
        async with aiosqlite_engine.begin() as conn:
            await conn.run_sync(CachedAuthor.metadata.drop_all)


@pytest.mark.asyncio
@pytest.mark.aiosqlite
@pytest.mark.skipif(not DOGPILE_CACHE_INSTALLED, reason="dogpile.cache not installed")
async def test_async_repository_get_singleflight_coalesces_concurrent_misses(
    aiosqlite_engine: AsyncEngine,
    memory_cache_manager: CacheManager,
    request: pytest.FixtureRequest,
) -> None:
    """Test per-process async singleflight reduces stampedes on cache miss."""
    from sqlalchemy.ext.asyncio import AsyncSession as AS
    from sqlalchemy.ext.asyncio import async_sessionmaker

    worker_id = get_worker_id(request)
    CachedAuthor = get_cached_author_model("aiosqlite_singleflight", worker_id)

    async with aiosqlite_engine.begin() as conn:
        await conn.run_sync(CachedAuthor.metadata.create_all)

    query_count = 0

    def before_cursor_execute(_conn: object, _cursor: object, statement: str, *_: object) -> None:
        nonlocal query_count
        if statement.lstrip().upper().startswith("SELECT"):
            query_count += 1

    event.listen(aiosqlite_engine.sync_engine, "before_cursor_execute", before_cursor_execute)

    try:
        async_session_factory = async_sessionmaker(aiosqlite_engine, class_=AS, expire_on_commit=False)
        async with async_session_factory() as session:

            class CachedAuthorRepository(SQLAlchemyAsyncRepository[Any]):
                model_type = CachedAuthor

            repo = CachedAuthorRepository(session=session, cache_manager=memory_cache_manager, auto_expunge=True)

            author = CachedAuthor(name="SF")
            await repo.add(author)
            await session.commit()

            author_id = author.id
            model_name = CachedAuthor.__tablename__

            # Force cache miss for this entity
            memory_cache_manager.invalidate_entity_sync(model_name, author_id)

            query_count = 0
            results = await asyncio.gather(*[repo.get(author_id) for _ in range(10)])
            assert all(r.id == author_id for r in results)
            assert query_count == 1

    finally:
        event.remove(aiosqlite_engine.sync_engine, "before_cursor_execute", before_cursor_execute)
        async with aiosqlite_engine.begin() as conn:
            await conn.run_sync(CachedAuthor.metadata.drop_all)


# Sync repository tests


@pytest.mark.sqlite
@pytest.mark.skipif(not DOGPILE_CACHE_INSTALLED, reason="dogpile.cache not installed")
def test_sync_repository_get_uses_cache(
    sqlite_engine: Engine,
    memory_cache_manager: CacheManager,
    request: pytest.FixtureRequest,
) -> None:
    """Test sync repository get() uses cache on second call."""
    from sqlalchemy.orm import sessionmaker

    worker_id = get_worker_id(request)
    CachedAuthor = get_cached_author_model("sqlite", worker_id)

    CachedAuthor.metadata.create_all(sqlite_engine)

    try:
        session_factory = sessionmaker(sqlite_engine)
        with session_factory() as session:

            class CachedAuthorRepository(SQLAlchemySyncRepository[Any]):
                model_type = CachedAuthor

            repo = CachedAuthorRepository(session=session, cache_manager=memory_cache_manager, auto_expunge=True)

            # Create an author
            author = CachedAuthor(name="John Doe", bio="Author bio")
            repo.add(author)
            session.commit()

            author_id = author.id

            # First get - should hit database and populate cache
            author1 = repo.get(author_id)
            assert author1.name == "John Doe"

            # Verify cache was populated
            table_name = CachedAuthor.__tablename__
            cached = memory_cache_manager.get_entity_sync(table_name, author_id, CachedAuthor)
            assert cached is not None
            assert cached.name == "John Doe"

    finally:
        CachedAuthor.metadata.drop_all(sqlite_engine)


@pytest.mark.sqlite
def test_sync_repository_without_cache_manager_works(
    sqlite_engine: Engine,
    request: pytest.FixtureRequest,
) -> None:
    """Test sync repository works without cache_manager."""
    from sqlalchemy.orm import sessionmaker

    worker_id = get_worker_id(request)
    CachedAuthor = get_cached_author_model("sqlite_nocache", worker_id)

    CachedAuthor.metadata.create_all(sqlite_engine)

    try:
        session_factory = sessionmaker(sqlite_engine)
        with session_factory() as session:

            class CachedAuthorRepository(SQLAlchemySyncRepository[Any]):
                model_type = CachedAuthor

            repo = CachedAuthorRepository(session=session)  # No cache_manager

            author = CachedAuthor(name="No Cache Sync")
            repo.add(author)
            session.commit()

            retrieved = repo.get(author.id)
            assert retrieved.name == "No Cache Sync"

    finally:
        CachedAuthor.metadata.drop_all(sqlite_engine)
