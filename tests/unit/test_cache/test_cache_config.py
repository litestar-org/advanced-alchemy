"""Unit tests for CacheConfig dataclass."""

from __future__ import annotations

from advanced_alchemy.cache.config import CacheConfig


def test_cache_config_defaults() -> None:
    """Test CacheConfig has sensible defaults."""
    config = CacheConfig()

    assert config.backend == "dogpile.cache.null"
    assert config.expiration_time == 3600
    assert config.arguments == {}
    assert config.key_prefix == "aa:"
    assert config.enabled is True
    assert config.serializer is None
    assert config.deserializer is None
    assert config.region_factory is None


def test_cache_config_custom_backend() -> None:
    """Test CacheConfig with custom backend."""
    config = CacheConfig(
        backend="dogpile.cache.memory",
        expiration_time=300,
    )

    assert config.backend == "dogpile.cache.memory"
    assert config.expiration_time == 300


def test_cache_config_redis_arguments() -> None:
    """Test CacheConfig with Redis-specific arguments."""
    config = CacheConfig(
        backend="dogpile.cache.redis",
        expiration_time=600,
        arguments={
            "host": "localhost",
            "port": 6379,
            "db": 0,
        },
    )

    assert config.backend == "dogpile.cache.redis"
    assert config.arguments["host"] == "localhost"
    assert config.arguments["port"] == 6379
    assert config.arguments["db"] == 0


def test_cache_config_disabled() -> None:
    """Test CacheConfig can be disabled."""
    config = CacheConfig(enabled=False)

    assert config.enabled is False


def test_cache_config_custom_key_prefix() -> None:
    """Test CacheConfig with custom key prefix."""
    config = CacheConfig(key_prefix="myapp:")

    assert config.key_prefix == "myapp:"


def test_cache_config_custom_serializers() -> None:
    """Test CacheConfig with custom serializer/deserializer."""

    def custom_serializer(obj: object) -> bytes:
        return b"serialized"

    def custom_deserializer(data: bytes, model_class: type) -> object:
        return model_class()

    config = CacheConfig(
        serializer=custom_serializer,
        deserializer=custom_deserializer,
    )

    assert config.serializer is custom_serializer
    assert config.deserializer is custom_deserializer


def test_cache_config_no_expiration() -> None:
    """Test CacheConfig with no expiration (set to -1)."""
    config = CacheConfig(expiration_time=-1)

    assert config.expiration_time == -1
