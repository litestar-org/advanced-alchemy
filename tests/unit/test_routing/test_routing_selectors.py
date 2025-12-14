"""Unit tests for replica selectors.

Tests different strategies for selecting read replicas.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from advanced_alchemy.routing.selectors import RandomSelector, RoundRobinSelector

if TYPE_CHECKING:
    from sqlalchemy import Engine


@pytest.fixture
def mock_engines() -> list[Engine]:
    """Create mock engines for testing."""
    return [MagicMock(name=f"engine_{i}") for i in range(3)]


def test_round_robin_selector_initialization(mock_engines: list[Engine]) -> None:
    """Test RoundRobinSelector initialization."""
    selector = RoundRobinSelector(mock_engines)

    assert selector.has_replicas() is True
    assert len(selector.replicas) == 3


def test_round_robin_selector_empty_initialization() -> None:
    """Test RoundRobinSelector initialization with no replicas."""
    selector: RoundRobinSelector[Engine] = RoundRobinSelector([])

    assert selector.has_replicas() is False
    assert len(selector.replicas) == 0


def test_round_robin_selector_cycles_through_replicas(mock_engines: list[Engine]) -> None:
    """Test that RoundRobinSelector cycles through replicas in order."""
    selector = RoundRobinSelector(mock_engines)

    # First cycle
    assert selector.next() is mock_engines[0]
    assert selector.next() is mock_engines[1]
    assert selector.next() is mock_engines[2]

    # Second cycle - should start over
    assert selector.next() is mock_engines[0]
    assert selector.next() is mock_engines[1]
    assert selector.next() is mock_engines[2]


def test_round_robin_selector_single_replica() -> None:
    """Test RoundRobinSelector with a single replica."""
    engine = MagicMock(name="single_engine")
    selector = RoundRobinSelector([engine])

    # Should always return the same engine
    assert selector.next() is engine
    assert selector.next() is engine
    assert selector.next() is engine


def test_round_robin_selector_no_replicas_raises() -> None:
    """Test that RoundRobinSelector raises RuntimeError when no replicas configured."""
    selector: RoundRobinSelector[Engine] = RoundRobinSelector([])

    with pytest.raises(RuntimeError, match="No replicas configured for round-robin selection"):
        selector.next()


def test_round_robin_selector_thread_safe(mock_engines: list[Engine]) -> None:
    """Test that RoundRobinSelector is thread-safe (uses lock)."""
    import threading

    selector = RoundRobinSelector(mock_engines)
    results: list[Engine] = []

    def worker() -> None:
        for _ in range(10):
            results.append(selector.next())  # noqa: PERF401

    threads = [threading.Thread(target=worker) for _ in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    # All 50 results should be valid engines
    assert len(results) == 50
    assert all(engine in mock_engines for engine in results)


def test_random_selector_initialization(mock_engines: list[Engine]) -> None:
    """Test RandomSelector initialization."""
    selector = RandomSelector(mock_engines)

    assert selector.has_replicas() is True
    assert len(selector.replicas) == 3


def test_random_selector_empty_initialization() -> None:
    """Test RandomSelector initialization with no replicas."""
    selector: RandomSelector[Engine] = RandomSelector([])

    assert selector.has_replicas() is False
    assert len(selector.replicas) == 0


def test_random_selector_returns_valid_replica(mock_engines: list[Engine]) -> None:
    """Test that RandomSelector returns valid replicas."""
    selector = RandomSelector(mock_engines)

    # Get 100 selections and verify all are valid
    selections = [selector.next() for _ in range(100)]

    assert all(engine in mock_engines for engine in selections)


def test_random_selector_distributes_randomly(mock_engines: list[Engine]) -> None:
    """Test that RandomSelector distributes selections across replicas."""
    selector = RandomSelector(mock_engines)

    # Get many selections
    selections = [selector.next() for _ in range(1000)]

    # Count selections per engine
    counts = {engine: selections.count(engine) for engine in mock_engines}

    # All engines should be selected at least once
    assert all(count > 0 for count in counts.values())

    # Distribution should be roughly even (with some randomness tolerance)
    # Each engine should get roughly 333 selections (1000 / 3)
    # Allow +/- 100 for randomness
    for count in counts.values():
        assert 200 < count < 450, f"Distribution not random enough: {counts}"


def test_random_selector_single_replica() -> None:
    """Test RandomSelector with a single replica."""
    engine = MagicMock(name="single_engine")
    selector = RandomSelector([engine])

    # Should always return the same engine
    assert selector.next() is engine
    assert selector.next() is engine
    assert selector.next() is engine


def test_random_selector_no_replicas_raises() -> None:
    """Test that RandomSelector raises RuntimeError when no replicas configured."""
    selector: RandomSelector[Engine] = RandomSelector([])

    with pytest.raises(RuntimeError, match="No replicas configured for random selection"):
        selector.next()


def test_replica_selector_replicas_property(mock_engines: list[Engine]) -> None:
    """Test that replica selector exposes replicas property."""
    selector = RoundRobinSelector(mock_engines)

    assert selector.replicas == mock_engines


def test_has_replicas_returns_false_for_empty_list() -> None:
    """Test has_replicas returns False for empty replica list."""
    selector: RoundRobinSelector[Engine] = RoundRobinSelector([])

    assert selector.has_replicas() is False


def test_has_replicas_returns_true_for_non_empty_list(mock_engines: list[Engine]) -> None:
    """Test has_replicas returns True for non-empty replica list."""
    selector = RoundRobinSelector(mock_engines)

    assert selector.has_replicas() is True
