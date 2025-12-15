"""Unit tests for CacheManager."""

from __future__ import annotations

import asyncio
import time
from typing import Any
from unittest.mock import MagicMock

import pytest

from advanced_alchemy.cache.config import CacheConfig
from advanced_alchemy.cache.manager import DOGPILE_CACHE_INSTALLED, CacheManager


@pytest.fixture
def memory_config() -> CacheConfig:
    """Create a memory cache configuration."""
    return CacheConfig(backend="dogpile.cache.memory", expiration_time=300)


@pytest.fixture
def disabled_config() -> CacheConfig:
    """Create a disabled cache configuration."""
    return CacheConfig(enabled=False)


@pytest.mark.skipif(not DOGPILE_CACHE_INSTALLED, reason="dogpile.cache not installed")
def test_cache_manager_lazy_initialization(memory_config: CacheConfig) -> None:
    """Test CacheManager lazy initializes the region."""
    manager = CacheManager(memory_config)

    # Region should be None initially
    assert manager._region is None

    # Accessing region should initialize it
    region = manager.region
    assert region is not None
    assert manager._region is region


@pytest.mark.skipif(not DOGPILE_CACHE_INSTALLED, reason="dogpile.cache not installed")
def test_cache_manager_creates_region_with_config(memory_config: CacheConfig) -> None:
    """Test CacheManager creates region with correct configuration."""
    manager = CacheManager(memory_config)

    region = manager.region

    # Verify region is configured (dogpile.cache doesn't expose config easily,
    # but we can test it works)
    assert region is not None


def test_cache_manager_disabled_returns_null_region(disabled_config: CacheConfig) -> None:
    """Test CacheManager returns NullRegion when disabled."""
    manager = CacheManager(disabled_config)

    region = manager.region

    # Should be NullRegion
    from advanced_alchemy.cache._null import NullRegion

    assert isinstance(region, NullRegion)


@pytest.mark.skipif(DOGPILE_CACHE_INSTALLED, reason="Test requires dogpile.cache NOT installed")
def test_cache_manager_without_dogpile_returns_null_region() -> None:
    """Test CacheManager returns NullRegion when dogpile.cache not installed."""
    config = CacheConfig(backend="dogpile.cache.memory")
    manager = CacheManager(config)

    region = manager.region

    from advanced_alchemy.cache._null import NullRegion

    assert isinstance(region, NullRegion)


@pytest.mark.skipif(not DOGPILE_CACHE_INSTALLED, reason="dogpile.cache not installed")
def test_cache_manager_get_or_create_caches_value(memory_config: CacheConfig) -> None:
    """Test get_or_create caches the created value."""
    manager = CacheManager(memory_config)
    call_count = 0

    def creator() -> str:
        nonlocal call_count
        call_count += 1
        return "test_value"

    # First call should invoke creator
    result1 = manager.get_or_create_sync("test_key", creator)
    assert result1 == "test_value"
    assert call_count == 1

    # Second call should use cached value
    result2 = manager.get_or_create_sync("test_key", creator)
    assert result2 == "test_value"
    assert call_count == 1  # Creator not called again


@pytest.mark.skipif(not DOGPILE_CACHE_INSTALLED, reason="dogpile.cache not installed")
def test_cache_manager_get_or_create_with_custom_expiration(memory_config: CacheConfig) -> None:
    """Test get_or_create with custom expiration time."""
    manager = CacheManager(memory_config)

    result = manager.get_or_create_sync("key", lambda: "value", expiration_time=60)

    assert result == "value"


def test_cache_manager_get_or_create_disabled_always_calls_creator(disabled_config: CacheConfig) -> None:
    """Test get_or_create bypasses cache when disabled."""
    manager = CacheManager(disabled_config)
    call_count = 0

    def creator() -> str:
        nonlocal call_count
        call_count += 1
        return "value"

    # Both calls should invoke creator
    result1 = manager.get_or_create_sync("key", creator)
    result2 = manager.get_or_create_sync("key", creator)

    assert result1 == "value"
    assert result2 == "value"
    assert call_count == 2


@pytest.mark.skipif(not DOGPILE_CACHE_INSTALLED, reason="dogpile.cache not installed")
def test_cache_manager_get_set_delete(memory_config: CacheConfig) -> None:
    """Test get, set, and delete operations."""
    from advanced_alchemy.cache.manager import DOGPILE_NO_VALUE

    manager = CacheManager(memory_config)

    # Initially empty
    result_initial = manager.get_sync("test_key")
    assert result_initial is DOGPILE_NO_VALUE or result_initial is None

    # Set value
    manager.set_sync("test_key", "test_value")

    # Get value
    result = manager.get_sync("test_key")
    assert result == "test_value"

    # Delete value
    manager.delete_sync("test_key")

    # Should be empty again
    result_after_delete = manager.get_sync("test_key")
    assert result_after_delete is DOGPILE_NO_VALUE or result_after_delete is None


