"""Each `provide_filters` config must produce its own dependency."""

from typing import Annotated, Any

import pytest
from fastapi import Depends, FastAPI

from advanced_alchemy.extensions.fastapi import providers
from advanced_alchemy.extensions.fastapi.providers import DEPENDENCY_DEFAULTS, DependencyDefaults, FilterConfig

pytestmark = pytest.mark.unit


def _query_parameter_names(app: FastAPI, path: str) -> list[str]:
    return [parameter["name"] for parameter in app.openapi()["paths"][path]["get"].get("parameters", [])]


def test_two_configs_do_not_share_one_signature() -> None:
    """Building a second dependency must not rewrite the first one's parameters.

    The aggregate function used to be a single module-level object whose `__signature__` was
    reassigned per config, so the last config built won and every earlier router silently served
    the wrong query parameters.
    """
    app = FastAPI()
    authors = providers.provide_filters({"search": "name"})
    books = providers.provide_filters({"created_at": True})

    @app.get("/authors")
    async def list_authors(filters: Annotated[list[Any], Depends(authors)]) -> list[Any]:
        return filters

    @app.get("/books")
    async def list_books(filters: Annotated[list[Any], Depends(books)]) -> list[Any]:
        return filters

    assert authors is not books
    assert _query_parameter_names(app, "/authors") == ["searchString", "searchIgnoreCase"]
    assert _query_parameter_names(app, "/books") == ["createdBefore", "createdAfter"]


def _cached_config() -> FilterConfig:
    """A fresh, equal config each call, so the cache is exercised by value rather than by identity."""
    return {"search": "name", "pagination_type": "limit_offset"}


def test_the_same_config_is_still_cached() -> None:
    """The per-config cache is what keeps repeated identical configs cheap; it should still hit."""
    assert providers.provide_filters(_cached_config()) is providers.provide_filters(_cached_config())


class _BigPages(DependencyDefaults):
    DEFAULT_PAGINATION_SIZE = 100


def _page_size(dependency: Any, path: str) -> Any:
    app = FastAPI()

    @app.get(path)
    async def endpoint(filters: Annotated[list[Any], Depends(dependency)]) -> list[Any]:
        return filters

    parameters = app.openapi()["paths"][path]["get"]["parameters"]
    return next(p["schema"]["default"] for p in parameters if p["name"] == "pageSize")


def test_one_config_with_two_dependency_defaults_does_not_share_a_dependency() -> None:
    """`dep_defaults` shapes the signature too, so it has to take part in the cache key.

    Keyed on the config alone, whichever defaults were built first won for the whole process, and
    the other caller silently served a page size it never asked for.
    """
    config: FilterConfig = {"pagination_type": "limit_offset"}

    default = providers.provide_filters(dict(config))  # type: ignore[arg-type]
    big = providers.provide_filters(dict(config), _BigPages())  # type: ignore[arg-type]

    assert default is not big
    assert _page_size(default, "/default") == DEPENDENCY_DEFAULTS.DEFAULT_PAGINATION_SIZE
    assert _page_size(big, "/big") == _BigPages.DEFAULT_PAGINATION_SIZE


def test_equal_dependency_defaults_still_share_a_dependency() -> None:
    """Keying on the values rather than the instance is what keeps the cache useful here."""
    assert providers.provide_filters(_cached_config(), DependencyDefaults()) is providers.provide_filters(
        _cached_config(), DependencyDefaults()
    )
