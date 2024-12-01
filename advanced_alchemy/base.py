"""Application ORM configuration."""

from __future__ import annotations

import contextlib
import re
from datetime import date, datetime
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable
from uuid import UUID

from sqlalchemy import Date, MetaData, String
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapper,
    declared_attr,
    registry,
)
from sqlalchemy.orm.decl_base import _TableArgsType as TableArgsType  # pyright: ignore[reportPrivateUsage]
from typing_extensions import TypeVar

from advanced_alchemy.mixins import (
    AuditColumns as _AuditColumns,
)
from advanced_alchemy.mixins import (
    BigIntPrimaryKey as _BigIntPrimaryKey,
)
from advanced_alchemy.mixins import (
    NanoIDPrimaryKey as _NanoIDPrimaryKey,
)
from advanced_alchemy.mixins import (
    SlugKey as _SlugKey,
)
from advanced_alchemy.mixins import (
    UUIDPrimaryKey as _UUIDPrimaryKey,
)
from advanced_alchemy.mixins import (
    UUIDv6PrimaryKey as _UUIDv6PrimaryKey,
)
from advanced_alchemy.mixins import (
    UUIDv7PrimaryKey as _UUIDv7PrimaryKey,
)
from advanced_alchemy.types import GUID, DateTimeUTC, JsonB
from advanced_alchemy.utils.dataclass import DataclassProtocol
from advanced_alchemy.utils.deprecation import deprecated

if TYPE_CHECKING:
    from sqlalchemy.sql import FromClause
    from sqlalchemy.sql.schema import (
        _NamingSchemaParameter as NamingSchemaParameter,  # pyright: ignore[reportPrivateUsage]
    )
    from sqlalchemy.types import TypeEngine


__all__ = (
    "AuditColumns",
    "BasicAttributes",
    "BigIntAuditBase",
    "BigIntBase",
    "BigIntPrimaryKey",
    "CommonTableAttributes",
    "ModelProtocol",
    "NanoIDAuditBase",
    "NanoIDBase",
    "NanoIDPrimaryKey",
    "SQLQuery",
    "SlugKey",
    "TableArgsType",
    "UUIDAuditBase",
    "UUIDBase",
    "UUIDPrimaryKey",
    "UUIDv6AuditBase",
    "UUIDv6Base",
    "UUIDv6PrimaryKey",
    "UUIDv7AuditBase",
    "UUIDv7Base",
    "UUIDv7PrimaryKey",
    "create_registry",
    "merge_table_arguments",
    "orm_registry",
)


UUIDBaseT = TypeVar("UUIDBaseT", bound="UUIDBase")
"""Type variable for :class:`UUIDBase`."""
BigIntBaseT = TypeVar("BigIntBaseT", bound="BigIntBase")
"""Type variable for :class:`BigIntBase`."""
UUIDv6BaseT = TypeVar("UUIDv6BaseT", bound="UUIDv6Base")
"""Type variable for :class:`UUIDv6Base`."""
UUIDv7BaseT = TypeVar("UUIDv7BaseT", bound="UUIDv7Base")
"""Type variable for :class:`UUIDv7Base`."""
NanoIDBaseT = TypeVar("NanoIDBaseT", bound="NanoIDBase")
"""Type variable for :class:`NanoIDBase`."""

convention: NamingSchemaParameter = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}
"""Templates for automated constraint name generation."""
table_name_regexp = re.compile("((?<=[a-z0-9])[A-Z]|(?!^)[A-Z](?=[a-z]))")
"""Regular expression for table name"""


@deprecated(
    version="0.26.0",
    alternative="advanced_alchemy.mixins.BigIntPrimaryKey",
    removal_in="1.0.0",
    info="`BigIntPrimaryKey` has been moved to `advanced_alchemy.mixins`",
)
class BigIntPrimaryKey(_BigIntPrimaryKey):
    """BigInt Primary Key Field Mixin.

    .. deprecated:: 0.26.0
        Use :class:`advanced_alchemy.mixins.BigIntPrimaryKey` instead.
    """


