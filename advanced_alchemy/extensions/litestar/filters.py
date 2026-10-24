"""Litestar extension lazy re-exports for ``advanced_alchemy.filters``."""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from advanced_alchemy.filters import (
        LIKE_ESCAPE_CHAR,
        BeforeAfter,
        BooleanFilter,
        ChoicesFilter,
        CollectionFilter,
        ComparisonFilter,
        ExistsFilter,
        FilterGroup,
        FilterMap,
        FilterTypes,
        InAnyFilter,
        LimitOffset,
        LogicalOperatorMap,
        MultiFilter,
        NotExistsFilter,
        NotInCollectionFilter,
        NotInSearchFilter,
        NotNullFilter,
        NullFilter,
        OnBeforeAfter,
        OrderBy,
        PaginationFilter,
        SearchFilter,
        StatementFilter,
        StatementFilterT,
        StatementTypeT,
        escape_like_value,
    )

__all__ = (
    "LIKE_ESCAPE_CHAR",
    "BeforeAfter",
    "BooleanFilter",
    "ChoicesFilter",
    "CollectionFilter",
    "ComparisonFilter",
    "ExistsFilter",
    "FilterGroup",
    "FilterMap",
    "FilterTypes",
    "InAnyFilter",
    "LimitOffset",
    "LogicalOperatorMap",
    "MultiFilter",
    "NotExistsFilter",
    "NotInCollectionFilter",
    "NotInSearchFilter",
    "NotNullFilter",
    "NullFilter",
    "OnBeforeAfter",
    "OrderBy",
    "PaginationFilter",
    "SearchFilter",
    "StatementFilter",
    "StatementFilterT",
    "StatementTypeT",
    "escape_like_value",
)


def __getattr__(attr_name: str) -> object:
    """Lazily resolve exported attributes from ``advanced_alchemy.filters``."""
    if attr_name in __all__:
        module = importlib.import_module("advanced_alchemy.filters")
        value = getattr(module, attr_name)
        globals()[attr_name] = value
        return value
    msg = f"module {__name__!r} has no attribute {attr_name!r}"
    raise AttributeError(msg)


def __dir__() -> list[str]:
    """Return module attributes including lazily re-exported symbols."""
    return sorted(set(globals()).union(__all__))
