"""Service object implementation for SQLAlchemy.

RepositoryService object is generic on the domain model type which
should be a SQLAlchemy model.
"""

import datetime
from collections.abc import Sequence
from enum import Enum
from functools import lru_cache, partial
from pathlib import Path, PurePath
from typing import TYPE_CHECKING, Any, Callable, Optional, Union, cast, overload
from uuid import UUID

from advanced_alchemy.exceptions import AdvancedAlchemyError
from advanced_alchemy.filters import LimitOffset, StatementFilter
from advanced_alchemy.service.pagination import OffsetPagination
from advanced_alchemy.service.typing import (
    ATTRS_INSTALLED,
    CATTRS_INSTALLED,
    MSGSPEC_INSTALLED,
    PYDANTIC_INSTALLED,
    BaseModel,
    FilterTypeT,
    ModelDTOT,
    Struct,
    convert,
    fields,
    get_type_adapter,
    is_attrs_schema,
    schema_dump,
    structure,
)

if TYPE_CHECKING:
    from sqlalchemy import ColumnElement, RowMapping
    from sqlalchemy.engine.row import Row

    from advanced_alchemy.base import ModelProtocol
    from advanced_alchemy.repository.typing import ModelOrRowMappingT

__all__ = ("ResultConverter", "find_filter")

DEFAULT_TYPE_DECODERS = [  # pyright: ignore[reportUnknownVariableType]
    (lambda x: x is UUID, lambda t, v: t(v.hex)),  # pyright: ignore[reportUnknownLambdaType,reportUnknownMemberType]
    (lambda x: x is datetime.datetime, lambda t, v: t(v.isoformat())),  # pyright: ignore[reportUnknownLambdaType,reportUnknownMemberType]
    (lambda x: x is datetime.date, lambda t, v: t(v.isoformat())),  # pyright: ignore[reportUnknownLambdaType,reportUnknownMemberType]
    (lambda x: x is datetime.time, lambda t, v: t(v.isoformat())),  # pyright: ignore[reportUnknownLambdaType,reportUnknownMemberType]
    (lambda x: x is Enum, lambda t, v: t(v.value)),  # pyright: ignore[reportUnknownLambdaType,reportUnknownMemberType]
]


def find_filter(
    filter_type: type[FilterTypeT],
    filters: "Union[Sequence[Union[StatementFilter, ColumnElement[bool]]], Sequence[StatementFilter]]",
) -> "Union[FilterTypeT, None]":
    """Get the filter specified by filter type from the filters.

    Args:
        filter_type: The type of filter to find.
        filters: filter types to apply to the query

    Returns:
        The match filter instance or None
    """
    return next(
        (cast("Optional[FilterTypeT]", filter_) for filter_ in filters if isinstance(filter_, filter_type)),
        None,
    )


