from typing import TypedDict

from sqlalchemy.orm import Mapped, MappedAsDataclass, declarative_mixin, declared_attr, mapped_column
from sqlalchemy.sql.schema import (
    _InsertSentinelColumnDefault as InsertSentinelColumnDefault,  # pyright: ignore [reportPrivateUsage]
)


class SentinelKwargs(TypedDict, total=False):
    init: bool


@declarative_mixin
class SentinelMixin:
    """Mixin to add a sentinel column for SQLAlchemy models."""

    kwargs: SentinelKwargs

    def __init_subclass__(cls) -> None:
        if issubclass(cls, MappedAsDataclass):
            cls.kwargs = {"init": False}

        else:
            cls.kwargs = {}

    @declared_attr
    def _sentinel(cls) -> Mapped[int]:
        return mapped_column(
            name="sa_orm_sentinel",
            insert_default=InsertSentinelColumnDefault(),
            _omit_from_statements=True,
            insert_sentinel=True,
            use_existing_column=True,
            nullable=True,
            **cls.kwargs,
        )
