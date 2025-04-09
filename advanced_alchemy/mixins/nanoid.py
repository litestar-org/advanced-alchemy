from typing import TYPE_CHECKING

from sqlalchemy.orm import Mapped, declarative_mixin, declared_attr, mapped_column

from advanced_alchemy.mixins.sentinel import SentinelMixin
from advanced_alchemy.types import NANOID_INSTALLED

if NANOID_INSTALLED and not TYPE_CHECKING:
    from fastnanoid import (  # type: ignore[import-not-found,unused-ignore]  # pyright: ignore[reportMissingImports]
        generate as nanoid,
    )
else:
    from uuid import uuid4 as nanoid  # type: ignore[assignment,unused-ignore]


@declarative_mixin
class NanoIDPrimaryKey(SentinelMixin):
    """Nano ID Primary Key Field Mixin."""

    __abstract__ = True

    @declared_attr
    def id(cls) -> Mapped[str]:
        """Nano ID Primary key column.

        Returns:
            Nano ID Primary key column.
        """
        return mapped_column(default=nanoid, primary_key=True)
