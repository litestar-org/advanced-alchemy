from typing import TypedDict

from sqlalchemy.orm import Mapped, MappedAsDataclass, declarative_mixin, declared_attr, mapped_column
from sqlalchemy.sql.schema import _InsertSentinelColumnDefault  # pyright: ignore [reportPrivateUsage]
from typing_extensions import NotRequired


class SentinelKwargs(TypedDict):
    init: NotRequired[bool]


@declarative_mixin
class SentinelMixin:
    """Mixin to add a sentinel column for SQLAlchemy models."""

    __abstract__ = True

    @declared_attr
    def _sentinel(cls) -> Mapped[int]:
        kwargs: SentinelKwargs = {}
        if issubclass(type[cls], MappedAsDataclass):
            kwargs["init"] = False
        return mapped_column(
            name="sa_orm_sentinel",
            insert_default=_InsertSentinelColumnDefault(),
            _omit_from_statements=True,
            insert_sentinel=True,
            use_existing_column=True,
            nullable=True,
            **kwargs,
        )
