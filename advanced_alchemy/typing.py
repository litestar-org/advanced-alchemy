"""Public type shims for optional dependencies.

Re-exports foundational stub types so that internal and external code
can ``from advanced_alchemy.typing import SQLModelBase`` without
reaching into private modules.
"""

from advanced_alchemy._typing import SQLMODEL_INSTALLED, SQLModelBase, SQLModelBaseLike

__all__ = (
    "SQLMODEL_INSTALLED",
    "SQLModelBase",
    "SQLModelBaseLike",
)
