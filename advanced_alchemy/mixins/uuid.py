from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy.orm import Mapped, declarative_mixin, mapped_column

from advanced_alchemy.mixins.sentinel import SentinelMixin
from advanced_alchemy.types import UUID_UTILS_INSTALLED

if UUID_UTILS_INSTALLED and not TYPE_CHECKING:
    from uuid_utils.compat import (  # type: ignore[no-redef,unused-ignore]  # pyright: ignore[reportMissingImports]
        uuid4,
        uuid6,
        uuid7,
    )
else:
    from uuid import uuid4  # type: ignore[no-redef,unused-ignore]

    uuid6 = uuid4  # type: ignore[assignment, unused-ignore]
    uuid7 = uuid4  # type: ignore[assignment, unused-ignore]


@declarative_mixin
class UUIDPrimaryKey(SentinelMixin):
    """UUID Primary Key Field Mixin."""

    id: Mapped[UUID] = mapped_column(default=uuid4, primary_key=True)
    """UUID Primary key column."""


@declarative_mixin
class UUIDv6PrimaryKey(SentinelMixin):
    """UUID v6 Primary Key Field Mixin."""

    id: Mapped[UUID] = mapped_column(default=uuid6, primary_key=True)
    """UUID Primary key column."""


@declarative_mixin
class UUIDv7PrimaryKey(SentinelMixin):
    """UUID v7 Primary Key Field Mixin."""

    id: Mapped[UUID] = mapped_column(default=uuid7, primary_key=True)
    """UUID Primary key column."""
