"""Common base classes for SQLAlchemy declarative models."""

import contextlib
import datetime
import re
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any, Optional, Protocol, Union, cast, runtime_checkable
from uuid import UUID

from sqlalchemy import Date, MetaData, String
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapper,
    declared_attr,
)
from sqlalchemy.orm import (
    registry as SQLAlchemyRegistry,  # noqa: N812
)
from sqlalchemy.orm.decl_base import (
    _TableArgsType as TableArgsType,  # pyright: ignore[reportPrivateUsage]
)
from sqlalchemy.types import TypeEngine
from typing_extensions import Self, TypeVar

from advanced_alchemy.mixins import (
    AuditColumns,
    BigIntPrimaryKey,
    IdentityPrimaryKey,
    NanoIDPrimaryKey,
    UUIDPrimaryKey,
    UUIDv6PrimaryKey,
    UUIDv7PrimaryKey,
)
from advanced_alchemy.types import GUID, DateTimeUTC, FileObject, FileObjectList, JsonB, StoredObject
from advanced_alchemy.utils.dataclass import DataclassProtocol

if TYPE_CHECKING:
    from sqlalchemy.sql import FromClause
    from sqlalchemy.sql.schema import (
        _NamingSchemaParameter as NamingSchemaParameter,  # pyright: ignore[reportPrivateUsage]
    )


__all__ = (
    "AdvancedDeclarativeBase",
    "BasicAttributes",
    "BigIntAuditBase",
    "BigIntBase",
    "BigIntBaseT",
    "CommonTableAttributes",
    "DefaultBase",
    "IdentityAuditBase",
    "IdentityBase",
    "IdentityBaseT",
    "ModelProtocol",
    "NanoIDAuditBase",
    "NanoIDBase",
    "NanoIDBaseT",
    "SQLQuery",
    "TableArgsType",
    "UUIDAuditBase",
    "UUIDBase",
    "UUIDBaseT",
    "UUIDv6AuditBase",
    "UUIDv6Base",
    "UUIDv6BaseT",
    "UUIDv7AuditBase",
    "UUIDv7Base",
    "UUIDv7BaseT",
    "convention",
    "create_registry",
    "merge_table_arguments",
    "metadata_registry",
    "orm_registry",
    "table_name_regexp",
)


UUIDBaseT = TypeVar("UUIDBaseT", bound="UUIDBase")
"""Type variable for :class:`UUIDBase`."""
BigIntBaseT = TypeVar("BigIntBaseT", bound="BigIntBase")
"""Type variable for :class:`BigIntBase`."""
IdentityBaseT = TypeVar("IdentityBaseT", bound="IdentityBase")
"""Type variable for :class:`IdentityBase`."""
UUIDv6BaseT = TypeVar("UUIDv6BaseT", bound="UUIDv6Base")
"""Type variable for :class:`UUIDv6Base`."""
UUIDv7BaseT = TypeVar("UUIDv7BaseT", bound="UUIDv7Base")
"""Type variable for :class:`UUIDv7Base`."""
NanoIDBaseT = TypeVar("NanoIDBaseT", bound="NanoIDBase")
"""Type variable for :class:`NanoIDBase`."""

convention: "NamingSchemaParameter" = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}
"""Templates for automated constraint name generation."""
table_name_regexp = re.compile(r"((?<=[a-z0-9])[A-Z]|(?!^)[A-Z](?=[a-z]))")
"""Regular expression for table name"""