class ResultConverter:
    """Simple mixin to help convert to a paginated response model.

    Single objects are transformed to the supplied schema type, and lists of objects are automatically transformed into an `OffsetPagination` response of the supplied schema type.

    Args:
        data: A database model instance or row mapping.
              Type: :class:`~advanced_alchemy.repository.typing.ModelOrRowMappingT`

    Returns:
        The converted schema object.
    """

    @overload
    def to_schema(
        self,
        data: "ModelOrRowMappingT",
        *,
        schema_type: None = None,
    ) -> "ModelOrRowMappingT": ...

    @overload
    def to_schema(
        self,
        data: "Union[ModelProtocol, RowMapping, Row[Any], dict[str, Any]]",
        *,
        schema_type: "type[ModelDTOT]",
    ) -> "ModelDTOT": ...

    @overload
    def to_schema(
        self,
        data: "ModelOrRowMappingT",
        total: "Optional[int]" = None,
        *,
        schema_type: None = None,
    ) -> "ModelOrRowMappingT": ...

    @overload
    def to_schema(
        self,
        data: "Union[ModelProtocol, RowMapping, Row[Any], dict[str, Any]]",
        total: "Optional[int]" = None,
        *,
        schema_type: "type[ModelDTOT]",
    ) -> "ModelDTOT": ...

    @overload
    def to_schema(
        self,
        data: "ModelOrRowMappingT",
        total: "Optional[int]" = None,
        filters: "Union[Sequence[Union[StatementFilter, ColumnElement[bool]]], Sequence[StatementFilter], None]" = None,
        *,
        schema_type: None = None,
    ) -> "ModelOrRowMappingT": ...

    @overload
    def to_schema(
        self,
        data: "Union[ModelProtocol, RowMapping, Row[Any], dict[str, Any]]",
        total: "Optional[int]" = None,
        filters: "Union[Sequence[Union[StatementFilter, ColumnElement[bool]]], Sequence[StatementFilter], None]" = None,
        *,
        schema_type: "type[ModelDTOT]",
    ) -> "ModelDTOT": ...

    @overload
    def to_schema(
        self,
        data: "Sequence[ModelOrRowMappingT]",
        *,
        schema_type: None = None,
    ) -> "OffsetPagination[ModelOrRowMappingT]": ...

    @overload
    def to_schema(
        self,
        data: "Union[Sequence[ModelProtocol], Sequence[RowMapping], Sequence[Row[Any]], Sequence[dict[str, Any]]]",
        *,
        schema_type: "type[ModelDTOT]",
    ) -> "OffsetPagination[ModelDTOT]": ...

    @overload
    def to_schema(
        self,
        data: "Sequence[ModelOrRowMappingT]",
        total: "Optional[int]" = None,
        filters: "Union[Sequence[Union[StatementFilter, ColumnElement[bool]]], Sequence[StatementFilter], None]" = None,
        *,
        schema_type: None = None,
    ) -> "OffsetPagination[ModelOrRowMappingT]": ...

    @overload
    def to_schema(
        self,
        data: "Union[Sequence[ModelProtocol], Sequence[RowMapping], Sequence[Row[Any]], Sequence[dict[str, Any]]]",
        total: "Optional[int]" = None,
        filters: "Union[Sequence[Union[StatementFilter, ColumnElement[bool]]], Sequence[StatementFilter], None]" = None,
        *,
        schema_type: "type[ModelDTOT]",
    ) -> "OffsetPagination[ModelDTOT]": ...

    def to_schema(
        self,
        data: "Union[ModelOrRowMappingT, Sequence[ModelOrRowMappingT], ModelProtocol, Sequence[ModelProtocol], RowMapping, Sequence[RowMapping], Row[Any], Sequence[Row[Any]], dict[str, Any], Sequence[dict[str, Any]]]",
        total: "Optional[int]" = None,
        filters: "Union[Sequence[Union[StatementFilter, ColumnElement[bool]]], Sequence[StatementFilter], None]" = None,
        *,
        schema_type: "Optional[type[ModelDTOT]]" = None,
    ) -> "Union[ModelOrRowMappingT, OffsetPagination[ModelOrRowMappingT], ModelDTOT, OffsetPagination[ModelDTOT]]":
        """Convert the object to a response schema.

        When `schema_type` is None, the model is returned with no conversion.

        Args:
            data: The return from one of the service calls.
              Type: :class:`~advanced_alchemy.repository.typing.ModelOrRowMappingT`
            total: The total number of rows in the data.
            filters: :class:`~advanced_alchemy.filters.StatementFilter`| :class:`sqlalchemy.sql.expression.ColumnElement` Collection of route filters.
            schema_type: :class:`~advanced_alchemy.service.typing.ModelDTOT` Optional schema type to convert the data to

        Raises:
            AdvancedAlchemyError: If `schema_type` is not a valid Pydantic, Msgspec, or attrs schema and all libraries are not installed.

        Returns:
            :class:`~advanced_alchemy.base.ModelProtocol` | :class:`sqlalchemy.orm.RowMapping` | :class:`~advanced_alchemy.service.pagination.OffsetPagination` | :class:`msgspec.Struct` | :class:`pydantic.BaseModel` | :class:`attrs class`
        """
        if filters is None:
            filters = []
        if schema_type is None:
            if not isinstance(data, Sequence):
                return cast("ModelOrRowMappingT", data)  # type: ignore[unreachable,unused-ignore]
            return cast(
                "OffsetPagination[ModelOrRowMappingT]",
                _create_pagination(cast("Sequence[ModelOrRowMappingT]", data), filters, total),
            )
        if MSGSPEC_INSTALLED and issubclass(schema_type, Struct):
            if not isinstance(data, Sequence):
                return convert(
                    obj=data,
                    type=schema_type,
                    from_attributes=True,
                    dec_hook=partial(
                        _default_msgspec_deserializer,
                        type_decoders=DEFAULT_TYPE_DECODERS,
                    ),
                )
            converted_items = convert(
                obj=data,
                type=list[schema_type],  # type: ignore[valid-type]
                from_attributes=True,
                dec_hook=partial(
                    _default_msgspec_deserializer,
                    type_decoders=DEFAULT_TYPE_DECODERS,
                ),
            )
            return cast("OffsetPagination[ModelDTOT]", _create_pagination(converted_items, filters, total))

        if PYDANTIC_INSTALLED and issubclass(schema_type, BaseModel):
            if not isinstance(data, Sequence):
                return cast(
                    "ModelDTOT",
                    get_type_adapter(schema_type).validate_python(data, from_attributes=True),
                )
            validated_items = get_type_adapter(list[schema_type]).validate_python(data, from_attributes=True)  # type: ignore[valid-type] # pyright: ignore[reportUnknownArgumentType]
            return cast("OffsetPagination[ModelDTOT]", _create_pagination(validated_items, filters, total))
        if CATTRS_INSTALLED and is_attrs_schema(schema_type):
            if not isinstance(data, Sequence):
                return cast("ModelDTOT", structure(schema_dump(data), schema_type))
            structured_items = [cast("ModelDTOT", structure(schema_dump(item), schema_type)) for item in data]
            return cast("OffsetPagination[ModelDTOT]", _create_pagination(structured_items, filters, total))

        if ATTRS_INSTALLED and is_attrs_schema(schema_type):
            # Cache field names for performance
            field_names = _get_attrs_field_names(schema_type)

            if not isinstance(data, Sequence):
                return cast("ModelDTOT", _convert_attrs_item(data, schema_type, field_names))

            converted_items = [_convert_attrs_item(item, schema_type, field_names) for item in data]
            return cast("OffsetPagination[ModelDTOT]", _create_pagination(converted_items, filters, total))

        if not MSGSPEC_INSTALLED and not PYDANTIC_INSTALLED and not ATTRS_INSTALLED:
            msg = "Either Msgspec, Pydantic, or attrs must be installed to use schema conversion"
            raise AdvancedAlchemyError(msg)

        msg = "`schema_type` should be a valid Pydantic, Msgspec, or attrs schema"
        raise AdvancedAlchemyError(msg)


