from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.orm import Mapped, declarative_mixin, mapped_column

from advanced_alchemy.mixins.sentinel import SentinelMixin
from advanced_alchemy.types import NANOID_INSTALLED

if NANOID_INSTALLED and not TYPE_CHECKING:
    from fastnanoid import generate as nanoid  # pyright: ignore[reportMissingImports]
else:
    from uuid import uuid4 as nanoid  # type: ignore[assignment]


@declarative_mixin
class NanoIDPrimaryKey(SentinelMixin):
    """Nano ID Primary Key Field Mixin."""

    id: Mapped[str] = mapped_column(default=nanoid, primary_key=True)
    """Nano ID Primary key column."""