def merge_table_arguments(cls: type[DeclarativeBase], table_args: Optional[TableArgsType] = None) -> TableArgsType:
    """Merge Table Arguments.

    This function helps merge table arguments when using mixins that include their own table args,
    making it easier to append additional information such as comments or constraints to the model.

    Args:
        cls (type[:class:`sqlalchemy.orm.DeclarativeBase`]): The model that will get the table args.
        table_args (:class:`TableArgsType`, optional): Additional information to add to table_args.

    Returns:
        :class:`TableArgsType`: Merged table arguments.
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
                kwargs.update(arg_to_merge)  # pyright: ignore

    if args:
        if kwargs:
            return (*args, kwargs)
        return tuple(args)
    return kwargs


@runtime_checkable
class ModelProtocol(Protocol):
    """The base SQLAlchemy model protocol.

    Attributes:
        __table__ (:class:`sqlalchemy.sql.FromClause`): The table associated with the model.
        __mapper__ (:class:`sqlalchemy.orm.Mapper`): The mapper for the model.
        __name__ (str): The name of the model.
    """

    if TYPE_CHECKING:
        __table__: FromClause
        __mapper__: Mapper[Any]
        __name__: str

    def to_dict(self, exclude: Optional[set[str]] = None) -> dict[str, Any]:
        """Convert model to dictionary.

        Returns:
            Dict[str, Any]: A dict representation of the model
        """
        ...


class BasicAttributes:
    """Basic attributes for SQLAlchemy tables and queries.

    Provides a method to convert the model to a dictionary representation.

    Methods:
        to_dict: Converts the model to a dictionary, excluding specified fields. :no-index:
    """

    if TYPE_CHECKING:
        __name__: str
        __table__: FromClause
        __mapper__: Mapper[Any]

    def to_dict(self, exclude: Optional[set[str]] = None) -> dict[str, Any]:
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
    """Common attributes for SQLAlchemy tables.

    Inherits from :class:`BasicAttributes` and provides a mechanism to infer table names from class names.

    Attributes:
        __tablename__ (str): The inferred table name.
    """

    if TYPE_CHECKING:
        __tablename__: str
    else:

        @declared_attr.directive
        def __tablename__(cls) -> str:
            """Infer table name from class name.

            Returns:
                str: The inferred table name.
            """

            return table_name_regexp.sub(r"_\1", cls.__name__).lower()


def create_registry(
    custom_annotation_map: Optional[dict[Any, Union[type[TypeEngine[Any]], TypeEngine[Any]]]] = None,
) -> SQLAlchemyRegistry:
    """Create a new SQLAlchemy registry.

    Args:
        custom_annotation_map (dict, optional): Custom type annotations to use for the registry.

    Returns:
        :class:`sqlalchemy.orm.registry`: A new SQLAlchemy registry with the specified type annotations.
    """
    import uuid as core_uuid

    meta = MetaData(naming_convention=convention)
    type_annotation_map: dict[Any, Union[type[TypeEngine[Any]], TypeEngine[Any]]] = {
        UUID: GUID,
        core_uuid.UUID: GUID,
        datetime.datetime: DateTimeUTC,
        datetime.date: Date,
        dict: JsonB,
        dict[str, Any]: JsonB,
        dict[str, str]: JsonB,
        DataclassProtocol: JsonB,
        FileObject: StoredObject,
        FileObjectList: StoredObject,
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
    return SQLAlchemyRegistry(metadata=meta, type_annotation_map=type_annotation_map)


orm_registry = create_registry()


class MetadataRegistry:
    """A registry for metadata.

    Provides methods to get and set metadata for different bind keys.

    Methods:
        get: Retrieves the metadata for a given bind key.
        set: Sets the metadata for a given bind key.
    """

    _instance: Optional["MetadataRegistry"] = None
    _registry: dict[Union[str, None], MetaData] = {None: orm_registry.metadata}

    def __new__(cls) -> Self:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cast("Self", cls._instance)

    def get(self, bind_key: Optional[str] = None) -> MetaData:
        """Get the metadata for the given bind key.

        Args:
            bind_key (Optional[str]): The bind key for the metadata.

        Returns:
            :class:`sqlalchemy.MetaData`: The metadata for the given bind key.
        """
        return self._registry.setdefault(bind_key, MetaData(naming_convention=convention))

    def set(self, bind_key: Optional[str], metadata: MetaData) -> None:
        """Set the metadata for the given bind key.

        Args:
            bind_key (Optional[str]): The bind key for the metadata.
            metadata (:class:`sqlalchemy.MetaData`): The metadata to set.
        """
        self._registry[bind_key] = metadata

    def __iter__(self) -> Iterator[Union[str, None]]:
        return iter(self._registry)

    def __getitem__(self, bind_key: Union[str, None]) -> MetaData:
        return self._registry[bind_key]

    def __setitem__(self, bind_key: Union[str, None], metadata: MetaData) -> None:
        self._registry[bind_key] = metadata

    def __contains__(self, bind_key: Union[str, None]) -> bool:
        return bind_key in self._registry


metadata_registry = MetadataRegistry()


class AdvancedDeclarativeBase(DeclarativeBase):
    """A subclass of declarative base that allows for overriding of the registry.

    Inherits from :class:`sqlalchemy.orm.DeclarativeBase`.

    Attributes:
        registry (:class:`sqlalchemy.orm.registry`): The registry for the declarative base.
        __metadata_registry__ (:class:`~advanced_alchemy.base.MetadataRegistry`): The metadata registry.
        __bind_key__ (Optional[:class:`str`]): The bind key for the metadata.
    """

    registry = orm_registry
    __abstract__ = True
    __metadata_registry__: MetadataRegistry = MetadataRegistry()
    __bind_key__: Optional[str] = None

    def __init_subclass__(cls, **kwargs: Any) -> None:
        bind_key = getattr(cls, "__bind_key__", None)
        if bind_key is not None:
            cls.metadata = cls.__metadata_registry__.get(bind_key)
        elif None not in cls.__metadata_registry__ and getattr(cls, "metadata", None) is not None:
            cls.__metadata_registry__[None] = cls.metadata
        super().__init_subclass__(**kwargs)


class UUIDBase(UUIDPrimaryKey, CommonTableAttributes, AdvancedDeclarativeBase, AsyncAttrs):
    """Base for all SQLAlchemy declarative models with UUID v4 primary keys.

    .. seealso::
        :class:`CommonTableAttributes`
        :class:`advanced_alchemy.mixins.UUIDPrimaryKey`
        :class:`AdvancedDeclarativeBase`
        :class:`AsyncAttrs`
    """

    __abstract__ = True


class UUIDAuditBase(CommonTableAttributes, UUIDPrimaryKey, AuditColumns, AdvancedDeclarativeBase, AsyncAttrs):
    """Base for declarative models with UUID v4 primary keys and audit columns.

    .. seealso::
        :class:`CommonTableAttributes`
        :class:`advanced_alchemy.mixins.UUIDPrimaryKey`
        :class:`advanced_alchemy.mixins.AuditColumns`
        :class:`AdvancedDeclarativeBase`
        :class:`AsyncAttrs`
    """

    __abstract__ = True


class UUIDv6Base(UUIDv6PrimaryKey, CommonTableAttributes, AdvancedDeclarativeBase, AsyncAttrs):
    """Base for all SQLAlchemy declarative models with UUID v6 primary keys.

    .. seealso::
        :class:`advanced_alchemy.mixins.UUIDv6PrimaryKey`
        :class:`CommonTableAttributes`
        :class:`AdvancedDeclarativeBase`
        :class:`AsyncAttrs`
    """

    __abstract__ = True


class UUIDv6AuditBase(CommonTableAttributes, UUIDv6PrimaryKey, AuditColumns, AdvancedDeclarativeBase, AsyncAttrs):
    """Base for declarative models with UUID v6 primary keys and audit columns.

    .. seealso::
        :class:`CommonTableAttributes`
        :class:`advanced_alchemy.mixins.UUIDv6PrimaryKey`
        :class:`advanced_alchemy.mixins.AuditColumns`
        :class:`AdvancedDeclarativeBase`
        :class:`AsyncAttrs`
    """

    __abstract__ = True


class UUIDv7Base(UUIDv7PrimaryKey, CommonTableAttributes, AdvancedDeclarativeBase, AsyncAttrs):
    """Base for all SQLAlchemy declarative models with UUID v7 primary keys.

    .. seealso::
        :class:`advanced_alchemy.mixins.UUIDv7PrimaryKey`
        :class:`CommonTableAttributes`
        :class:`AdvancedDeclarativeBase`
        :class:`AsyncAttrs`
    """

    __abstract__ = True


class UUIDv7AuditBase(CommonTableAttributes, UUIDv7PrimaryKey, AuditColumns, AdvancedDeclarativeBase, AsyncAttrs):
    """Base for declarative models with UUID v7 primary keys and audit columns.

    .. seealso::
        :class:`CommonTableAttributes`
        :class:`advanced_alchemy.mixins.UUIDv7PrimaryKey`
        :class:`advanced_alchemy.mixins.AuditColumns`
        :class:`AdvancedDeclarativeBase`
        :class:`AsyncAttrs`
    """

    __abstract__ = True


class NanoIDBase(NanoIDPrimaryKey, CommonTableAttributes, AdvancedDeclarativeBase, AsyncAttrs):
    """Base for all SQLAlchemy declarative models with Nano ID primary keys.

    .. seealso::
        :class:`advanced_alchemy.mixins.NanoIDPrimaryKey`
        :class:`CommonTableAttributes`
        :class:`AdvancedDeclarativeBase`
        :class:`AsyncAttrs`
    """

    __abstract__ = True


class NanoIDAuditBase(CommonTableAttributes, NanoIDPrimaryKey, AuditColumns, AdvancedDeclarativeBase, AsyncAttrs):
    """Base for declarative models with Nano ID primary keys and audit columns.

    .. seealso::
        :class:`CommonTableAttributes`
        :class:`advanced_alchemy.mixins.NanoIDPrimaryKey`
        :class:`advanced_alchemy.mixins.AuditColumns`
        :class:`AdvancedDeclarativeBase`
        :class:`AsyncAttrs`
    """

    __abstract__ = True


class BigIntBase(BigIntPrimaryKey, CommonTableAttributes, AdvancedDeclarativeBase, AsyncAttrs):
    """Base for all SQLAlchemy declarative models with BigInt primary keys.

    .. seealso::
        :class:`advanced_alchemy.mixins.BigIntPrimaryKey`
        :class:`CommonTableAttributes`
        :class:`AdvancedDeclarativeBase`
        :class:`AsyncAttrs`
    """

    __abstract__ = True


class BigIntAuditBase(CommonTableAttributes, BigIntPrimaryKey, AuditColumns, AdvancedDeclarativeBase, AsyncAttrs):
    """Base for declarative models with BigInt primary keys and audit columns.

    .. seealso::
        :class:`CommonTableAttributes`
        :class:`advanced_alchemy.mixins.BigIntPrimaryKey`
        :class:`advanced_alchemy.mixins.AuditColumns`
        :class:`AdvancedDeclarativeBase`
        :class:`AsyncAttrs`
    """

    __abstract__ = True


class IdentityBase(IdentityPrimaryKey, CommonTableAttributes, AdvancedDeclarativeBase, AsyncAttrs):
    """Base for all SQLAlchemy declarative models with database IDENTITY primary keys.

    This model uses the database native IDENTITY feature for generating primary keys
    instead of using database sequences.

    .. seealso::
        :class:`advanced_alchemy.mixins.IdentityPrimaryKey`
        :class:`CommonTableAttributes`
        :class:`AdvancedDeclarativeBase`
        :class:`AsyncAttrs`
    """

    __abstract__ = True


class IdentityAuditBase(CommonTableAttributes, IdentityPrimaryKey, AuditColumns, AdvancedDeclarativeBase, AsyncAttrs):
    """Base for declarative models with database IDENTITY primary keys and audit columns.

    This model uses the database native IDENTITY feature for generating primary keys
    instead of using database sequences.

    .. seealso::
        :class:`CommonTableAttributes`
        :class:`advanced_alchemy.mixins.IdentityPrimaryKey`
        :class:`advanced_alchemy.mixins.AuditColumns`
        :class:`AdvancedDeclarativeBase`
        :class:`AsyncAttrs`
    """

    __abstract__ = True


class DefaultBase(CommonTableAttributes, AdvancedDeclarativeBase, AsyncAttrs):
    """Base for all SQLAlchemy declarative models.  No primary key is added.

    .. seealso::
        :class:`CommonTableAttributes`
        :class:`AdvancedDeclarativeBase`
        :class:`AsyncAttrs`
    """

    __abstract__ = True


class SQLQuery(BasicAttributes, AdvancedDeclarativeBase, AsyncAttrs):
    """Base for all SQLAlchemy custom mapped objects.

    .. seealso::
        :class:`BasicAttributes`
        :class:`AdvancedDeclarativeBase`
        :class:`AsyncAttrs`
    """

    __abstract__ = True
    __allow_unmapped__ = True
