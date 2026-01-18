"""Integration tests for repository caching with bind_group support.

These tests verify that cache keys properly include bind_group for multi-master
database configurations, preventing data leaks between database shards.
"""

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


def get_bind_group_author_model(engine_dialect_name: str, worker_id: str) -> type[DeclarativeBase]:
    """Create appropriate model for bind_group tests."""
    global _class_counter
    cache_key = f"bind_group_author_{worker_id}_{engine_dialect_name}"

    if cache_key not in _model_cache:

        class TestBase(DeclarativeBase):
            pass

        _class_counter += 1
        unique_suffix = f"{_class_counter}_{worker_id}_{engine_dialect_name}"

        class_name = f"BindGroupAuthor_{unique_suffix}"

        BindGroupAuthor = type(
            class_name,
            (UUIDBase, TestBase),
            {
                "__tablename__": f"test_bind_group_authors_{worker_id}_{engine_dialect_name}",
                "__mapper_args__": {"concrete": True},
                "__module__": __name__,
                "name": mapped_column(String(length=100)),
                "bio": mapped_column(String(length=500), nullable=True),
                "__annotations__": {"name": Mapped[str], "bio": Mapped[Optional[str]]},
            },
        )

        _model_cache[cache_key] = BindGroupAuthor

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
        key_prefix="test_bind_group:",
    )
    return CacheManager(config)


# ============================================================================
# Cache Invalidation Tracker Tests
# ============================================================================


@pytest.mark.skipif(not DOGPILE_CACHE_INSTALLED, reason="dogpile.cache not installed")
def test_cache_invalidation_tracker_add_invalidation_with_bind_group(memory_cache_manager: CacheManager) -> None:
    """Test CacheInvalidationTracker stores bind_group with invalidations."""
    from advanced_alchemy._listeners import CacheInvalidationTracker

    tracker = CacheInvalidationTracker(memory_cache_manager)

    # Add invalidations with different bind_groups
    tracker.add_invalidation("model_a", "id1", bind_group=None)
    tracker.add_invalidation("model_a", "id2", bind_group="shard_a")
    tracker.add_invalidation("model_b", "id3", bind_group="shard_b")

    # Verify pending invalidations stored correctly
    assert len(tracker._pending_invalidations) == 3
    assert ("model_a", "id1", None) in tracker._pending_invalidations
    assert ("model_a", "id2", "shard_a") in tracker._pending_invalidations
    assert ("model_b", "id3", "shard_b") in tracker._pending_invalidations

    # Verify model bumps queued
    assert "model_a" in tracker._pending_model_bumps
    assert "model_b" in tracker._pending_model_bumps


@pytest.mark.skipif(not DOGPILE_CACHE_INSTALLED, reason="dogpile.cache not installed")
def test_cache_invalidation_tracker_rollback_clears_pending(memory_cache_manager: CacheManager) -> None:
    """Test CacheInvalidationTracker rollback clears all pending invalidations."""
    from advanced_alchemy._listeners import CacheInvalidationTracker

    tracker = CacheInvalidationTracker(memory_cache_manager)

    tracker.add_invalidation("model", "id1", bind_group="shard_a")
    tracker.add_invalidation("model", "id2", bind_group="shard_b")

    # Verify pending invalidations exist
    assert len(tracker._pending_invalidations) == 2
    assert len(tracker._pending_model_bumps) == 1

    # Rollback should clear everything
    tracker.rollback()

    assert len(tracker._pending_invalidations) == 0
    assert len(tracker._pending_model_bumps) == 0


