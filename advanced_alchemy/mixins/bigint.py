from typing import Any, Optional

from sqlalchemy import Sequence
from sqlalchemy.orm import Mapped, declarative_mixin, declared_attr, mapped_column

from advanced_alchemy.types import BigIntIdentity


def _get_schema(cls: "BigIntPrimaryKey") -> Optional[str]:  # pragma: nocover
    """Get the schema for the class if set via __table_args__, __table__, or __table_kwargs__."""
    table_args = getattr(cls, "__table_args__", None)
    if isinstance(table_args, dict) and "schema" in table_args:
        return table_args["schema"]  # type: ignore
    if isinstance(table_args, tuple) and table_args and isinstance(table_args[-1], dict) and "schema" in table_args[-1]:
        return table_args[-1]["schema"]  # type: ignore
    if hasattr(cls, "__table__") and hasattr(cls.__table__, "schema"):  # pyright: ignore
        return cls.__table__.schema  # type: ignore[no-any-return]
    table_kwargs = getattr(cls, "__table_kwargs__", None)
    if isinstance(table_kwargs, dict) and "schema" in table_kwargs:
        return table_kwargs["schema"]  # type: ignore
    return None


@declarative_mixin
class BigIntPrimaryKey:
    """BigInt Primary Key Field Mixin."""

    @declared_attr
    def id(cls) -> Mapped[int]:
        """BigInt Primary key column."""
        seq_kwargs: dict[str, Any] = {"optional": False}
        if schema := _get_schema(cls):
            seq_kwargs["schema"] = schema
        return mapped_column(
            BigIntIdentity,
            Sequence(f"{cls.__tablename__}_id_seq", **seq_kwargs),  # type: ignore[attr-defined]
            primary_key=True,
        )


@declarative_mixin
class IdentityPrimaryKey:
    """Primary Key Field Mixin using database IDENTITY feature.

    This mixin uses the database's native IDENTITY feature rather than a sequence.
    This can be more efficient for databases that support IDENTITY natively.
    """

    @declared_attr
    def id(cls) -> Mapped[int]:
        """Primary key column using IDENTITY."""
        return mapped_column(
            BigIntIdentity,
            primary_key=True,
            autoincrement=True,
        )
