"""Pytest configuration for routing unit tests.

The routing subsystem uses ``ContextVar`` state to implement session-level read/write routing.
That state is process-local, so it can leak between tests when running without xdist or when
xdist schedules related tests onto the same worker.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from advanced_alchemy.routing.context import reset_routing_context


@pytest.fixture(autouse=True)
def _reset_routing_context() -> Iterator[None]:
    """Ensure routing ContextVar state never leaks between tests."""
    reset_routing_context()
    try:
        yield
    finally:
        reset_routing_context()

