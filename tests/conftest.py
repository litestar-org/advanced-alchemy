from __future__ import annotations

from typing import Any

import pytest
from pytest_asyncio import is_async_test

from tests.helpers import _resolve_lazy_fixture

pytest_plugins = [
    "pytest_databases.docker",
    "pytest_databases.docker.oracle",
    "pytest_databases.docker.postgres",
    "pytest_databases.docker.spanner",
    "pytest_databases.docker.cockroachdb",
    "pytest_databases.docker.mysql",
    "pytest_databases.docker.mssql",
]


def pytest_collection_modifyitems(items: Any) -> None:
    pytest_asyncio_tests = (item for item in items if is_async_test(item))
    session_scope_marker = pytest.mark.asyncio(scope="session")
    for async_test in pytest_asyncio_tests:
        async_test.add_marker(session_scope_marker, append=False)


@pytest.hookimpl(tryfirst=True)
def pytest_fixture_setup(
    fixturedef: pytest.FixtureDef,
    request: pytest.FixtureRequest,
) -> object | None:
    """Lazy fixture setup hook.

    This hook will never take over a fixture setup but just simply will
    try to resolve recursively any lazy fixture found in request.param.

    Reference:
    - https://bit.ly/3SyvsXJ

    Args:
        fixturedef (pytest.FixtureDef): fixture definition object.
        request (pytest.FixtureRequest): fixture request object.

    Returns:
        object | None: fixture value or None otherwise.
    """
    if hasattr(request, "param") and request.param:
        request.param = _resolve_lazy_fixture(request.param, request)
    return None
