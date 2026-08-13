"""Each `provide_filters` config must produce its own dependency."""

from typing import Annotated, Any

import pytest
from fastapi import Depends, FastAPI

from advanced_alchemy.extensions.fastapi import providers

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


def test_the_same_config_is_still_cached() -> None:
    """The per-config cache is what keeps repeated identical configs cheap; it should still hit."""
    config: dict[str, Any] = {"search": "name", "pagination_type": "limit_offset"}
    assert providers.provide_filters(dict(config)) is providers.provide_filters(dict(config))