# ============================================================================
# Async Repository Tests with bind_group
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.aiosqlite
@pytest.mark.skipif(not DOGPILE_CACHE_INSTALLED, reason="dogpile.cache not installed")
async def test_async_repository_get_with_bind_group_uses_separate_cache(
    aiosqlite_engine: AsyncEngine,
    memory_cache_manager: CacheManager,
    request: pytest.FixtureRequest,
) -> None:
    """Test async repository get() with bind_group uses separate cache entries."""
    from sqlalchemy.ext.asyncio import AsyncSession as AS
    from sqlalchemy.ext.asyncio import async_sessionmaker

    worker_id = get_worker_id(request)
    BindGroupAuthor = get_bind_group_author_model("aiosqlite_bind", worker_id)

    async with aiosqlite_engine.begin() as conn:
        await conn.run_sync(BindGroupAuthor.metadata.create_all)

    try:
        async_session_factory = async_sessionmaker(aiosqlite_engine, class_=AS, expire_on_commit=False)
        async with async_session_factory() as session:

            class BindGroupAuthorRepository(SQLAlchemyAsyncRepository[Any]):
                model_type = BindGroupAuthor

            repo = BindGroupAuthorRepository(session=session, cache_manager=memory_cache_manager, auto_expunge=True)

            # Create an author
            author = BindGroupAuthor(name="Test Author", bio="Bio")
            await repo.add(author)
            await session.commit()

            author_id = author.id
            table_name = BindGroupAuthor.__tablename__

            # Get without bind_group - should cache to default key
            author1 = await repo.get(author_id)
            assert author1.name == "Test Author"

            # Verify default cache was populated
            cached_default = memory_cache_manager.get_entity_sync(table_name, author_id, BindGroupAuthor, bind_group=None)
            assert cached_default is not None

            # Get with bind_group="shard_a" - should cache to shard_a key
            author2 = await repo.get(author_id, bind_group="shard_a")
            assert author2.name == "Test Author"

            # Verify shard_a cache was populated
            cached_shard_a = memory_cache_manager.get_entity_sync(table_name, author_id, BindGroupAuthor, bind_group="shard_a")
            assert cached_shard_a is not None

            # Invalidate only shard_a cache
            memory_cache_manager.invalidate_entity_sync(table_name, author_id, bind_group="shard_a")

            # Verify default cache still exists
            cached_default_after = memory_cache_manager.get_entity_sync(table_name, author_id, BindGroupAuthor, bind_group=None)
            assert cached_default_after is not None, "Default cache should still exist"

            # Verify shard_a cache was invalidated
            cached_shard_a_after = memory_cache_manager.get_entity_sync(table_name, author_id, BindGroupAuthor, bind_group="shard_a")
            assert cached_shard_a_after is None, "shard_a cache should be invalidated"

    finally:
        async with aiosqlite_engine.begin() as conn:
            await conn.run_sync(BindGroupAuthor.metadata.drop_all)


@pytest.mark.asyncio
@pytest.mark.aiosqlite
@pytest.mark.skipif(not DOGPILE_CACHE_INSTALLED, reason="dogpile.cache not installed")
async def test_async_repository_singleflight_key_includes_bind_group(
    aiosqlite_engine: AsyncEngine,
    memory_cache_manager: CacheManager,
    request: pytest.FixtureRequest,
) -> None:
    """Test that singleflight deduplication includes bind_group in key."""
    from sqlalchemy.ext.asyncio import AsyncSession as AS
    from sqlalchemy.ext.asyncio import async_sessionmaker

    worker_id = get_worker_id(request)
    BindGroupAuthor = get_bind_group_author_model("aiosqlite_sf", worker_id)

    async with aiosqlite_engine.begin() as conn:
        await conn.run_sync(BindGroupAuthor.metadata.create_all)

    query_count = 0

    def before_cursor_execute(_conn: object, _cursor: object, statement: str, *_: object) -> None:
        nonlocal query_count
        if statement.lstrip().upper().startswith("SELECT"):
            query_count += 1

    event.listen(aiosqlite_engine.sync_engine, "before_cursor_execute", before_cursor_execute)

    try:
        async_session_factory = async_sessionmaker(aiosqlite_engine, class_=AS, expire_on_commit=False)
        async with async_session_factory() as session:

            class BindGroupAuthorRepository(SQLAlchemyAsyncRepository[Any]):
                model_type = BindGroupAuthor

            repo = BindGroupAuthorRepository(session=session, cache_manager=memory_cache_manager, auto_expunge=True)

            author = BindGroupAuthor(name="SF Author")
            await repo.add(author)
            await session.commit()

            author_id = author.id
            table_name = BindGroupAuthor.__tablename__

            # Invalidate cache to force misses
            memory_cache_manager.invalidate_entity_sync(table_name, author_id, bind_group=None)
            memory_cache_manager.invalidate_entity_sync(table_name, author_id, bind_group="shard_a")

            # Concurrent gets without bind_group should coalesce
            query_count = 0
            results_default = await asyncio.gather(*[repo.get(author_id) for _ in range(5)])
            assert all(r.id == author_id for r in results_default)
            queries_default = query_count

            # Concurrent gets with bind_group="shard_a" should coalesce separately
            query_count = 0
            results_shard_a = await asyncio.gather(*[repo.get(author_id, bind_group="shard_a") for _ in range(5)])
            assert all(r.id == author_id for r in results_shard_a)
            queries_shard_a = query_count

            # Both should have coalesced to 1 query each
            assert queries_default == 1, "Default queries should coalesce"
            assert queries_shard_a == 1, "shard_a queries should coalesce"

    finally:
        event.remove(aiosqlite_engine.sync_engine, "before_cursor_execute", before_cursor_execute)
        async with aiosqlite_engine.begin() as conn:
            await conn.run_sync(BindGroupAuthor.metadata.drop_all)


