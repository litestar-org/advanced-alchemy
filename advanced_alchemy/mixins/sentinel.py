from sqlalchemy.orm import Mapped, declarative_mixin, declared_attr, mapped_column
from sqlalchemy.sql.schema import _InsertSentinelColumnDefault as InsertSentinelColumnDefault


@declarative_mixin
class SentinelMixin:
    """Mixin to add a sentinel column for SQLAlchemy models."""

    @declared_attr
    def _sentinel(cls) -> Mapped[int]:
        return mapped_column(
            name='sa_orm_sentinel',
            init=False,
            insert_default=InsertSentinelColumnDefault(),
            _omit_from_statements=True,
            insert_sentinel=True,
            use_existing_column=True,
            nullable=True,
        )