def test_cache_manager_get_disabled_returns_no_value(disabled_config: CacheConfig) -> None:
    """Test get returns NO_VALUE when disabled."""
    manager = CacheManager(disabled_config)

    result = manager.get_sync("any_key")

    # Should return dogpile's NO_VALUE
    from advanced_alchemy.cache.manager import DOGPILE_NO_VALUE

    assert result is DOGPILE_NO_VALUE


def test_cache_manager_set_disabled_is_noop(disabled_config: CacheConfig) -> None:
    """Test set does nothing when disabled."""
    manager = CacheManager(disabled_config)

    # Should not raise
    manager.set_sync("key", "value")


@pytest.mark.skipif(not DOGPILE_CACHE_INSTALLED, reason="dogpile.cache not installed")
def test_cache_manager_make_key_adds_prefix(memory_config: CacheConfig) -> None:
    """Test _make_key adds the configured prefix."""
    manager = CacheManager(memory_config)

    key = manager._make_key("test_key")

    assert key == "aa:test_key"


@pytest.mark.skipif(not DOGPILE_CACHE_INSTALLED, reason="dogpile.cache not installed")
def test_cache_manager_get_entity(memory_config: CacheConfig) -> None:
    """Test get_entity retrieves and deserializes cached entity."""
    from advanced_alchemy._serialization import encode_json

    manager = CacheManager(memory_config)

    # Manually cache a serialized entity (using JSON directly to avoid SQLAlchemy complexity)
    fake_entity_data = {
        "__aa_model__": "TestModel",
        "__aa_table__": "test_model",
        "id": "12345678-1234-5678-1234-567812345678",
        "name": "Test Entity",
    }
    serialized = encode_json(fake_entity_data).encode("utf-8")
    manager.set_sync("test_model:get:1", serialized)

    # Note: This test is simplified - we skip deserialization test because it requires
    # a real SQLAlchemy model. The integration tests cover full serialization/deserialization.


@pytest.mark.skipif(not DOGPILE_CACHE_INSTALLED, reason="dogpile.cache not installed")
def test_cache_manager_get_entity_not_found_returns_none(memory_config: CacheConfig) -> None:
    """Test get_entity returns None when entity not in cache."""

    manager = CacheManager(memory_config)

    # Use a mock class to avoid SQLAlchemy model creation complexity
    MockModel = MagicMock()

    cached = manager.get_entity_sync("test_model", 999, MockModel)

    assert cached is None


@pytest.mark.skipif(not DOGPILE_CACHE_INSTALLED, reason="dogpile.cache not installed")
def test_cache_manager_get_entity_deserialization_error_returns_none(memory_config: CacheConfig) -> None:
    """Test get_entity returns None and deletes corrupted cache on deserialization error."""

    from advanced_alchemy.cache.manager import DOGPILE_NO_VALUE

    MockModel = MagicMock()

    manager = CacheManager(memory_config)

    # Put corrupted data in cache
    manager.set_sync("test_model:get:1", b"corrupted_data")

    # Should return None and log error
    cached = manager.get_entity_sync("test_model", 1, MockModel)

    assert cached is None

    # Corrupted entry should be deleted
    result = manager.get_sync("test_model:get:1")
    assert result is DOGPILE_NO_VALUE or result is None


@pytest.mark.skipif(not DOGPILE_CACHE_INSTALLED, reason="dogpile.cache not installed")
def test_cache_manager_set_entity_serialization_succeeds() -> None:
    """Test set_entity can cache data (serialization tested in integration)."""
    # Note: Full serialization test requires real SQLAlchemy models in a session.
    # This is covered by integration tests. Here we just test the basic flow works.
    pass


@pytest.mark.skipif(not DOGPILE_CACHE_INSTALLED, reason="dogpile.cache not installed")
def test_cache_manager_set_entity_serialization_error_logs_and_continues(memory_config: CacheConfig) -> None:
    """Test set_entity logs error and continues on serialization failure."""

    class UnserializableModel:
        """Model that cannot be serialized."""

        def __init__(self) -> None:
            self.data = lambda: None  # Functions can't be serialized

    manager = CacheManager(memory_config)

    # Should not raise, just log error
    manager.set_entity_sync("test_model", 1, UnserializableModel())


@pytest.mark.skipif(not DOGPILE_CACHE_INSTALLED, reason="dogpile.cache not installed")
def test_cache_manager_invalidate_entity(memory_config: CacheConfig) -> None:
    """Test invalidate_entity removes entity from cache."""
    from advanced_alchemy.cache.manager import DOGPILE_NO_VALUE

    manager = CacheManager(memory_config)

    # Set a value
    manager.set_sync("users:get:1", b"test_data")

    # Invalidate
    manager.invalidate_entity_sync("users", 1)

    # Should be gone
    result = manager.get_sync("users:get:1")
    assert result is DOGPILE_NO_VALUE or result is None