@pytest.mark.asyncio
@pytest.mark.aiosqlite
@pytest.mark.skipif(not DOGPILE_CACHE_INSTALLED, reason="dogpile.cache not installed")
async def test_async_repository_get_bypasses_cache_when_disabled(
    aiosqlite_engine: AsyncEngine,
    memory_cache_manager: CacheManager,
    request: pytest.FixtureRequest,
) -> None:
    """Test async repository get() with use_cache=False bypasses cache regardless of bind_group."""
    from sqlalchemy.ext.asyncio import AsyncSession as AS
    from sqlalchemy.ext.asyncio import async_sessionmaker

    worker_id = get_worker_id(request)
    BindGroupAuthor = get_bind_group_author_model("aiosqlite_bypass", worker_id)

    async with aiosqlite_engine.begin() as conn:
        await conn.run_sync(BindGroupAuthor.metadata.create_all)

    try:
        async_session_factory = async_sessionmaker(aiosqlite_engine, class_=AS, expire_on_commit=False)
        async with async_session_factory() as session:

            class BindGroupAuthorRepository(SQLAlchemyAsyncRepository[Any]):
                model_type = BindGroupAuthor

            repo = BindGroupAuthorRepository(session=session, cache_manager=memory_cache_manager, auto_expunge=True)

            author = BindGroupAuthor(name="No Cache Author")
            await repo.add(author)
            await session.commit()

            author_id = author.id
            table_name = BindGroupAuthor.__tablename__

            # Get with cache disabled and bind_group
            await repo.get(author_id, use_cache=False, bind_group="shard_a")

            # Cache should not be populated
            cached = memory_cache_manager.get_entity_sync(table_name, author_id, BindGroupAuthor, bind_group="shard_a")
            assert cached is None, "Cache should not be populated when use_cache=False"

    finally:
        async with aiosqlite_engine.begin() as conn:
            await conn.run_sync(BindGroupAuthor.metadata.drop_all)


# ============================================================================
# Sync Repository Tests with bind_group
# ============================================================================


@pytest.mark.sqlite
@pytest.mark.skipif(not DOGPILE_CACHE_INSTALLED, reason="dogpile.cache not installed")
def test_sync_repository_get_with_bind_group_uses_separate_cache(
    sqlite_engine: Engine,
    memory_cache_manager: CacheManager,
    request: pytest.FixtureRequest,
) -> None:
    """Test sync repository get() with bind_group uses separate cache entries."""
    from sqlalchemy.orm import sessionmaker

    worker_id = get_worker_id(request)
    BindGroupAuthor = get_bind_group_author_model("sqlite_bind", worker_id)

    BindGroupAuthor.metadata.create_all(sqlite_engine)

    try:
        session_factory = sessionmaker(sqlite_engine)
        with session_factory() as session:

            class BindGroupAuthorRepository(SQLAlchemySyncRepository[Any]):
                model_type = BindGroupAuthor

            repo = BindGroupAuthorRepository(session=session, cache_manager=memory_cache_manager, auto_expunge=True)

            # Create an author
            author = BindGroupAuthor(name="Test Author", bio="Bio")
            repo.add(author)
            session.commit()

            author_id = author.id
            table_name = BindGroupAuthor.__tablename__

            # Get without bind_group
            author1 = repo.get(author_id)
            assert author1.name == "Test Author"

            # Verify default cache was populated
            cached_default = memory_cache_manager.get_entity_sync(table_name, author_id, BindGroupAuthor, bind_group=None)
            assert cached_default is not None

            # Get with bind_group="shard_a"
            author2 = repo.get(author_id, bind_group="shard_a")
            assert author2.name == "Test Author"

            # Verify shard_a cache was populated
            cached_shard_a = memory_cache_manager.get_entity_sync(table_name, author_id, BindGroupAuthor, bind_group="shard_a")
            assert cached_shard_a is not None

            # Invalidate only shard_a
            memory_cache_manager.invalidate_entity_sync(table_name, author_id, bind_group="shard_a")

            # Verify default still cached, shard_a invalidated
            assert memory_cache_manager.get_entity_sync(table_name, author_id, BindGroupAuthor, bind_group=None) is not None
            assert memory_cache_manager.get_entity_sync(table_name, author_id, BindGroupAuthor, bind_group="shard_a") is None

    finally:
        BindGroupAuthor.metadata.drop_all(sqlite_engine)


