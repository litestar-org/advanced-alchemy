from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, declarative_mixin, declared_attr, mapped_column

if TYPE_CHECKING:
    from sqlalchemy.orm.decl_base import _TableArgsType as TableArgsType  # pyright: ignore[reportPrivateUsage]


@declarative_mixin
class SlugKey:
    """Slug unique Field Model Mixin."""

    @declared_attr
    def slug(cls) -> Mapped[str]:
        """Slug field."""
        return mapped_column(
            String(length=100),
            nullable=False,
        )

    @staticmethod
    def _create_unique_slug_index(*_: Any, **kwargs: Any) -> bool:
        return bool(kwargs["dialect"].name.startswith("spanner"))

    @staticmethod
    def _create_unique_slug_constraint(*_: Any, **kwargs: Any) -> bool:
        return not kwargs["dialect"].name.startswith("spanner")

    @declared_attr.directive
    @classmethod
    def __table_args__(cls) -> TableArgsType:
        return (
            UniqueConstraint(
                cls.slug,
                name=f"uq_{cls.__tablename__}_slug",  # type: ignore[attr-defined]
            ).ddl_if(callable_=cls._create_unique_slug_constraint),
            Index(
                f"ix_{cls.__tablename__}_slug_unique",  # type: ignore[attr-defined]
                cls.slug,
                unique=True,
            ).ddl_if(callable_=cls._create_unique_slug_index),
        )
