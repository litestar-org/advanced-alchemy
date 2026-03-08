# ruff: noqa: RUF100
"""Foundational type shims for optional dependencies.

Provides stub types used across the package when optional libraries
(e.g. SQLModel) are not installed.  This module is intentionally
kept minimal and free of internal imports so that low-level modules
like ``base`` can use it without reaching into higher-level packages.
"""

from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from sqlalchemy.orm import Mapper
    from sqlalchemy.sql import FromClause


class SQLModelBaseLike:
    """Placeholder for sqlmodel.SQLModel when the package is not installed.

    Declares the same structural attributes as :class:`ModelProtocol`
    so that type checkers can see SQLModel ``table=True`` models as
    protocol-compatible without requiring the real SQLModel package.
    """

    if TYPE_CHECKING:
        __table__: "FromClause"
        __mapper__: "Mapper[Any]"
        __name__: str

    model_fields: ClassVar[dict[str, Any]] = {}


try:
    from sqlmodel import SQLModel as SQLModelBase

    SQLMODEL_INSTALLED: bool = True  # pyright: ignore[reportConstantRedefinition]
except ImportError:
    SQLModelBase = SQLModelBaseLike  # type: ignore[assignment,misc]
    SQLMODEL_INSTALLED = False  # pyright: ignore[reportConstantRedefinition]

__all__ = (
    "SQLMODEL_INSTALLED",
    "SQLModelBase",
    "SQLModelBaseLike",
)
