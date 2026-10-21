"""Litestar extension lazy re-exports for ``advanced_alchemy.exceptions``."""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from advanced_alchemy.exceptions import (
        AdvancedAlchemyError,
        DuplicateKeyError,
        ErrorMessages,
        ForeignKeyError,
        ImproperConfigurationError,
        IntegrityError,
        MissingDependencyError,
        MultipleResultsFoundError,
        NotFoundError,
        RepositoryError,
        SerializationError,
        wrap_sqlalchemy_exception,
    )

__all__ = (
    "AdvancedAlchemyError",
    "DuplicateKeyError",
    "ErrorMessages",
    "ForeignKeyError",
    "ImproperConfigurationError",
    "IntegrityError",
    "MissingDependencyError",
    "MultipleResultsFoundError",
    "NotFoundError",
    "RepositoryError",
    "SerializationError",
    "wrap_sqlalchemy_exception",
)


def __getattr__(attr_name: str) -> object:
    """Lazily resolve exported attributes from ``advanced_alchemy.exceptions``."""
    if attr_name in __all__:
        module = importlib.import_module("advanced_alchemy.exceptions")
        value = getattr(module, attr_name)
        globals()[attr_name] = value
        return value
    msg = f"module {__name__!r} has no attribute {attr_name!r}"
    raise AttributeError(msg)


def __dir__() -> list[str]:
    """Return module attributes including lazily re-exported symbols."""
    return sorted(set(globals()).union(__all__))
