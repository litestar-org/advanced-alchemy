"""Unit tests for NullRegion implementation."""

from __future__ import annotations

from advanced_alchemy.cache._null import NO_VALUE, NullRegion


def test_null_region_get_always_returns_no_value() -> None:
    """Test NullRegion.get() always returns NO_VALUE."""
    region = NullRegion()

    result = region.get("any_key")

    assert result is NO_VALUE


def test_null_region_get_or_create_always_calls_creator() -> None:
    """Test NullRegion.get_or_create() always calls creator function."""
    region = NullRegion()
    call_count = 0

    def creator() -> str:
        nonlocal call_count
        call_count += 1
        return "created"

    # First call
    result1 = region.get_or_create("key", creator)
    assert result1 == "created"
    assert call_count == 1

    # Second call - should call creator again (no caching)
    result2 = region.get_or_create("key", creator)
    assert result2 == "created"
    assert call_count == 2


def test_null_region_set_is_noop() -> None:
    """Test NullRegion.set() does nothing."""
    region = NullRegion()

    # Should not raise any errors
    region.set("key", "value")

    # Verify value is not stored
    assert region.get("key") is NO_VALUE


def test_null_region_delete_is_noop() -> None:
    """Test NullRegion.delete() does nothing."""
    region = NullRegion()

    # Should not raise any errors
    region.delete("key")


def test_null_region_invalidate_is_noop() -> None:
    """Test NullRegion.invalidate() does nothing."""
    region = NullRegion()

    # Should not raise any errors
    region.invalidate()


def test_null_region_configure_returns_self() -> None:
    """Test NullRegion.configure() returns self for method chaining."""
    region = NullRegion()

    result = region.configure(
        backend="dogpile.cache.memory",
        expiration_time=300,
        arguments={"test": "value"},
    )

    assert result is region


def test_no_value_sentinel_repr() -> None:
    """Test NO_VALUE has meaningful repr."""
    assert repr(NO_VALUE) == "<NO_VALUE>"


def test_null_region_get_with_expiration() -> None:
    """Test NullRegion.get() ignores expiration_time parameter."""
    region = NullRegion()

    result = region.get("key", expiration_time=100)

    assert result is NO_VALUE


def test_null_region_get_or_create_with_expiration() -> None:
    """Test NullRegion.get_or_create() ignores expiration_time parameter."""
    region = NullRegion()

    result = region.get_or_create("key", lambda: "value", expiration_time=100)

    assert result == "value"
