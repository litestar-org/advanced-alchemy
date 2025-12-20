"""Unit tests for replica selectors.

Tests different strategies for selecting read replicas.
"""

from unittest.mock import MagicMock

import pytest
from sqlalchemy import Engine

from advanced_alchemy.routing.selectors import RandomSelector, RoundRobinSelector


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

    assert selector.next() is mock_engines[0]
    assert selector.next() is mock_engines[1]
    assert selector.next() is mock_engines[2]

    assert selector.next() is mock_engines[0]
    assert selector.next() is mock_engines[1]
    assert selector.next() is mock_engines[2]


def test_round_robin_selector_single_replica() -> None:
    """Test RoundRobinSelector with a single replica."""
    engine = MagicMock(name="single_engine")
    selector = RoundRobinSelector([engine])

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
        results.extend([selector.next() for _ in range(10)])

    threads = [threading.Thread(target=worker) for _ in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

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

    selections = [selector.next() for _ in range(100)]

    assert all(engine in mock_engines for engine in selections)


def test_random_selector_distributes_randomly(mock_engines: list[Engine]) -> None:
    """Test that RandomSelector distributes selections across replicas."""
    selector = RandomSelector(mock_engines)

    selections = [selector.next() for _ in range(1000)]

    counts = {engine: selections.count(engine) for engine in mock_engines}

    assert all(count > 0 for count in counts.values())

    for count in counts.values():
        assert 200 < count < 450, f"Distribution not random enough: {counts}"


def test_random_selector_single_replica() -> None:
    """Test RandomSelector with a single replica."""
    engine = MagicMock(name="single_engine")
    selector = RandomSelector([engine])

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
