"""Application ORM configuration."""

from __future__ import annotations

import contextlib
import re
from datetime import date, datetime, timezone
from typing import TYPE_CHECKING, Any, ClassVar, Protocol, TypeVar, runtime_checkable
from uuid import UUID

from sqlalchemy import Date, Index, MetaData, Sequence, String, UniqueConstraint
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Mapper,
    declarative_mixin,
    declared_attr,
    mapped_column,
    orm_insert_sentinel,
    registry,
)

from advanced_alchemy.types import GUID, UUID_UTILS_INSTALLED, BigIntIdentity, DateTimeUTC, JsonB

if UUID_UTILS_INSTALLED and not TYPE_CHECKING:
    from uuid_utils.compat import uuid4, uuid6, uuid7  # pyright: ignore[reportMissingImports]

else:
    from uuid import uuid4  # type: ignore[assignment]

    uuid6 = uuid4  # type: ignore[assignment]
    uuid7 = uuid4  # type: ignore[assignment]

if TYPE_CHECKING:
    from sqlalchemy.sql import FromClause
    from sqlalchemy.sql.schema import _NamingSchemaParameter as NamingSchemaParameter
    from sqlalchemy.types import TypeEngine


__all__ = (
    "AuditColumns",
    "BigIntAuditBase",
    "BigIntBase",
    "BigIntPrimaryKey",
    "CommonTableAttributes",
    "create_registry",
    "ModelProtocol",
    "UUIDAuditBase",
    "UUIDBase",
    "UUIDv6AuditBase",
    "UUIDv6Base",
    "UUIDv7AuditBase",
    "UUIDv7Base",
    "UUIDPrimaryKey",
    "UUIDv7PrimaryKey",
    "UUIDv6PrimaryKey",
    "SlugKey",
    "SQLQuery",
    "orm_registry",
)


UUIDBaseT = TypeVar("UUIDBaseT", bound="UUIDBase")
BigIntBaseT = TypeVar("BigIntBaseT", bound="BigIntBase")
UUIDv6BaseT = TypeVar("UUIDv6BaseT", bound="UUIDv6Base")
UUIDv7BaseT = TypeVar("UUIDv7BaseT", bound="UUIDv7Base")

convention: NamingSchemaParameter = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}
"""Templates for automated constraint name generation."""


@runtime_checkable
class ModelProtocol(Protocol):
    """The base SQLAlchemy model protocol."""

    __table__: FromClause
    __mapper__: Mapper
    __name__: ClassVar[str]

    def to_dict(self, exclude: set[str] | None = None) -> dict[str, Any]:
        """Convert model to dictionary.

        Returns:
            dict[str, Any]: A dict representation of the model
        """
        ...


class UUIDPrimaryKey:
    """UUID Primary Key Field Mixin."""

    id: Mapped[UUID] = mapped_column(default=uuid4, primary_key=True)
    """UUID Primary key column."""

    @declared_attr
    def _sentinel(cls) -> Mapped[int]:
        return orm_insert_sentinel(name="sa_orm_sentinel")


class UUIDv6PrimaryKey:
    """UUID v6 Primary Key Field Mixin."""

    id: Mapped[UUID] = mapped_column(default=uuid6, primary_key=True)
    """UUID Primary key column."""

    @declared_attr
    def _sentinel(cls) -> Mapped[int]:
        return orm_insert_sentinel(name="sa_orm_sentinel")


class UUIDv7PrimaryKey:
    """UUID v7 Primary Key Field Mixin."""

    id: Mapped[UUID] = mapped_column(default=uuid7, primary_key=True)
    """UUID Primary key column."""

    @declared_attr
    def _sentinel(cls) -> Mapped[int]:
        return orm_insert_sentinel(name="sa_orm_sentinel")


class BigIntPrimaryKey:
    """BigInt Primary Key Field Mixin."""

    # noinspection PyMethodParameters
    @declared_attr
    def id(cls) -> Mapped[int]:
        """BigInt Primary key column."""
        return mapped_column(
            BigIntIdentity,
            Sequence(f"{cls.__tablename__}_id_seq", optional=False),  # type: ignore[attr-defined]
            primary_key=True,
        )