@deprecated(
    version="0.26.0",
    alternative="advanced_alchemy.mixins.UUIDPrimaryKey",
    removal_in="1.0.0",
    info="`UUIDPrimaryKey` has been moved to `advanced_alchemy.mixins`",
)
class UUIDPrimaryKey(_UUIDPrimaryKey):
    """UUID Primary Key Field Mixin.

    .. deprecated:: 0.26.0
        Use :class:`advanced_alchemy.mixins.UUIDPrimaryKey` instead.
    """


@deprecated(
    version="0.26.0",
    alternative="advanced_alchemy.mixins.UUIDv6PrimaryKey",
    removal_in="1.0.0",
    info="`UUIDv6PrimaryKey` has been moved to `advanced_alchemy.mixins`",
)
class UUIDv6PrimaryKey(_UUIDv6PrimaryKey):
    """UUID v6 Primary Key Field Mixin.

    .. deprecated:: 0.26.0
        Use :class:`advanced_alchemy.mixins.UUIDv6PrimaryKey` instead.
    """


@deprecated(
    version="0.26.0",
    alternative="advanced_alchemy.mixins.UUIDv7PrimaryKey",
    removal_in="1.0.0",
    info="`UUIDv7PrimaryKey` has been moved to `advanced_alchemy.mixins`",
)
class UUIDv7PrimaryKey(_UUIDv7PrimaryKey):
    """UUID v7 Primary Key Field Mixin.

    .. deprecated:: 0.26.0
        Use :class:`advanced_alchemy.mixins.UUIDv7PrimaryKey` instead.
    """


@deprecated(
    version="0.26.0",
    alternative="advanced_alchemy.mixins.NanoIDPrimaryKey",
    removal_in="1.0.0",
    info="`NanoIDPrimaryKey` has been moved to `advanced_alchemy.mixins`",
)
class NanoIDPrimaryKey(_NanoIDPrimaryKey):
    """Nano ID Primary Key Field Mixin.

    .. deprecated:: 0.26.0
        Use :class:`advanced_alchemy.mixins.NanoIDPrimaryKey` instead.
    """


@deprecated(
    version="0.26.0",
    alternative="advanced_alchemy.mixins.AuditColumns",
    removal_in="1.0.0",
    info="`AuditColumns` has been moved to `advanced_alchemy.mixins`",
)
class AuditColumns(_AuditColumns):
    """Created/Updated At Fields Mixin.

    .. deprecated:: 0.26.0
        Use :class:`advanced_alchemy.mixins.AuditColumns` instead.
    """


@deprecated(
    version="0.26.0",
    alternative="advanced_alchemy.mixins.SlugKey",
    removal_in="1.0.0",
    info="`SlugKey` has been moved to `advanced_alchemy.mixins`",
)
class SlugKey(_SlugKey):
    """Slug unique Field Model Mixin.

    .. deprecated:: 0.26.0
        Use :class:`advanced_alchemy.mixins.SlugKey` instead.
    """


def merge_table_arguments(cls: type[DeclarativeBase], table_args: TableArgsType | None = None) -> TableArgsType:
    """Merge Table Arguments.

    When using mixins that include their own table args, it is difficult to append info into the model such as a comment.

    This function helps you merge the args together.

    Args:
        cls: :class:`sqlalchemy.orm.DeclarativeBase` This is the model that will get the table args
        table_args: :class:`TableArgsType` additional information to add to table_args

    Returns:
        :class:`TableArgsType`
    """
    args: list[Any] = []
    kwargs: dict[str, Any] = {}

    mixin_table_args = (getattr(super(base_cls, cls), "__table_args__", None) for base_cls in cls.__bases__)  # pyright: ignore[reportUnknownParameter,reportUnknownArgumentType,reportArgumentType]

    for arg_to_merge in (*mixin_table_args, table_args):
        if arg_to_merge:
            if isinstance(arg_to_merge, tuple):
                last_positional_arg = arg_to_merge[-1]  # pyright: ignore[reportUnknownVariableType]
                args.extend(arg_to_merge[:-1])  # pyright: ignore[reportUnknownArgumentType]
                if isinstance(last_positional_arg, dict):
                    kwargs.update(last_positional_arg)  # pyright: ignore[reportUnknownArgumentType]
                else:
                    args.append(last_positional_arg)
            else:
                kwargs.update(arg_to_merge)

    if args:
        if kwargs:
            return (*args, kwargs)
        return tuple(args)
    return kwargs


