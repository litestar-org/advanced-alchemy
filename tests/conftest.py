import pytest


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


pytest_plugins = [
    "tests.docker_service_fixtures",
    "pytest_databases.docker",
    "pytest_databases.docker.postgres",
    "pytest_databases.docker.mysql",
    "pytest_databases.docker.oracle",
]
