"""`create_filter_dependencies` must key its cache on `dep_defaults` as well as the config."""

from __future__ import annotations

import inspect
from typing import Any, cast

import pytest

from advanced_alchemy.extensions.litestar.providers import (
    DEPENDENCY_DEFAULTS,
    DependencyDefaults,
    FilterConfig,
    create_filter_dependencies,
)

pytestmark = pytest.mark.unit


class _BigPages(DependencyDefaults):
    DEFAULT_PAGINATION_SIZE = 100


def _page_size(dependencies: dict[str, Any], dep_defaults: DependencyDefaults) -> Any:
    provider = dependencies[dep_defaults.LIMIT_OFFSET_FILTER_DEPENDENCY_KEY].dependency
    return inspect.signature(provider).parameters["page_size"].default


def _pagination_config() -> FilterConfig:
    return cast("FilterConfig", {"pagination_type": "limit_offset"})


def test_one_config_with_two_dependency_defaults_does_not_share_a_cache_entry() -> None:
    """`dep_defaults` shapes the generated dependencies, so it has to take part in the cache key.

    Keyed on the config alone, whichever defaults were built first won for the whole process, and
    the other caller silently served a page size it never asked for.
    """
    default = create_filter_dependencies(_pagination_config())
    big = create_filter_dependencies(_pagination_config(), _BigPages())

    assert default is not big
    assert _page_size(default, DEPENDENCY_DEFAULTS) == DEPENDENCY_DEFAULTS.DEFAULT_PAGINATION_SIZE
    assert _page_size(big, _BigPages()) == _BigPages.DEFAULT_PAGINATION_SIZE


def test_equal_dependency_defaults_still_share_a_cache_entry() -> None:
    """Keying on the values rather than the instance is what keeps the cache useful here."""
    assert create_filter_dependencies(_pagination_config(), DependencyDefaults()) is create_filter_dependencies(
        _pagination_config(), DependencyDefaults()
    )


def test_renamed_dependency_keys_get_their_own_entry() -> None:
    """The defaults also name the dependencies, so a rename must not reuse the previous set."""

    class _Renamed(DependencyDefaults):
        LIMIT_OFFSET_FILTER_DEPENDENCY_KEY = "page_filter"

    renamed = create_filter_dependencies(_pagination_config(), _Renamed())

    assert "page_filter" in renamed
    assert DEPENDENCY_DEFAULTS.LIMIT_OFFSET_FILTER_DEPENDENCY_KEY not in renamed