@runtime_checkable
class ModelProtocol(Protocol):
    """The base SQLAlchemy model protocol."""

    if TYPE_CHECKING:
        __table__: FromClause
        __mapper__: Mapper[Any]
        __name__: str

    def to_dict(self, exclude: set[str] | None = None) -> dict[str, Any]:
        """Convert model to dictionary.

        Returns:
            Dict[str, Any]: A dict representation of the model
        """
        ...


class BasicAttributes:
    """Basic attributes for SQLALchemy tables and queries."""

    if TYPE_CHECKING:
        __name__: str
        __table__: FromClause
        __mapper__: Mapper[Any]

    def to_dict(self, exclude: set[str] | None = None) -> dict[str, Any]:
        """Convert model to dictionary.

        Returns:
            Dict[str, Any]: A dict representation of the model
        """
        exclude = {"sa_orm_sentinel", "_sentinel"}.union(self._sa_instance_state.unloaded).union(exclude or [])  # type: ignore[attr-defined]
        return {
            field: getattr(self, field)
            for field in self.__mapper__.columns.keys()  # noqa: SIM118
            if field not in exclude
        }


class CommonTableAttributes(BasicAttributes):
    """Common attributes for SQLALchemy tables.

    .. seealso::
        :class:`BasicAttributes`
    """

    if TYPE_CHECKING:
        __tablename__: str
    else:

        @declared_attr.directive
        def __tablename__(cls) -> str:
            """Infer table name from class name."""

            return table_name_regexp.sub(r"_\1", cls.__name__).lower()


def create_registry(
    custom_annotation_map: dict[Any, type[TypeEngine[Any]] | TypeEngine[Any]] | None = None,
) -> registry:
    """Create a new SQLAlchemy registry.

    Args:
        custom_annotation_map: :class:`dict` of custom type annotations to use for the registry

    Returns:
        :class:`sqlalchemy.orm.registry`
    """
    import uuid as core_uuid

    meta = MetaData(naming_convention=convention)
    type_annotation_map: dict[Any, type[TypeEngine[Any]] | TypeEngine[Any]] = {
        UUID: GUID,
        core_uuid.UUID: GUID,
        datetime: DateTimeUTC,
        date: Date,
        dict: JsonB,
        DataclassProtocol: JsonB,
    }
    with contextlib.suppress(ImportError):
        from pydantic import AnyHttpUrl, AnyUrl, EmailStr, IPvAnyAddress, IPvAnyInterface, IPvAnyNetwork, Json

        type_annotation_map.update(
            {
                EmailStr: String,
                AnyUrl: String,
                AnyHttpUrl: String,
                Json: JsonB,
                IPvAnyAddress: String,
                IPvAnyInterface: String,
                IPvAnyNetwork: String,
            }
        )
    with contextlib.suppress(ImportError):
        from msgspec import Struct

        type_annotation_map[Struct] = JsonB
    if custom_annotation_map is not None:
        type_annotation_map.update(custom_annotation_map)
    return registry(metadata=meta, type_annotation_map=type_annotation_map)


orm_registry = create_registry()


class UUIDBase(_UUIDPrimaryKey, CommonTableAttributes, DeclarativeBase):
    """Base for all SQLAlchemy declarative models with UUID v4 primary keys.

    .. seealso::
        :class:`advanced_alchemy.mixins.UUIDPrimaryKey`
        :class:`CommonTableAttributes`
        :class:`DeclarativeBase`
    """

    registry = orm_registry


class UUIDAuditBase(CommonTableAttributes, _UUIDPrimaryKey, _AuditColumns, DeclarativeBase):
    """Base for declarative models with UUID v4 primary keys and audit columns.

    .. seealso::
        :class:`CommonTableAttributes`
        :class:`advanced_alchemy.mixins.UUIDPrimaryKey`
        :class:`advanced_alchemy.mixins.AuditColumns`
        :class:`DeclarativeBase`
    """

    registry = orm_registry