@pytest.mark.sqlite
@pytest.mark.skipif(not DOGPILE_CACHE_INSTALLED, reason="dogpile.cache not installed")
def test_sync_repository_get_bypasses_cache_when_disabled(
    sqlite_engine: Engine,
    memory_cache_manager: CacheManager,
    request: pytest.FixtureRequest,
) -> None:
    """Test sync repository get() with use_cache=False bypasses cache regardless of bind_group."""
    from sqlalchemy.orm import sessionmaker

    worker_id = get_worker_id(request)
    BindGroupAuthor = get_bind_group_author_model("sqlite_bypass", worker_id)

    BindGroupAuthor.metadata.create_all(sqlite_engine)

    try:
        session_factory = sessionmaker(sqlite_engine)
        with session_factory() as session:

            class BindGroupAuthorRepository(SQLAlchemySyncRepository[Any]):
                model_type = BindGroupAuthor

            repo = BindGroupAuthorRepository(session=session, cache_manager=memory_cache_manager, auto_expunge=True)

            author = BindGroupAuthor(name="No Cache")
            repo.add(author)
            session.commit()

            author_id = author.id
            table_name = BindGroupAuthor.__tablename__

            # Get with cache disabled and bind_group
            repo.get(author_id, use_cache=False, bind_group="shard_a")

            # Cache should not be populated
            cached = memory_cache_manager.get_entity_sync(table_name, author_id, BindGroupAuthor, bind_group="shard_a")
            assert cached is None, "Cache should not be populated when use_cache=False"

    finally:
        BindGroupAuthor.metadata.drop_all(sqlite_engine)


# ============================================================================
# Repository default bind_group Tests
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.aiosqlite
@pytest.mark.skipif(not DOGPILE_CACHE_INSTALLED, reason="dogpile.cache not installed")
async def test_async_repository_uses_default_bind_group_for_cache(
    aiosqlite_engine: AsyncEngine,
    memory_cache_manager: CacheManager,
    request: pytest.FixtureRequest,
) -> None:
    """Test that repository uses default bind_group from constructor for cache keys."""
    from sqlalchemy.ext.asyncio import AsyncSession as AS
    from sqlalchemy.ext.asyncio import async_sessionmaker

    worker_id = get_worker_id(request)
    BindGroupAuthor = get_bind_group_author_model("aiosqlite_default", worker_id)

    async with aiosqlite_engine.begin() as conn:
        await conn.run_sync(BindGroupAuthor.metadata.create_all)

    try:
        async_session_factory = async_sessionmaker(aiosqlite_engine, class_=AS, expire_on_commit=False)
        async with async_session_factory() as session:

            class BindGroupAuthorRepository(SQLAlchemyAsyncRepository[Any]):
                model_type = BindGroupAuthor

            # Create repo with default bind_group via constructor parameter
            repo = BindGroupAuthorRepository(
                session=session,
                cache_manager=memory_cache_manager,
                auto_expunge=True,
                bind_group="default_shard",
            )

            author = BindGroupAuthor(name="Default Shard Author")
            await repo.add(author)
            await session.commit()

            author_id = author.id
            table_name = BindGroupAuthor.__tablename__

            # Get without explicit bind_group - should use default from constructor
            await repo.get(author_id)

            # Verify cache was populated for default_shard bind_group
            cached = memory_cache_manager.get_entity_sync(table_name, author_id, BindGroupAuthor, bind_group="default_shard")
            assert cached is not None, "Cache should use default bind_group from constructor"

            # Verify no cache for None bind_group
            cached_none = memory_cache_manager.get_entity_sync(table_name, author_id, BindGroupAuthor, bind_group=None)
            assert cached_none is None, "No cache should exist for None bind_group"

    finally:
        async with aiosqlite_engine.begin() as conn:
            await conn.run_sync(BindGroupAuthor.metadata.drop_all)