# Private helper functions


def _default_msgspec_deserializer(
    target_type: Any,
    value: Any,
    type_decoders: "Union[Sequence[tuple[Callable[[Any], bool], Callable[[Any, Any], Any]]], None]" = None,
) -> Any:  # pragma: no cover
    """Transform values non-natively supported by ``msgspec``

    Args:
        target_type: Encountered type
        value: Value to coerce
        type_decoders: Optional sequence of type decoders

    Raises:
        TypeError: If the value cannot be coerced to the target type

    Returns:
        A ``msgspec``-supported type
    """

    if isinstance(value, target_type):
        return value

    if type_decoders:
        for predicate, decoder in type_decoders:
            if predicate(target_type):
                return decoder(target_type, value)

    if issubclass(target_type, (Path, PurePath, UUID)):
        return target_type(value)

    try:
        return target_type(value)
    except Exception as e:
        msg = f"Unsupported type: {type(value)!r}"
        raise TypeError(msg) from e


@lru_cache(maxsize=128)
def _get_attrs_field_names(schema_type: "type[Any]") -> "set[str]":
    """Get and cache the field names for a given attrs class.

    Args:
        schema_type: attrs class to get field names for.

    Returns:
        Set of field names for the attrs class.
    """
    if ATTRS_INSTALLED and is_attrs_schema(schema_type):
        return {field.name for field in fields(schema_type)}
    return set()


def _convert_attrs_item(item: Any, schema_type: "type[ModelDTOT]", field_names: "set[str]") -> "ModelDTOT":
    """Convert a single item to attrs schema using cached field names.

    Args:
        item: Item to convert.
        schema_type: Target attrs schema type.
        field_names: Cached set of field names.

    Returns:
        Converted attrs instance.
    """
    item_dict = schema_dump(item)
    filtered_dict = {k: v for k, v in item_dict.items() if k in field_names}
    return schema_type(**filtered_dict)  # type: ignore[return-value]


def _create_pagination(items: Any, filters: Any, total: "Optional[int]") -> "OffsetPagination[Any]":
    """Create OffsetPagination with consistent limit_offset logic.

    Args:
        items: Items to paginate.
        filters: Filters to extract LimitOffset from.
        total: Total count or None.

    Returns:
        OffsetPagination instance.
    """
    limit_offset = find_filter(LimitOffset, filters=filters) or LimitOffset(limit=len(items), offset=0)
    return OffsetPagination(
        items=items,
        limit=limit_offset.limit,
        offset=limit_offset.offset,
        total=total or len(items),
    )
