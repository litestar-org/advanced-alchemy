from __future__ import annotations

from sqlalchemy import Sequence
from sqlalchemy.orm import Mapped, declared_attr, mapped_column

from advanced_alchemy.types import BigIntIdentity


class BigIntPrimaryKey:
    """BigInt Primary Key Field Mixin."""

    @declared_attr
    def id(cls) -> Mapped[int]:
        """BigInt Primary key column."""
        return mapped_column(
            BigIntIdentity,
            Sequence(f"{cls.__tablename__}_id_seq", optional=False),  # type: ignore[attr-defined]
            primary_key=True,
        )