@pytest.mark.asyncio
@pytest.mark.aiosqlite
@pytest.mark.skipif(not DOGPILE_CACHE_INSTALLED, reason="dogpile.cache not installed")
async def test_async_repository_explicit_bind_group_overrides_default(
    aiosqlite_engine: AsyncEngine,
    memory_cache_manager: CacheManager,
    request: pytest.FixtureRequest,
) -> None:
    """Test that explicit bind_group parameter overrides repository default."""
    from sqlalchemy.ext.asyncio import AsyncSession as AS
    from sqlalchemy.ext.asyncio import async_sessionmaker

    worker_id = get_worker_id(request)
    BindGroupAuthor = get_bind_group_author_model("aiosqlite_override", worker_id)

    async with aiosqlite_engine.begin() as conn:
        await conn.run_sync(BindGroupAuthor.metadata.create_all)

    try:
        async_session_factory = async_sessionmaker(aiosqlite_engine, class_=AS, expire_on_commit=False)
        async with async_session_factory() as session:

            class BindGroupAuthorRepository(SQLAlchemyAsyncRepository[Any]):
                model_type = BindGroupAuthor

            # Create repo with default bind_group via constructor
            repo = BindGroupAuthorRepository(
                session=session,
                cache_manager=memory_cache_manager,
                auto_expunge=True,
                bind_group="default_shard",
            )

            author = BindGroupAuthor(name="Override Test")
            await repo.add(author)
            await session.commit()

            author_id = author.id
            table_name = BindGroupAuthor.__tablename__

            # Get with explicit bind_group override
            await repo.get(author_id, bind_group="override_shard")

            # Verify cache was populated for override_shard, not default_shard
            cached_override = memory_cache_manager.get_entity_sync(table_name, author_id, BindGroupAuthor, bind_group="override_shard")
            cached_default = memory_cache_manager.get_entity_sync(table_name, author_id, BindGroupAuthor, bind_group="default_shard")

            assert cached_override is not None, "Cache should be for override_shard"
            assert cached_default is None, "No cache for default_shard when overridden"

    finally:
        async with aiosqlite_engine.begin() as conn:
            await conn.run_sync(BindGroupAuthor.metadata.drop_all)


# ============================================================================
# Cache Manager Direct Tests (using model instances)
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.aiosqlite
@pytest.mark.skipif(not DOGPILE_CACHE_INSTALLED, reason="dogpile.cache not installed")
async def test_cache_manager_entity_methods_with_bind_group(
    aiosqlite_engine: AsyncEngine,
    memory_cache_manager: CacheManager,
    request: pytest.FixtureRequest,
) -> None:
    """Test CacheManager entity methods correctly handle bind_group in cache keys."""
    from sqlalchemy.ext.asyncio import AsyncSession as AS
    from sqlalchemy.ext.asyncio import async_sessionmaker

    worker_id = get_worker_id(request)
    BindGroupAuthor = get_bind_group_author_model("aiosqlite_cm", worker_id)

    async with aiosqlite_engine.begin() as conn:
        await conn.run_sync(BindGroupAuthor.metadata.create_all)

    try:
        async_session_factory = async_sessionmaker(aiosqlite_engine, class_=AS, expire_on_commit=False)
        async with async_session_factory() as session:
            # Create a model instance
            author = BindGroupAuthor(name="Cache Manager Test")
            session.add(author)
            await session.commit()

            author_id = author.id
            table_name = BindGroupAuthor.__tablename__

            # Test set_entity_sync with different bind_groups
            memory_cache_manager.set_entity_sync(table_name, author_id, author, bind_group=None)

            # Modify for shard_a (simulate different data in shard)
            author.name = "Shard A Data"
            memory_cache_manager.set_entity_sync(table_name, author_id, author, bind_group="shard_a")

            # Modify for shard_b
            author.name = "Shard B Data"
            memory_cache_manager.set_entity_sync(table_name, author_id, author, bind_group="shard_b")

            # Test get_entity_sync returns correct cached entity per bind_group
            cached_default = memory_cache_manager.get_entity_sync(table_name, author_id, BindGroupAuthor, bind_group=None)
            cached_shard_a = memory_cache_manager.get_entity_sync(table_name, author_id, BindGroupAuthor, bind_group="shard_a")
            cached_shard_b = memory_cache_manager.get_entity_sync(table_name, author_id, BindGroupAuthor, bind_group="shard_b")

            assert cached_default is not None
            assert cached_shard_a is not None
            assert cached_shard_b is not None

            # Names should reflect what was cached at the time
            assert cached_default.name == "Cache Manager Test"
            assert cached_shard_a.name == "Shard A Data"
            assert cached_shard_b.name == "Shard B Data"

            # Test invalidate_entity_sync only affects specific bind_group
            memory_cache_manager.invalidate_entity_sync(table_name, author_id, bind_group="shard_a")

            # Verify only shard_a was invalidated
            assert memory_cache_manager.get_entity_sync(table_name, author_id, BindGroupAuthor, bind_group=None) is not None
            assert memory_cache_manager.get_entity_sync(table_name, author_id, BindGroupAuthor, bind_group="shard_a") is None
            assert memory_cache_manager.get_entity_sync(table_name, author_id, BindGroupAuthor, bind_group="shard_b") is not None

    finally:
        async with aiosqlite_engine.begin() as conn:
            await conn.run_sync(BindGroupAuthor.metadata.drop_all)


