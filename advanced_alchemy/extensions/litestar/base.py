"""Litestar extension lazy re-exports for ``advanced_alchemy.base``."""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from advanced_alchemy.base import (
        AdvancedDeclarativeBase,
        BasicAttributes,
        BigIntAuditBase,
        BigIntBase,
        BigIntBaseT,
        CommonTableAttributes,
        DefaultBase,
        IdentityAuditBase,
        IdentityBase,
        IdentityBaseT,
        ModelProtocol,
        NanoIDAuditBase,
        NanoIDBase,
        NanoIDBaseT,
        SQLQuery,
        TableArgsType,  # pyright: ignore[reportPrivateUsage]
        UUIDAuditBase,
        UUIDBase,
        UUIDBaseT,
        UUIDv6AuditBase,
        UUIDv6Base,
        UUIDv6BaseT,
        UUIDv7AuditBase,
        UUIDv7Base,
        UUIDv7BaseT,
        convention,
        create_registry,
        merge_table_arguments,
        metadata_registry,
        model_to_dict,
        orm_registry,
        table_name_regexp,
    )

__all__ = (
    "AdvancedDeclarativeBase",
    "BasicAttributes",
    "BigIntAuditBase",
    "BigIntBase",
    "BigIntBaseT",
    "CommonTableAttributes",
    "DefaultBase",
    "IdentityAuditBase",
    "IdentityBase",
    "IdentityBaseT",
    "ModelProtocol",
    "NanoIDAuditBase",
    "NanoIDBase",
    "NanoIDBaseT",
    "SQLQuery",
    "TableArgsType",
    "UUIDAuditBase",
    "UUIDBase",
    "UUIDBaseT",
    "UUIDv6AuditBase",
    "UUIDv6Base",
    "UUIDv6BaseT",
    "UUIDv7AuditBase",
    "UUIDv7Base",
    "UUIDv7BaseT",
    "convention",
    "create_registry",
    "merge_table_arguments",
    "metadata_registry",
    "model_to_dict",
    "orm_registry",
    "table_name_regexp",
)


def __getattr__(attr_name: str) -> object:
    """Lazily resolve exported attributes from ``advanced_alchemy.base``."""
    if attr_name in __all__:
        module = importlib.import_module("advanced_alchemy.base")
        value = getattr(module, attr_name)
        globals()[attr_name] = value
        return value
    msg = f"module {__name__!r} has no attribute {attr_name!r}"
    raise AttributeError(msg)


def __dir__() -> list[str]:
    """Return module attributes including lazily re-exported symbols."""
    return sorted(set(globals()).union(__all__))
