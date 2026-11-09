"""Litestar extension lazy re-exports for ``advanced_alchemy.utils``."""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from advanced_alchemy.utils import (
        cli_tools,
        dataclass,
        dependencies,
        deprecation,
        fixtures,
        module_loader,
        portals,
        serialization,
        singleton,
        sync_tools,
        text,
    )

__all__ = (
    "cli_tools",
    "dataclass",
    "dependencies",
    "deprecation",
    "fixtures",
    "module_loader",
    "portals",
    "serialization",
    "singleton",
    "sync_tools",
    "text",
)


def __getattr__(attr_name: str) -> object:
    """Lazily resolve exported submodules from ``advanced_alchemy.utils``."""
    if attr_name in __all__:
        value = importlib.import_module(f"advanced_alchemy.utils.{attr_name}")
        globals()[attr_name] = value
        return value
    msg = f"module {__name__!r} has no attribute {attr_name!r}"
    raise AttributeError(msg)


def __dir__() -> list[str]:
    """Return module attributes including lazily re-exported submodules."""
    return sorted(set(globals()).union(__all__))