@pytest.mark.asyncio
@pytest.mark.aiosqlite
@pytest.mark.skipif(not DOGPILE_CACHE_INSTALLED, reason="dogpile.cache not installed")
async def test_cache_manager_async_entity_methods_with_bind_group(
    aiosqlite_engine: AsyncEngine,
    memory_cache_manager: CacheManager,
    request: pytest.FixtureRequest,
) -> None:
    """Test CacheManager async entity methods correctly handle bind_group in cache keys."""
    from sqlalchemy.ext.asyncio import AsyncSession as AS
    from sqlalchemy.ext.asyncio import async_sessionmaker

    worker_id = get_worker_id(request)
    BindGroupAuthor = get_bind_group_author_model("aiosqlite_cm_async", worker_id)

    async with aiosqlite_engine.begin() as conn:
        await conn.run_sync(BindGroupAuthor.metadata.create_all)

    try:
        async_session_factory = async_sessionmaker(aiosqlite_engine, class_=AS, expire_on_commit=False)
        async with async_session_factory() as session:
            author = BindGroupAuthor(name="Async Cache Test")
            session.add(author)
            await session.commit()

            author_id = author.id
            table_name = BindGroupAuthor.__tablename__

            # Test async set/get with bind_groups
            await memory_cache_manager.set_entity_async(table_name, author_id, author, bind_group=None)

            author.name = "Shard A Async"
            await memory_cache_manager.set_entity_async(table_name, author_id, author, bind_group="shard_a")

            # Verify both cached correctly
            cached_default = await memory_cache_manager.get_entity_async(table_name, author_id, BindGroupAuthor, bind_group=None)
            cached_shard_a = await memory_cache_manager.get_entity_async(table_name, author_id, BindGroupAuthor, bind_group="shard_a")

            assert cached_default is not None
            assert cached_shard_a is not None
            assert cached_default.name == "Async Cache Test"
            assert cached_shard_a.name == "Shard A Async"

            # Test async invalidation
            await memory_cache_manager.invalidate_entity_async(table_name, author_id, bind_group="shard_a")

            # Verify only shard_a was invalidated
            assert await memory_cache_manager.get_entity_async(table_name, author_id, BindGroupAuthor, bind_group=None) is not None
            assert await memory_cache_manager.get_entity_async(table_name, author_id, BindGroupAuthor, bind_group="shard_a") is None

    finally:
        async with aiosqlite_engine.begin() as conn:
            await conn.run_sync(BindGroupAuthor.metadata.drop_all)


