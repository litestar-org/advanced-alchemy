"""Litestar extension lazy re-exports for ``advanced_alchemy.mixins``."""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from advanced_alchemy.mixins import (
        AuditColumns,
        BigIntPrimaryKey,
        IdentityPrimaryKey,
        NanoIDPrimaryKey,
        SentinelMixin,
        SlugKey,
        UniqueMixin,
        UUIDPrimaryKey,
        UUIDv6PrimaryKey,
        UUIDv7PrimaryKey,
    )

__all__ = (
    "AuditColumns",
    "BigIntPrimaryKey",
    "IdentityPrimaryKey",
    "NanoIDPrimaryKey",
    "SentinelMixin",
    "SlugKey",
    "UUIDPrimaryKey",
    "UUIDv6PrimaryKey",
    "UUIDv7PrimaryKey",
    "UniqueMixin",
)


def __getattr__(attr_name: str) -> object:
    """Lazily resolve exported attributes from ``advanced_alchemy.mixins``."""
    if attr_name in __all__:
        module = importlib.import_module("advanced_alchemy.mixins")
        value = getattr(module, attr_name)
        globals()[attr_name] = value
        return value
    msg = f"module {__name__!r} has no attribute {attr_name!r}"
    raise AttributeError(msg)


def __dir__() -> list[str]:
    """Return module attributes including lazily re-exported symbols."""
    return sorted(set(globals()).union(__all__))
