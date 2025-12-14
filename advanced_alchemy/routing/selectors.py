"""Replica selectors for read/write routing.

This module provides different strategies for selecting which read replica
to use for read operations.
"""

from __future__ import annotations

import random
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


class ReplicaSelector(ABC, Generic[EngineT]):
    """Abstract base class for replica selection strategies.

    Subclasses implement different algorithms for choosing which
    replica to use for read operations.

    Attributes:
        _replicas: List of replica engines to select from.
    """

    __slots__ = ("_replicas",)

    def __init__(self, replicas: list[EngineT]) -> None:
        """Initialize the selector with a list of replica engines.

        Args:
            replicas: List of replica database engines.
        """
        self._replicas = replicas

    def has_replicas(self) -> bool:
        """Check if any replicas are configured.

        Returns:
            ``True`` if at least one replica is available.
        """
        return len(self._replicas) > 0

    @property
    def replicas(self) -> list[EngineT]:
        """Get the list of replica engines.

        Returns:
            List of configured replica engines.
        """
        return self._replicas

    @abstractmethod
    def next(self) -> EngineT:
        """Select the next replica engine to use.

        Returns:
            The selected replica engine.

        Raises:
            RuntimeError: If no replicas are available.
        """
        ...


class RoundRobinSelector(ReplicaSelector[EngineT]):
    """Round-robin replica selection.

    Cycles through replicas in order, distributing load evenly
    across all available replicas.

    This selector is thread-safe.

    Example:
        Creating a round-robin selector::

            selector = RoundRobinSelector(replica_engines)
            engine1 = selector.next()  # Returns first replica
            engine2 = selector.next()  # Returns second replica
            engine3 = (
                selector.next()
            )  # Returns first replica again (if only 2 replicas)
    """

    __slots__ = ("_cycle", "_lock")

    def __init__(self, replicas: list[EngineT]) -> None:
        """Initialize the round-robin selector.

        Args:
            replicas: List of replica database engines.
        """
        super().__init__(replicas)
        self._cycle: Iterator[EngineT] = cycle(replicas) if replicas else iter([])
        self._lock = threading.Lock()

    def next(self) -> EngineT:
        """Select the next replica in round-robin order.

        Returns:
            The next replica engine in the cycle.

        Raises:
            RuntimeError: If no replicas are configured.
        """
        if not self._replicas:
            msg = "No replicas configured for round-robin selection"
            raise RuntimeError(msg)
        with self._lock:
            return next(self._cycle)


class RandomSelector(ReplicaSelector[EngineT]):
    """Random replica selection.

    Selects replicas randomly, which can help with load distribution
    when replicas have varying capacity or when you want to avoid
    predictable patterns.

    Example:
        Creating a random selector::

            selector = RandomSelector(replica_engines)
            engine = selector.next()  # Returns a random replica
    """

    __slots__ = ()

    def next(self) -> EngineT:
        """Select a random replica.

        Returns:
            A randomly selected replica engine.

        Raises:
            RuntimeError: If no replicas are configured.
        """
        if not self._replicas:
            msg = "No replicas configured for random selection"
            raise RuntimeError(msg)
        return random.choice(self._replicas)  # noqa: S311
