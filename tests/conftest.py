from typing import Generator

import pytest


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(scope="session")
def monkeysession() -> Generator[pytest.MonkeyPatch, None, None]:
    with pytest.MonkeyPatch.context() as mp:
        yield mp


pytest_plugins = [
    "tests.docker_service_fixtures",
    "tests.fixtures.bigint.raw_data",
    "tests.fixtures.uuid.raw_data",
    "pytest_databases.docker",
    "pytest_databases.docker.postgres",
    "pytest_databases.docker.mysql",
    "pytest_databases.docker.oracle",
]