# ============================================================================
# Cache Invalidation Tracker with Commit Tests
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.aiosqlite
@pytest.mark.skipif(not DOGPILE_CACHE_INSTALLED, reason="dogpile.cache not installed")
async def test_cache_invalidation_tracker_commit_with_bind_group(
    aiosqlite_engine: AsyncEngine,
    memory_cache_manager: CacheManager,
    request: pytest.FixtureRequest,
) -> None:
    """Test CacheInvalidationTracker commit properly invalidates with bind_group."""
    from sqlalchemy.ext.asyncio import AsyncSession as AS
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from advanced_alchemy._listeners import CacheInvalidationTracker

    worker_id = get_worker_id(request)
    BindGroupAuthor = get_bind_group_author_model("aiosqlite_tracker", worker_id)

    async with aiosqlite_engine.begin() as conn:
        await conn.run_sync(BindGroupAuthor.metadata.create_all)

    try:
        async_session_factory = async_sessionmaker(aiosqlite_engine, class_=AS, expire_on_commit=False)
        async with async_session_factory() as session:
            author = BindGroupAuthor(name="Tracker Test")
            session.add(author)
            await session.commit()

            author_id = author.id
            table_name = BindGroupAuthor.__tablename__

            # Pre-populate cache for different bind_groups
            memory_cache_manager.set_entity_sync(table_name, author_id, author, bind_group=None)
            memory_cache_manager.set_entity_sync(table_name, author_id, author, bind_group="shard_a")
            memory_cache_manager.set_entity_sync(table_name, author_id, author, bind_group="shard_b")

            # Create tracker and add invalidation for shard_a only
            tracker = CacheInvalidationTracker(memory_cache_manager)
            tracker.add_invalidation(table_name, author_id, bind_group="shard_a")

            # Commit the tracker (sync)
            tracker.commit()

            # Verify only shard_a was invalidated
            assert memory_cache_manager.get_entity_sync(table_name, author_id, BindGroupAuthor, bind_group=None) is not None
            assert memory_cache_manager.get_entity_sync(table_name, author_id, BindGroupAuthor, bind_group="shard_a") is None
            assert memory_cache_manager.get_entity_sync(table_name, author_id, BindGroupAuthor, bind_group="shard_b") is not None

    finally:
        async with aiosqlite_engine.begin() as conn:
            await conn.run_sync(BindGroupAuthor.metadata.drop_all)


@pytest.mark.asyncio
@pytest.mark.aiosqlite
@pytest.mark.skipif(not DOGPILE_CACHE_INSTALLED, reason="dogpile.cache not installed")
async def test_cache_invalidation_tracker_async_commit_with_bind_group(
    aiosqlite_engine: AsyncEngine,
    memory_cache_manager: CacheManager,
    request: pytest.FixtureRequest,
) -> None:
    """Test CacheInvalidationTracker async commit properly invalidates with bind_group."""
    from sqlalchemy.ext.asyncio import AsyncSession as AS
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from advanced_alchemy._listeners import CacheInvalidationTracker

    worker_id = get_worker_id(request)
    BindGroupAuthor = get_bind_group_author_model("aiosqlite_tracker_async", worker_id)

    async with aiosqlite_engine.begin() as conn:
        await conn.run_sync(BindGroupAuthor.metadata.create_all)

    try:
        async_session_factory = async_sessionmaker(aiosqlite_engine, class_=AS, expire_on_commit=False)
        async with async_session_factory() as session:
            author = BindGroupAuthor(name="Async Tracker Test")
            session.add(author)
            await session.commit()

            author_id = author.id
            table_name = BindGroupAuthor.__tablename__

            # Pre-populate cache
            await memory_cache_manager.set_entity_async(table_name, author_id, author, bind_group=None)
            await memory_cache_manager.set_entity_async(table_name, author_id, author, bind_group="shard_a")

            # Create tracker and add invalidation
            tracker = CacheInvalidationTracker(memory_cache_manager)
            tracker.add_invalidation(table_name, author_id, bind_group="shard_a")

            # Async commit
            await tracker.commit_async()

            # Verify only shard_a was invalidated
            assert await memory_cache_manager.get_entity_async(table_name, author_id, BindGroupAuthor, bind_group=None) is not None
            assert await memory_cache_manager.get_entity_async(table_name, author_id, BindGroupAuthor, bind_group="shard_a") is None

    finally:
        async with aiosqlite_engine.begin() as conn:
            await conn.run_sync(BindGroupAuthor.metadata.drop_all)
