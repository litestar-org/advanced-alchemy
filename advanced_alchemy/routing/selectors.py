"""Replica selectors for read/write routing.

This module provides different strategies for selecting which read replica
to use for read operations.
"""

import secrets
import threading
from abc import ABC, abstractmethod
from itertools import cycle
from typing import TYPE_CHECKING, Generic, TypeVar, Union

if TYPE_CHECKING:
    from collections.abc import Iterator

    from sqlalchemy import Engine
    from sqlalchemy.ext.asyncio import AsyncEngine


__all__ = (
    "RandomSelector",
    "ReplicaSelector",
    "RoundRobinSelector",
)


EngineT = TypeVar("EngineT", bound="Union[Engine, AsyncEngine]")


class EngineSelector(ABC, Generic[EngineT]):
    """Abstract base class for engine selection strategies.

    Subclasses implement different algorithms for choosing which
    engine to use for operations.

    Attributes:
        _engines: List of engines to select from.
    """

    __slots__ = ("_engines",)

    def __init__(self, engines: list[EngineT]) -> None:
        """Initialize the selector with a list of engines.

        Args:
            engines: List of database engines.
        """
        self._engines = engines

    def has_engines(self) -> bool:
        """Check if any engines are configured.

        Returns:
            ``True`` if at least one engine is available.
        """
        return len(self._engines) > 0

    def has_replicas(self) -> bool:
        """Check if any replicas are configured (alias for has_engines).

        Returns:
            ``True`` if at least one engine is available.
        """
        return self.has_engines()

    @property
    def engines(self) -> list[EngineT]:
        """Get the list of engines.

        Returns:
            List of configured engines.
        """
        return self._engines

    @property
    def replicas(self) -> list[EngineT]:
        """Get the list of replica engines (alias for engines).

        Returns:
            List of configured engines.
        """
        return self.engines

    @abstractmethod
    def next(self) -> EngineT:
        """Select the next engine to use.

        Returns:
            The selected engine.

        Raises:
            RuntimeError: If no engines are available.
        """
        ...


# Alias for backward compatibility
ReplicaSelector = EngineSelector


class RoundRobinSelector(EngineSelector[EngineT]):
    """Round-robin engine selection.

    Cycles through engines in order, distributing load evenly
    across all available engines.

    This selector is thread-safe.

    Example:
        Creating a round-robin selector::

            selector = RoundRobinSelector(engines)
            engine1 = selector.next()
            engine2 = selector.next()
            engine3 = selector.next()

        This cycles through engines in order and wraps back to the first.
    """

    __slots__ = ("_cycle", "_lock")

    def __init__(self, engines: list[EngineT]) -> None:
        """Initialize the round-robin selector.

        Args:
            engines: List of database engines.
        """
        super().__init__(engines)
        self._cycle: Iterator[EngineT] = cycle(engines) if engines else iter([])
        self._lock = threading.Lock()

    def next(self) -> EngineT:
        """Select the next engine in round-robin order.

        Returns:
            The next engine in the cycle.

        Raises:
            RuntimeError: If no engines are configured.
        """
        if not self._engines:
            msg = "No engines configured for round-robin selection"
            raise RuntimeError(msg)
        with self._lock:
            return next(self._cycle)


class RandomSelector(EngineSelector[EngineT]):
    """Random engine selection.

    Selects engines randomly, which can help with load distribution
    when engines have varying capacity or when you want to avoid
    predictable patterns.

    Example:
        Creating a random selector::

            selector = RandomSelector(engines)
            engine = selector.next()
    """

    __slots__ = ()

    def next(self) -> EngineT:
        """Select a random engine.

        Returns:
            A randomly selected engine.

        Raises:
            RuntimeError: If no engines are configured.
        """
        if not self._engines:
            msg = "No engines configured for random selection"
            raise RuntimeError(msg)
        return secrets.choice(self._engines)
