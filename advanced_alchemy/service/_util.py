"""Service object implementation for SQLAlchemy.

RepositoryService object is generic on the domain model type which
should be a SQLAlchemy model.
"""

import datetime
from collections.abc import Sequence
from enum import Enum
from functools import partial
from pathlib import Path, PurePath
from typing import TYPE_CHECKING, Any, Callable, Optional, Union, cast, overload
from uuid import UUID

from advanced_alchemy.exceptions import AdvancedAlchemyError
from advanced_alchemy.filters import LimitOffset, StatementFilter
from advanced_alchemy.repository.typing import ModelOrRowMappingT
from advanced_alchemy.service.pagination import OffsetPagination
from advanced_alchemy.service.typing import (
    MSGSPEC_INSTALLED,
    PYDANTIC_INSTALLED,
    BaseModel,
    FilterTypeT,
    ModelDTOT,
    Struct,
    convert,
    get_type_adapter,
)

if TYPE_CHECKING:
    from sqlalchemy import ColumnElement, RowMapping

    from advanced_alchemy.base import ModelProtocol

__all__ = ("ResultConverter", "find_filter")

DEFAULT_TYPE_DECODERS = [  # pyright: ignore[reportUnknownVariableType]
    (lambda x: x is UUID, lambda t, v: t(v.hex)),  # pyright: ignore[reportUnknownLambdaType,reportUnknownMemberType]
    (lambda x: x is datetime.datetime, lambda t, v: t(v.isoformat())),  # pyright: ignore[reportUnknownLambdaType,reportUnknownMemberType]
    (lambda x: x is datetime.date, lambda t, v: t(v.isoformat())),  # pyright: ignore[reportUnknownLambdaType,reportUnknownMemberType]
    (lambda x: x is datetime.time, lambda t, v: t(v.isoformat())),  # pyright: ignore[reportUnknownLambdaType,reportUnknownMemberType]
    (lambda x: x is Enum, lambda t, v: t(v.value)),  # pyright: ignore[reportUnknownLambdaType,reportUnknownMemberType]
]


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
        data: ModelOrRowMappingT,
        total: "Optional[int]" = None,
        filters: "Union[Sequence[Union[StatementFilter, ColumnElement[bool]]], Sequence[StatementFilter], None]" = None,
        *,
        schema_type: None = None,
    ) -> ModelOrRowMappingT: ...

    @overload
    def to_schema(
        self,
        data: "Sequence[ModelOrRowMappingT]",
        total: "Optional[int]" = None,
        filters: "Union[Sequence[Union[StatementFilter, ColumnElement[bool]]], Sequence[StatementFilter], None]" = None,
        *,
        schema_type: None = None,
    ) -> OffsetPagination[ModelOrRowMappingT]: ...

    @overload
    def to_schema(
        self,
        data: "Union[ModelProtocol, RowMapping]",
        total: "Optional[int]" = None,
        filters: "Union[Sequence[Union[StatementFilter, ColumnElement[bool]]], Sequence[StatementFilter], None]" = None,
        *,
        schema_type: type[ModelDTOT],
    ) -> ModelDTOT: ...

    @overload
    def to_schema(
        self,
        data: "Union[Sequence[ModelProtocol], Sequence[RowMapping]]",
        total: "Optional[int]" = None,
        filters: "Union[Sequence[Union[StatementFilter, ColumnElement[bool]]], Sequence[StatementFilter], None]" = None,
        *,
        schema_type: type[ModelDTOT],
    ) -> "OffsetPagination[ModelDTOT]": ...

    def to_schema(
        self,
        data: "Union[ModelOrRowMappingT, Sequence[ModelOrRowMappingT], ModelProtocol, Sequence[ModelProtocol], RowMapping, Sequence[RowMapping]]",
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
        Returns:
            - :class:`~advanced_alchemy.base.ModelProtocol` | :class:`sqlalchemy.orm.RowMapping` | :class:`~advanced_alchemy.service.pagination.OffsetPagination` | :class:`msgspec.Struct` | :class:`pydantic.BaseModel`
        """
        if filters is None:
            filters = []
        if schema_type is None:
            if not isinstance(data, Sequence):
                return cast("ModelOrRowMappingT", data)  # type: ignore[unreachable,unused-ignore]
            limit_offset = find_filter(LimitOffset, filters=filters)
            total = total or len(data)
            limit_offset = limit_offset if limit_offset is not None else LimitOffset(limit=len(data), offset=0)
            return OffsetPagination[ModelOrRowMappingT](
                items=cast("Sequence[ModelOrRowMappingT]", data),
                limit=limit_offset.limit,
                offset=limit_offset.offset,
                total=total,
            )
        if MSGSPEC_INSTALLED and issubclass(schema_type, Struct):
            if not isinstance(data, Sequence):
                return cast(
                    "ModelDTOT",
                    convert(
                        obj=data,
                        type=schema_type,
                        from_attributes=True,
                        dec_hook=partial(
                            _default_msgspec_deserializer,
                            type_decoders=DEFAULT_TYPE_DECODERS,
                        ),
                    ),
                )
            limit_offset = find_filter(LimitOffset, filters=filters)
            total = total or len(data)
            limit_offset = limit_offset if limit_offset is not None else LimitOffset(limit=len(data), offset=0)
            return OffsetPagination[ModelDTOT](
                items=convert(
                    obj=data,
                    type=list[schema_type],  # type: ignore[valid-type]
                    from_attributes=True,
                    dec_hook=partial(
                        _default_msgspec_deserializer,
                        type_decoders=DEFAULT_TYPE_DECODERS,
                    ),
                ),
                limit=limit_offset.limit,
                offset=limit_offset.offset,
                total=total,
            )

        if PYDANTIC_INSTALLED and issubclass(schema_type, BaseModel):
            if not isinstance(data, Sequence):
                return cast(
                    "ModelDTOT",
                    get_type_adapter(schema_type).validate_python(data, from_attributes=True),
                )
            limit_offset = find_filter(LimitOffset, filters=filters)
            total = total if total else len(data)
            limit_offset = limit_offset if limit_offset is not None else LimitOffset(limit=len(data), offset=0)
            return OffsetPagination[ModelDTOT](
                items=get_type_adapter(list[schema_type]).validate_python(data, from_attributes=True),  # type: ignore[valid-type] # pyright: ignore[reportUnknownArgumentType]
                limit=limit_offset.limit,
                offset=limit_offset.offset,
                total=total,
            )

        if not MSGSPEC_INSTALLED and not PYDANTIC_INSTALLED:
            msg = "Either Msgspec or Pydantic must be installed to use schema conversion"
            raise AdvancedAlchemyError(msg)

        msg = "`schema_type` should be a valid Pydantic or Msgspec schema"
        raise AdvancedAlchemyError(msg)
