"""Litestar extension lazy re-exports for ``advanced_alchemy.operations``."""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from advanced_alchemy.operations import (
        MergeStatement,
        OnConflictUpsert,
        UpsertKind,
        UpsertStrategy,
        resolve_column_default,
        resolve_upsert_strategy,
        validate_identifier,
    )

__all__ = (
    "MergeStatement",
    "OnConflictUpsert",
    "UpsertKind",
    "UpsertStrategy",
    "resolve_column_default",
    "resolve_upsert_strategy",
    "validate_identifier",
)


def __getattr__(attr_name: str) -> object:
    """Lazily resolve exported attributes from ``advanced_alchemy.operations``."""
    if attr_name in __all__:
        module = importlib.import_module("advanced_alchemy.operations")
        value = getattr(module, attr_name)
        globals()[attr_name] = value
        return value
    msg = f"module {__name__!r} has no attribute {attr_name!r}"
    raise AttributeError(msg)


def __dir__() -> list[str]:
    """Return module attributes including lazily re-exported symbols."""
    return sorted(set(globals()).union(__all__))
