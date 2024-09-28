from __future__ import annotations

import pytest

from tests.integration import _repository_tests as repo_tests
from tests.integration.adapters.duckdb.conftest import SessionTestsMixin


@pytest.mark.parametrize(
    ("pk_type", "session_type"),
    [
        ("bigint", "sync"),
        ("uuid", "sync"),
    ],
    scope="class",
)
class Test_Repository(repo_tests.AbstractRepositoryTests, SessionTestsMixin):
    """DuckDB Repository Tests"""
