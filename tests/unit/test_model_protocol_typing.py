"""Regression tests: plain SQLAlchemy declarative models satisfy ``ModelProtocol``.

``sqlalchemy.orm.DeclarativeBase`` declares ``__table__``/``__mapper__``/``__name__``
as ``ClassVar``, so ``ModelProtocol`` must declare them as ``ClassVar`` too — a plain
instance-variable declaration makes mypy reject every model not built on Advanced
Alchemy's own bases ("expected instance variable, got class variable"), which breaks
``SQLAlchemySyncRepository[PlainModel]`` and the service classes for external models.

The ``ModelProtocol``-annotated assignments below are the actual assertions: this
module is type-checked by mypy in CI, so a variance regression fails the build.
(``type-var`` is disabled for ``tests.*``, so the repository subclass documents the
downstream failure mode but the assignments are what fail CI.)
"""

from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from advanced_alchemy.base import ModelProtocol, UUIDBase
from advanced_alchemy.repository import SQLAlchemySyncRepository


class PlainBase(DeclarativeBase):
    """A declarative base with no Advanced Alchemy mixins."""


class PlainModel(PlainBase):
    """A model built directly on ``sqlalchemy.orm.DeclarativeBase``."""

    __tablename__ = "test_model_protocol_plain"

    id: Mapped[int] = mapped_column(primary_key=True)


class AAModel(UUIDBase):
    """A model built on Advanced Alchemy's own base."""

    __tablename__ = "test_model_protocol_aa"


class PlainModelRepository(SQLAlchemySyncRepository[PlainModel]):
    """The ``ModelT`` bound must accept plain declarative models."""

    model_type = PlainModel


def test_plain_declarative_model_satisfies_protocol_statically() -> None:
    instance: ModelProtocol = PlainModel(id=1)
    assert isinstance(instance, ModelProtocol)


def test_advanced_alchemy_model_satisfies_protocol_statically() -> None:
    instance: ModelProtocol = AAModel()
    assert isinstance(instance, ModelProtocol)
