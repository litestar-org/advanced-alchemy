"""Litestar extension lazy re-exports for ``advanced_alchemy.repository``."""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from advanced_alchemy.repository import (
        DEFAULT_ERROR_MESSAGE_TEMPLATES,
        Empty,
        EmptyType,
        ErrorMessages,
        FilterableRepository,
        FilterableRepositoryProtocol,
        LoadSpec,
        ModelOrRowMappingT,
        ModelT,
        OrderingPair,
        SQLAlchemyAsyncQueryRepository,
        SQLAlchemyAsyncRepository,
        SQLAlchemyAsyncRepositoryProtocol,
        SQLAlchemyAsyncSlugRepository,
        SQLAlchemyAsyncSlugRepositoryProtocol,
        SQLAlchemySyncQueryRepository,
        SQLAlchemySyncRepository,
        SQLAlchemySyncRepositoryProtocol,
        SQLAlchemySyncSlugRepository,
        SQLAlchemySyncSlugRepositoryProtocol,
        get_instrumented_attr,
        model_from_dict,
    )

__all__ = (
    "DEFAULT_ERROR_MESSAGE_TEMPLATES",
    "Empty",
    "EmptyType",
    "ErrorMessages",
    "FilterableRepository",
    "FilterableRepositoryProtocol",
    "LoadSpec",
    "ModelOrRowMappingT",
    "ModelT",
    "OrderingPair",
    "SQLAlchemyAsyncQueryRepository",
    "SQLAlchemyAsyncRepository",
    "SQLAlchemyAsyncRepositoryProtocol",
    "SQLAlchemyAsyncSlugRepository",
    "SQLAlchemyAsyncSlugRepositoryProtocol",
    "SQLAlchemySyncQueryRepository",
    "SQLAlchemySyncRepository",
    "SQLAlchemySyncRepositoryProtocol",
    "SQLAlchemySyncSlugRepository",
    "SQLAlchemySyncSlugRepositoryProtocol",
    "get_instrumented_attr",
    "model_from_dict",
)


def __getattr__(attr_name: str) -> object:
    """Lazily resolve exported attributes from ``advanced_alchemy.repository``."""
    if attr_name in __all__:
        module = importlib.import_module("advanced_alchemy.repository")
        value = getattr(module, attr_name)
        globals()[attr_name] = value
        return value
    msg = f"module {__name__!r} has no attribute {attr_name!r}"
    raise AttributeError(msg)


def __dir__() -> list[str]:
    """Return module attributes including lazily re-exported symbols."""
    return sorted(set(globals()).union(__all__))
