import asyncio
from collections.abc import Generator

import pytest

pytest_plugins = ["tests.docker_service_fixtures"]


@pytest.fixture(scope="session")
def event_loop() -> Generator["asyncio.AbstractEventLoop", None, None]:
    loop = asyncio.get_event_loop_policy().get_event_loop()
    yield loop
    loop.close()
