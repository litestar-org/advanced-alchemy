import asyncio
from collections.abc import Coroutine
from typing import Any, Callable

import pytest

from advanced_alchemy.utils.portals import Portal, PortalProvider


@pytest.fixture
async def async_function() -> Callable[[int], Coroutine[Any, Any, int]]:
    async def sample_async_function(x: int) -> int:
        await asyncio.sleep(0.1)
        return x * 2

    return sample_async_function


def test_portal_provider_singleton() -> None:
    provider1 = PortalProvider()
    provider2 = PortalProvider()
    assert provider1 is provider2, "PortalProvider is not a singleton"


def test_portal_provider_start_stop() -> None:
    provider = PortalProvider()
    provider.start()
    assert provider.is_running, "Provider should be running after start()"
    assert provider.is_ready, "Provider should be ready after start()"
    provider.stop()
    assert not provider.is_running, "Provider should not be running after stop()"


def test_portal_provider_call(async_function: Callable[[int], Coroutine[Any, Any, int]]) -> None:
    provider = PortalProvider()
    provider.start()
    result = provider.call(async_function, 5)
    assert result == 10, "The result of the async function should be 10"
    provider.stop()


def test_portal_provider_call_exception() -> None:
    async def faulty_async_function() -> None:
        raise ValueError("Intentional error")

    provider = PortalProvider()
    provider.start()
    with pytest.raises(ValueError, match="Intentional error"):
        provider.call(faulty_async_function)
    provider.stop()


def test_portal_call(async_function: Callable[[int], Coroutine[Any, Any, int]]) -> None:
    provider = PortalProvider()
    portal = Portal(provider)
    provider.start()
    result = portal.call(async_function, 3)
    assert result == 6, "The result of the async function should be 6"
    provider.stop()
