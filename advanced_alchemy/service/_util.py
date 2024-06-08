"""Service object implementation for SQLAlchemy.

RepositoryService object is generic on the domain model type which
should be a SQLAlchemy model.
"""

from __future__ import annotations

from functools import partial
from pathlib import Path, PurePath
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Sequence,
    cast,
    overload,
)
from uuid import UUID

from sqlalchemy import RowMapping

from advanced_alchemy.base import ModelProtocol
from advanced_alchemy.exceptions import AdvancedAlchemyError
from advanced_alchemy.filters import LimitOffset
from advanced_alchemy.service.pagination import OffsetPagination
from advanced_alchemy.service.typing import (  # type: ignore[attr-defined]
    BaseModel,
    ModelDTOT,
    ModelT,
    Struct,
    TypeAdapter,
    convert,
)

if TYPE_CHECKING:
    from sqlalchemy import ColumnElement

    from advanced_alchemy.filters import StatementFilter
    from advanced_alchemy.repository.typing import ModelOrRowMappingT
    from advanced_alchemy.service.typing import FilterTypeT


def _default_msgspec_deserializer(
    target_type: Any,
    value: Any,
    type_decoders: Sequence[tuple[Callable[[Any], bool], Callable[[Any, Any], Any]]] | None = None,
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

    msg = f"Unsupported type: {type(value)!r}"
    raise TypeError(msg)


def find_filter(
    filter_type: type[FilterTypeT],
    filters: Sequence[StatementFilter | ColumnElement[bool]] | Sequence[StatementFilter],
) -> FilterTypeT | None:
    """Get the filter specified by filter type from the filters.

    Args:
        filter_type: The type of filter to find.
        filters: filter types to apply to the query

    Returns:
        The match filter instance or None
    """
    return next(
        (cast("FilterTypeT | None", filter_) for filter_ in filters if isinstance(filter_, filter_type)),
        None,
    )


class ModelResultConverter:
    """Simple mixin to help convert to a paginated response model the results set is a list."""

    @overload
    def to_schema(
        self,
        data: ModelOrRowMappingT,
        total: int | None = None,
        filters: Sequence[StatementFilter | ColumnElement[bool]] | Sequence[StatementFilter] | None = None,
        *,
        schema_type: None = None,
    ) -> ModelOrRowMappingT: ...

    @overload
    def to_schema(
        self,
        data: Sequence[ModelOrRowMappingT],
        total: int | None = None,
        filters: Sequence[StatementFilter | ColumnElement[bool]] | Sequence[StatementFilter] | None = None,
        *,
        schema_type: None = None,
    ) -> OffsetPagination[ModelOrRowMappingT]: ...

    @overload
    def to_schema(
        self,
        data: ModelProtocol,
        total: int | None = None,
        filters: Sequence[StatementFilter | ColumnElement[bool]] | Sequence[StatementFilter] | None = None,
        *,
        schema_type: type[ModelDTOT],
    ) -> ModelDTOT: ...

    @overload
    def to_schema(
        self,
        data: Sequence[ModelProtocol],
        total: int | None = None,
        filters: Sequence[StatementFilter | ColumnElement[bool]] | Sequence[StatementFilter] | None = None,
        *,
        schema_type: type[ModelDTOT],
    ) -> OffsetPagination[ModelDTOT]: ...

    def to_schema(
        self,
        data: ModelT | Sequence[ModelT] | ModelProtocol | Sequence[ModelProtocol],
        total: int | None = None,
        filters: Sequence[StatementFilter | ColumnElement[bool]] | Sequence[StatementFilter] | None = None,
        *,
        schema_type: type[ModelDTOT] | None = None,
    ) -> ModelT | OffsetPagination[ModelT] | ModelDTOT | OffsetPagination[ModelDTOT]:
        """Convert the object to a response schema.  When `schema_type` is None, the model is returned with no conversion.

        Args:
            data: The return from one of the service calls.
            total: the total number of rows in the data
            filters: Collection route filters.
            schema_type: Collection route filters.

        Returns:
            The list of instances retrieved from the repository.
        """
        if filters is None:
            filters = []
        if schema_type is None:
            if not isinstance(data, Sequence):
                return cast("ModelT", data)
            limit_offset = find_filter(LimitOffset, filters=filters)
            total = total or len(data)
            limit_offset = limit_offset if limit_offset is not None else LimitOffset(limit=len(data), offset=0)
            return OffsetPagination[ModelT](
                items=cast("Sequence[ModelT]", data),
                limit=limit_offset.limit,
                offset=limit_offset.offset,
                total=total,
            )
        if issubclass(schema_type, Struct):
            if not isinstance(data, Sequence):
                return cast(
                    "ModelDTOT",
                    convert(
                        obj=data,
                        type=schema_type,
                        from_attributes=True,
                        dec_hook=partial(
                            _default_msgspec_deserializer,
                            type_decoders=[
                                (lambda x: x is UUID, lambda t, v: t(v.hex)),
                            ],
                        ),
                    ),
                )
            limit_offset = find_filter(LimitOffset, filters=filters)
            total = total or len(data)
            limit_offset = limit_offset if limit_offset is not None else LimitOffset(limit=len(data), offset=0)
            return OffsetPagination[ModelDTOT](
                items=convert(
                    obj=data,
                    type=Sequence[schema_type],
                    from_attributes=True,
                    dec_hook=partial(
                        _default_msgspec_deserializer,
                        type_decoders=[
                            (lambda x: x is UUID, lambda t, v: t(v.hex)),
                        ],
                    ),
                ),
                limit=limit_offset.limit,
                offset=limit_offset.offset,
                total=total,
            )

        if issubclass(schema_type, BaseModel):
            if not isinstance(data, Sequence):
                return cast("ModelDTOT", TypeAdapter(schema_type).validate_python(data, from_attributes=True))  # pyright: ignore[reportUnknownVariableType,reportUnknownMemberType,reportAttributeAccessIssue,reportCallIssue]
            limit_offset = find_filter(LimitOffset, filters=filters)
            total = total if total else len(data)
            limit_offset = limit_offset if limit_offset is not None else LimitOffset(limit=len(data), offset=0)
            return OffsetPagination[ModelDTOT](
                items=TypeAdapter(Sequence[schema_type]).validate_python(data, from_attributes=True),  # pyright: ignore[reportUnknownArgumentType]
                limit=limit_offset.limit,
                offset=limit_offset.offset,
                total=total,
            )
        msg = "`schema_type` should be a valid Pydantic or Msgspec schema"
        raise AdvancedAlchemyError(msg)


class RowMappingResultConverter:  # pragma: nocover
    """Simple mixin to help convert to a paginated response model the results set is a list."""

    @overload
    def to_schema(
        self,
        data: RowMapping,
        total: int | None = None,
        filters: Sequence[StatementFilter | ColumnElement[bool]] | Sequence[StatementFilter] | None = None,
    ) -> RowMapping: ...

    @overload
    def to_schema(
        self,
        data: Sequence[RowMapping],
        total: int | None = None,
        filters: Sequence[StatementFilter | ColumnElement[bool]] | Sequence[StatementFilter] | None = None,
    ) -> OffsetPagination[RowMapping]: ...
    @overload
    def to_schema(
        self,
        data: RowMapping,
        total: int | None = None,
        filters: Sequence[StatementFilter | ColumnElement[bool]] | Sequence[StatementFilter] | None = None,
        *,
        schema_type: None = None,
    ) -> RowMapping: ...

    @overload
    def to_schema(
        self,
        data: Sequence[RowMapping],
        total: int | None = None,
        filters: Sequence[StatementFilter | ColumnElement[bool]] | Sequence[StatementFilter] | None = None,
        *,
        schema_type: None = None,
    ) -> OffsetPagination[RowMapping]: ...

    @overload
    def to_schema(
        self,
        data: RowMapping,
        total: int | None = None,
        filters: Sequence[StatementFilter | ColumnElement[bool]] | Sequence[StatementFilter] | None = None,
        *,
        schema_type: type[ModelDTOT],
    ) -> ModelDTOT: ...

    @overload
    def to_schema(
        self,
        data: Sequence[RowMapping],
        total: int | None = None,
        filters: Sequence[StatementFilter | ColumnElement[bool]] | Sequence[StatementFilter] | None = None,
        *,
        schema_type: type[ModelDTOT],
    ) -> OffsetPagination[ModelDTOT]: ...

    def to_schema(
        self,
        data: RowMapping | Sequence[RowMapping],
        total: int | None = None,
        filters: Sequence[StatementFilter | ColumnElement[bool]] | Sequence[StatementFilter] | None = None,
        *,
        schema_type: type[ModelDTOT] | None = None,
    ) -> RowMapping | OffsetPagination[RowMapping] | ModelDTOT | OffsetPagination[ModelDTOT]:
        """Convert the object to a response schema.  When `schema_type` is None, the model is returned with no conversion.

        Args:
            data: The return from one of the service calls.
            total: the total number of rows in the data
            filters: Collection route filters.
            schema_type: Collection route filters.

        Returns:
            The list of instances retrieved from the repository.
        """
        if filters is None:
            filters = []
        if schema_type is None:
            if isinstance(data, RowMapping):
                return data
            limit_offset = find_filter(LimitOffset, filters=filters)
            total = total or len(data)
            limit_offset = limit_offset if limit_offset is not None else LimitOffset(limit=len(data), offset=0)
            return OffsetPagination[RowMapping](
                items=data,
                limit=limit_offset.limit,
                offset=limit_offset.offset,
                total=total,
            )
        if issubclass(schema_type, Struct):
            if isinstance(data, RowMapping):
                return cast(
                    "ModelDTOT",
                    convert(
                        obj=data,
                        type=schema_type,
                        from_attributes=True,
                        dec_hook=partial(
                            _default_msgspec_deserializer,
                            type_decoders=[
                                (lambda x: x is UUID, lambda t, v: t(v.hex)),
                            ],
                        ),
                    ),
                )
            limit_offset = find_filter(LimitOffset, filters=filters)
            total = total or len(data)
            limit_offset = limit_offset if limit_offset is not None else LimitOffset(limit=len(data), offset=0)
            return OffsetPagination[ModelDTOT](
                items=convert(
                    obj=data,
                    type=Sequence[ModelDTOT],
                    from_attributes=True,
                    dec_hook=partial(
                        _default_msgspec_deserializer,
                        type_decoders=[
                            (lambda x: x is UUID, lambda t, v: t(v.hex)),
                        ],
                    ),
                ),
                limit=limit_offset.limit,
                offset=limit_offset.offset,
                total=total,
            )

        if issubclass(schema_type, BaseModel):
            if isinstance(data, RowMapping):
                return cast("ModelDTOT", TypeAdapter(schema_type).validate_python(data, from_attributes=True))  # pyright: ignore[reportUnknownVariableType,reportUnknownMemberType,reportAttributeAccessIssue,reportCallIssue]
            limit_offset = find_filter(LimitOffset, filters=filters)
            total = total if total else len(data)
            limit_offset = limit_offset if limit_offset is not None else LimitOffset(limit=len(data), offset=0)
            return OffsetPagination[ModelDTOT](
                items=TypeAdapter(Sequence[ModelDTOT]).validate_python(data, from_attributes=True),  # pyright: ignore[reportUnknownArgumentType]
                limit=limit_offset.limit,
                offset=limit_offset.offset,
                total=total,
            )
        msg = "`schema_type` should be a valid Pydantic or Msgspec schema"
        raise AdvancedAlchemyError(msg)