class AuditColumns:
    """Created/Updated At Fields Mixin."""

    created_at: Mapped[datetime] = mapped_column(
        DateTimeUTC(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    """Date/time of instance creation."""
    updated_at: Mapped[datetime] = mapped_column(
        DateTimeUTC(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    """Date/time of instance last update."""


class CommonTableAttributes:
    """Common attributes for SQLALchemy tables."""

    __name__: ClassVar[str]
    __table__: FromClause
    __mapper__: Mapper

    # noinspection PyMethodParameters
    @declared_attr.directive
    def __tablename__(cls) -> str:
        """Infer table name from class name."""
        regexp = re.compile("((?<=[a-z0-9])[A-Z]|(?!^)[A-Z](?=[a-z]))")
        return regexp.sub(r"_\1", cls.__name__).lower()

    def to_dict(self, exclude: set[str] | None = None) -> dict[str, Any]:
        """Convert model to dictionary.

        Returns:
            dict[str, Any]: A dict representation of the model
        """
        exclude = {"sa_orm_sentinel", "_sentinel"}.union(self._sa_instance_state.unloaded).union(exclude or [])  # type: ignore[attr-defined]
        return {field.name: getattr(self, field.name) for field in self.__table__.columns if field.name not in exclude}


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
    def _create_unique_slug_index(*_args: Any, **kwargs: Any) -> bool:
        return bool(kwargs["dialect"].name.startswith("spanner"))

    @staticmethod
    def _create_unique_slug_constraint(*_args: Any, **kwargs: Any) -> bool:
        return not kwargs["dialect"].name.startswith("spanner")

    @declared_attr.directive
    def __table_args__(cls) -> tuple:
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


def create_registry(
    custom_annotation_map: dict[type, type[TypeEngine[Any]] | TypeEngine[Any]] | None = None,
) -> registry:
    """Create a new SQLAlchemy registry."""
    import uuid as core_uuid

    meta = MetaData(naming_convention=convention)
    type_annotation_map: dict[type, type[TypeEngine[Any]] | TypeEngine[Any]] = {
        UUID: GUID,
        core_uuid.UUID: GUID,
        datetime: DateTimeUTC,
        date: Date,
        dict: JsonB,
    }
    with contextlib.suppress(ImportError):
        from pydantic import AnyHttpUrl, AnyUrl, EmailStr, Json

        type_annotation_map.update(  # pyright: ignore[reportCallIssue]
            {EmailStr: String, AnyUrl: String, AnyHttpUrl: String, Json: JsonB},  # pyright: ignore[reportArgumentType]
        )
    with contextlib.suppress(ImportError):
        from msgspec import Struct

        type_annotation_map[Struct] = JsonB
    if custom_annotation_map is not None:
        type_annotation_map.update(custom_annotation_map)
    return registry(metadata=meta, type_annotation_map=type_annotation_map)


orm_registry = create_registry()


class UUIDBase(UUIDPrimaryKey, CommonTableAttributes, DeclarativeBase):
    """Base for all SQLAlchemy declarative models with UUID primary keys."""

    registry = orm_registry


class UUIDAuditBase(CommonTableAttributes, UUIDPrimaryKey, AuditColumns, DeclarativeBase):
    """Base for declarative models with UUID primary keys and audit columns."""

    registry = orm_registry


class UUIDv6Base(UUIDv6PrimaryKey, CommonTableAttributes, DeclarativeBase):
    """Base for all SQLAlchemy declarative models with UUID primary keys."""

    registry = orm_registry


class UUIDv6AuditBase(CommonTableAttributes, UUIDv6PrimaryKey, AuditColumns, DeclarativeBase):
    """Base for declarative models with UUID primary keys and audit columns."""

    registry = orm_registry


class UUIDv7Base(UUIDv7PrimaryKey, CommonTableAttributes, DeclarativeBase):
    """Base for all SQLAlchemy declarative models with UUID primary keys."""

    registry = orm_registry


class UUIDv7AuditBase(CommonTableAttributes, UUIDv7PrimaryKey, AuditColumns, DeclarativeBase):
    """Base for declarative models with UUID primary keys and audit columns."""

    registry = orm_registry


class BigIntBase(BigIntPrimaryKey, CommonTableAttributes, DeclarativeBase):
    """Base for all SQLAlchemy declarative models with BigInt primary keys."""

    registry = orm_registry


class BigIntAuditBase(CommonTableAttributes, BigIntPrimaryKey, AuditColumns, DeclarativeBase):
    """Base for declarative models with BigInt primary keys and audit columns."""

    registry = orm_registry


class SQLQuery(DeclarativeBase):
    """Base for all SQLAlchemy custom mapped objects."""

    __allow_unmapped__ = True
    registry = orm_registry

    def to_dict(self, exclude: set[str] | None = None) -> dict[str, Any]:
        """Convert model to dictionary.

        Returns:
            dict[str, Any]: A dict representation of the model
        """
        exclude = {"sa_orm_sentinel", "_sentinel"}.union(self._sa_instance_state.unloaded).union(exclude or [])  # type: ignore[attr-defined]
        return {field.name: getattr(self, field.name) for field in self.__table__.columns if field.name not in exclude}