class UUIDv6Base(_UUIDv6PrimaryKey, CommonTableAttributes, DeclarativeBase):
    """Base for all SQLAlchemy declarative models with UUID v6 primary keys.

    .. seealso::
        :class:`advanced_alchemy.mixins.UUIDv6PrimaryKey`
        :class:`CommonTableAttributes`
        :class:`DeclarativeBase`
    """

    registry = orm_registry


class UUIDv6AuditBase(CommonTableAttributes, _UUIDv6PrimaryKey, _AuditColumns, DeclarativeBase):
    """Base for declarative models with UUID v6 primary keys and audit columns.

    .. seealso::
        :class:`CommonTableAttributes`
        :class:`advanced_alchemy.mixins.UUIDv6PrimaryKey`
        :class:`advanced_alchemy.mixins.AuditColumns`
        :class:`DeclarativeBase`
    """

    registry = orm_registry


class UUIDv7Base(_UUIDv7PrimaryKey, CommonTableAttributes, DeclarativeBase):
    """Base for all SQLAlchemy declarative models with UUID v7 primary keys.

    .. seealso::
        :class:`advanced_alchemy.mixins.UUIDv7PrimaryKey`
        :class:`CommonTableAttributes`
        :class:`DeclarativeBase`
    """

    registry = orm_registry


class UUIDv7AuditBase(CommonTableAttributes, _UUIDv7PrimaryKey, _AuditColumns, DeclarativeBase):
    """Base for declarative models with UUID v7 primary keys and audit columns.

    .. seealso::
        :class:`CommonTableAttributes`
        :class:`advanced_alchemy.mixins.UUIDv7PrimaryKey`
        :class:`advanced_alchemy.mixins.AuditColumns`
        :class:`DeclarativeBase`
    """

    registry = orm_registry


class NanoIDBase(_NanoIDPrimaryKey, CommonTableAttributes, DeclarativeBase):
    """Base for all SQLAlchemy declarative models with Nano ID primary keys.

    .. seealso::
        :class:`advanced_alchemy.mixins.NanoIDPrimaryKey`
        :class:`CommonTableAttributes`
        :class:`DeclarativeBase`
    """

    registry = orm_registry


class NanoIDAuditBase(CommonTableAttributes, _NanoIDPrimaryKey, _AuditColumns, DeclarativeBase):
    """Base for declarative models with Nano ID primary keys and audit columns.

    .. seealso::
        :class:`CommonTableAttributes`
        :class:`advanced_alchemy.mixins.NanoIDPrimaryKey`
        :class:`advanced_alchemy.mixins.AuditColumns`
        :class:`DeclarativeBase`
    """

    registry = orm_registry


class BigIntBase(_BigIntPrimaryKey, CommonTableAttributes, DeclarativeBase):
    """Base for all SQLAlchemy declarative models with BigInt primary keys.

    .. seealso::
        :class:`advanced_alchemy.mixins.BigIntPrimaryKey`
        :class:`CommonTableAttributes`
        :class:`DeclarativeBase`
    """

    registry = orm_registry


class BigIntAuditBase(CommonTableAttributes, _BigIntPrimaryKey, _AuditColumns, DeclarativeBase):
    """Base for declarative models with BigInt primary keys and audit columns.

    .. seealso::
        :class:`CommonTableAttributes`
        :class:`advanced_alchemy.mixins.BigIntPrimaryKey`
        :class:`advanced_alchemy.mixins.AuditColumns`
        :class:`DeclarativeBase`
    """

    registry = orm_registry


class DefaultBase(CommonTableAttributes, DeclarativeBase):
    """Base for all SQLAlchemy declarative models.  No primary key is added.

    .. seealso::
        :class:`CommonTableAttributes`
        :class:`DeclarativeBase`
    """

    registry = orm_registry


class SQLQuery(BasicAttributes, DeclarativeBase):
    """Base for all SQLAlchemy custom mapped objects.

    .. seealso::
        :class:`BasicAttributes`
        :class:`DeclarativeBase`
    """

    __allow_unmapped__ = True
    registry = orm_registry
