"""`FilterConfig["alias_generator"]` controls the generated query parameter names."""

from typing import Annotated, Any

import pytest
from fastapi import Depends, FastAPI

from advanced_alchemy.extensions.fastapi import providers

pytestmark = pytest.mark.unit

CONFIG: dict[str, Any] = {
    "pagination_type": "limit_offset",
    "search": "name",
    "sort_field": "created_at",
    "created_at": True,
    "boolean_fields": ["is_active"],
    "in_fields": ["status"],
}


def _parameter_names(config: dict[str, Any]) -> list[str]:
    app = FastAPI()
    dependency = providers.provide_filters(config)

    @app.get("/things")
    async def list_things(filters: Annotated[list[Any], Depends(dependency)]) -> list[Any]:
        return filters

    return [parameter["name"] for parameter in app.openapi()["paths"]["/things"]["get"]["parameters"]]


def test_default_names_are_unchanged() -> None:
    """The default generator is `camelize`, which reproduces the previously hardcoded names."""
    assert _parameter_names(dict(CONFIG)) == [
        "createdBefore",
        "createdAfter",
        "currentPage",
        "pageSize",
        "searchString",
        "searchIgnoreCase",
        "orderBy",
        "sortOrder",
        "statusIn",
        "isActive",
    ]


def test_alias_generator_renames_every_parameter() -> None:
    """Including the per-field filters, which were camelized from the model's own field names."""
    assert _parameter_names({**CONFIG, "alias_generator": lambda name: name}) == [
        "created_before",
        "created_after",
        "current_page",
        "page_size",
        "search_string",
        "search_ignore_case",
        "order_by",
        "sort_order",
        "status_in",
        "is_active",
    ]


def test_distinct_generators_get_distinct_dependencies() -> None:
    """Two generators must not collide in the dependency cache.

    A function hashes by identity, and CPython reuses the address of a collected object — so a key
    that does not keep the generator alive can hand the second config the first one's providers.
    """
    snake = _parameter_names({**CONFIG, "alias_generator": lambda name: name})
    upper = _parameter_names({**CONFIG, "alias_generator": lambda name: name.upper()})

    assert snake[0] == "created_before"
    assert upper[0] == "CREATED_BEFORE"
    assert _parameter_names(dict(CONFIG))[0] == "createdBefore", "the default config must be unaffected"