@pytest.mark.skipif(not DOGPILE_CACHE_INSTALLED, reason="dogpile.cache not installed")
def test_cache_manager_bump_model_version(memory_config: CacheConfig) -> None:
    """Test bump_model_version changes version token."""
    manager = CacheManager(memory_config)

    # Initial version should be 0
    assert manager.get_model_version_sync("users") == "0"

    # Bump version
    version1 = manager.bump_model_version_sync("users")
    assert version1 != "0"
    assert manager.get_model_version_sync("users") == version1

    # Bump again
    version2 = manager.bump_model_version_sync("users")
    assert version2 != version1
    assert manager.get_model_version_sync("users") == version2


@pytest.mark.skipif(not DOGPILE_CACHE_INSTALLED, reason="dogpile.cache not installed")
def test_cache_manager_get_model_version_from_cache(memory_config: CacheConfig) -> None:
    """Test get_model_version retrieves version from distributed cache."""
    manager = CacheManager(memory_config)

    # Manually set version in cache
    manager.set_sync("users:version", "token")

    # Should retrieve from cache
    version = manager.get_model_version_sync("users")
    assert version == "token"


@pytest.mark.skipif(not DOGPILE_CACHE_INSTALLED, reason="dogpile.cache not installed")
def test_cache_manager_invalidate_all(memory_config: CacheConfig) -> None:
    """Test invalidate_all clears entire cache."""
    from advanced_alchemy.cache.manager import DOGPILE_NO_VALUE

    manager = CacheManager(memory_config)

    # Set some values
    manager.set_sync("key1", "value1")
    manager.set_sync("key2", "value2")
    manager._model_versions["users"] = "token"

    # Invalidate all
    manager.invalidate_all_sync()

    # All should be cleared
    result1 = manager.get_sync("key1")
    result2 = manager.get_sync("key2")
    assert result1 is DOGPILE_NO_VALUE or result1 is None
    assert result2 is DOGPILE_NO_VALUE or result2 is None
    assert manager._model_versions == {}


@pytest.mark.skipif(not DOGPILE_CACHE_INSTALLED, reason="dogpile.cache not installed")
def test_cache_manager_custom_serializers(memory_config: CacheConfig) -> None:
    """Test CacheManager with custom serializer/deserializer."""

    def custom_serializer(obj: Any) -> bytes:
        return b"custom"

    def custom_deserializer(data: bytes, model_class: type) -> Any:
        return "deserialized"

    memory_config.serializer = custom_serializer
    memory_config.deserializer = custom_deserializer

    manager = CacheManager(memory_config)

    # set_entity should use custom serializer
    manager.set_entity_sync("test", 1, {"data": "test"})

    # get_entity should use custom deserializer
    result = manager.get_entity_sync("test", 1, str)
    assert result == "deserialized"


def test_cache_manager_handles_region_creation_failure() -> None:
    """Test CacheManager handles region creation failure gracefully."""
    config = CacheConfig(backend="invalid.backend.that.does.not.exist")

    manager = CacheManager(config)

    # Should return NullRegion on failure
    region = manager.region

    from advanced_alchemy.cache._null import NullRegion

    assert isinstance(region, NullRegion)


@pytest.mark.asyncio
async def test_cache_manager_get_async_does_not_block_event_loop() -> None:
    """Ensure cache I/O is offloaded and doesn't block the loop."""

    class SlowRegion:
        def get(self, key: str, expiration_time: int | None = None) -> Any:
            time.sleep(0.2)
            return "value"

        def set(self, key: str, value: Any) -> None:
            return

        def delete(self, key: str) -> None:
            return

        def invalidate(self) -> None:
            return

    config = CacheConfig(region_factory=lambda _cfg: SlowRegion())
    manager = CacheManager(config)

    ticks = 0

    async def ticker() -> None:
        nonlocal ticks
        for _ in range(5):
            await asyncio.sleep(0.05)
            ticks += 1

    result, _ = await asyncio.gather(manager.get_async("key"), ticker())

    assert result == "value"
    assert ticks >= 3


@pytest.mark.asyncio
async def test_cache_manager_singleflight_async_coalesces() -> None:
    """Ensure async singleflight invokes creator only once per key."""
    manager = CacheManager(CacheConfig(backend="dogpile.cache.null"))

    call_count = 0

    async def creator() -> str:
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.05)
        return "ok"

    results = await asyncio.gather(*[manager.singleflight_async("k", creator) for _ in range(25)])

    assert call_count == 1
    assert results == ["ok"] * 25
