from __future__ import annotations

from functools import partial
from pathlib import Path, PurePath
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Generic,
    Sequence,
    TypeVar,
    cast,
)
from uuid import UUID

from advanced_alchemy.exceptions import AdvancedAlchemyError
from advanced_alchemy.filters import LimitOffset, StatementFilter
from advanced_alchemy.repository.typing import ModelOrRowMappingT
from advanced_alchemy.service.pagination import OffsetPagination
from advanced_alchemy.service.typing import PydanticModelDTOT, StructModelDTOT

if TYPE_CHECKING:
    from sqlalchemy import ColumnElement

    from advanced_alchemy.base import ModelProtocol
    from advanced_alchemy.service.typing import FilterTypeT

try:
    from msgspec import Struct, convert  # pyright: ignore[reportAssignmentType]
except ImportError:  # pragma: nocover

    class Struct:  # type: ignore[no-redef] # pragma: nocover
        """Placeholder Implementation"""

    def convert(*args: Any, **kwargs: Any) -> Any:  # type: ignore[no-redef] # noqa: ARG001 # pragma: nocover
        """Placeholder implementation"""
        return {}


try:
    from pydantic import BaseModel  # pyright: ignore[reportAssignmentType]
    from pydantic.type_adapter import TypeAdapter  # pyright: ignore[reportAssignmentType]
except ImportError:  # pragma: nocover

    class BaseModel:  # type: ignore[no-redef] # pragma: nocover
        """Placeholder Implementation"""

    T = TypeVar("T")  # pragma: nocover

    class TypeAdapter(Generic[T]):  # type: ignore[no-redef] # pragma: nocover
        """Placeholder Implementation"""

        def __init__(self, *args: Any, **kwargs: Any) -> None:  # pragma: nocover
            super().__init__()

        def validate_python(self, data: Any, *args: Any, **kwargs: Any) -> T:  # pragma: nocover
            """Stub"""
            return cast("T", data)


def _default_deserializer(
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


def _find_filter(
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


def to_schema(
    data: ModelOrRowMappingT | Sequence[ModelOrRowMappingT] | ModelProtocol | Sequence[ModelProtocol],
    total: int | None = None,
    filters: Sequence[StatementFilter | ColumnElement[bool]] | Sequence[StatementFilter] | None = None,
    schema_type: type[PydanticModelDTOT | StructModelDTOT] | None = None,
) -> (
    ModelOrRowMappingT
    | OffsetPagination[ModelOrRowMappingT]
    | StructModelDTOT
    | OffsetPagination[StructModelDTOT]
    | PydanticModelDTOT
    | OffsetPagination[PydanticModelDTOT]
):
    if filters is None:
        filters = []
    if schema_type is None:
        if not issubclass(type(data), Sequence):
            return cast("ModelOrRowMappingT", data)
        limit_offset = _find_filter(LimitOffset, filters=filters)
        total = total or len(data)  # type: ignore[arg-type]
        limit_offset = limit_offset if limit_offset is not None else LimitOffset(limit=len(data), offset=0)  # type: ignore[arg-type]
        return OffsetPagination[ModelOrRowMappingT](
            items=cast("Sequence[ModelOrRowMappingT]", data),
            limit=limit_offset.limit,
            offset=limit_offset.offset,
            total=total,
        )
    if issubclass(schema_type, Struct):
        if not isinstance(data, Sequence):
            return cast(
                "StructModelDTOT",
                convert(
                    obj=data,
                    type=schema_type,
                    from_attributes=True,
                    dec_hook=partial(
                        _default_deserializer,
                        type_decoders=[
                            (lambda x: x is UUID, lambda t, v: t(v.hex)),
                        ],
                    ),
                ),
            )
        limit_offset = _find_filter(LimitOffset, filters=filters)
        total = total or len(data)
        limit_offset = limit_offset if limit_offset is not None else LimitOffset(limit=len(data), offset=0)
        return OffsetPagination[StructModelDTOT](
            items=cast(
                "Sequence[StructModelDTOT]",
                convert(
                    obj=data,
                    type=Sequence[StructModelDTOT],
                    from_attributes=True,
                    dec_hook=partial(
                        _default_deserializer,
                        type_decoders=[
                            (lambda x: x is UUID, lambda t, v: t(v.hex)),
                        ],
                    ),
                ),
            ),
            limit=limit_offset.limit,
            offset=limit_offset.offset,
            total=total,
        )

    if issubclass(schema_type, BaseModel):
        if not isinstance(data, Sequence):
            return TypeAdapter(schema_type).validate_python(data, from_attributes=True)  # pyright: ignore[reportUnknownVariableType,reportUnknownMemberType,reportAttributeAccessIssue,reportCallIssue]
        limit_offset = _find_filter(LimitOffset, filters=filters)
        total = total if total else len(data)
        limit_offset = limit_offset if limit_offset is not None else LimitOffset(limit=len(data), offset=0)
        return OffsetPagination[PydanticModelDTOT](
            items=TypeAdapter(Sequence[PydanticModelDTOT]).validate_python(data, from_attributes=True),  # pyright: ignore[reportUnknownArgumentType]
            limit=limit_offset.limit,
            offset=limit_offset.offset,
            total=total,
        )
    msg = "`schema_type` should be a valid Pydantic or Msgspec schema"  # type: ignore[unreachable]
    raise AdvancedAlchemyError(msg)
