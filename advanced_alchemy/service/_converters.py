from __future__ import annotations

from functools import partial
from pathlib import Path, PurePath
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Sequence,
    cast,
)
from uuid import UUID

from advanced_alchemy.filters import FilterTypes, LimitOffset
from advanced_alchemy.repository.typing import ModelT
from advanced_alchemy.service.pagination import OffsetPagination

if TYPE_CHECKING:
    from sqlalchemy import ColumnElement, RowMapping

    from advanced_alchemy.service.typing import FilterTypeT, ModelDTOT

try:
    from msgspec import Struct, convert
except ImportError:  # pragma: nocover

    class Struct:  # type: ignore[no-redef]
        """Placeholder Implementation"""

    def convert(*args: Any, **kwargs: Any) -> Any:  # type: ignore[no-redef] # noqa: ARG001
        """Placeholder implementation"""
        return {}


try:
    from pydantic import BaseModel
    from pydantic.type_adapter import TypeAdapter
except ImportError:  # pragma: nocover

    class BaseModel:  # type: ignore[no-redef]
        """Placeholder Implementation"""

    class TypeAdapter:  # type: ignore[no-redef]
        """Placeholder Implementation"""


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
    *filters: FilterTypes | ColumnElement[bool],
) -> FilterTypeT | None:
    """Get the filter specified by filter type from the filters.

    Args:
        filter_type: The type of filter to find.
        *filters: filter types to apply to the query

    Returns:
        The match filter instance or None
    """
    return next(
        (cast("FilterTypeT | None", filter_) for filter_ in filters if isinstance(filter_, filter_type)),
        None,
    )


def to_schema(
    dto: type[ModelT | ModelDTOT],
    data: ModelT | Sequence[ModelT] | list[RowMapping] | RowMapping,
    total: int | None = None,
    *filters: FilterTypes,
) -> ModelT | OffsetPagination[ModelT] | ModelDTOT | OffsetPagination[ModelDTOT]:

    if issubclass(dto, Struct):
        if not isinstance(data, Sequence | list):
            return convert(  # type: ignore  # noqa: PGH003
                obj=data,
                type=dto,
                from_attributes=True,
                dec_hook=partial(
                    _default_deserializer,
                    type_decoders=[
                        (lambda x: x is UUID, lambda t, v: t(v.hex)),
                    ],
                ),
            )
        limit_offset = _find_filter(LimitOffset, *filters)
        total = total or len(data)
        limit_offset = limit_offset if limit_offset is not None else LimitOffset(limit=len(data), offset=0)
        return OffsetPagination[dto](  # type: ignore[valid-type]
            items=convert(
                obj=data,
                type=list[dto],  # type: ignore[valid-type]
                from_attributes=True,
                dec_hook=partial(
                    _default_deserializer,
                    type_decoders=[
                        (lambda x: x is UUID, lambda t, v: t(v.hex)),
                    ],
                ),
            ),
            limit=limit_offset.limit,
            offset=limit_offset.offset,
            total=total,
        )

    if issubclass(dto, BaseModel):
        if not isinstance(data, Sequence | list):
            return TypeAdapter(dto).validate_python(data)  # type: ignore  # noqa: PGH003
        limit_offset = _find_filter(LimitOffset, *filters)
        total = total if total else len(data)
        limit_offset = limit_offset if limit_offset is not None else LimitOffset(limit=len(data), offset=0)
        return OffsetPagination[dto](  # type: ignore[valid-type]
            items=TypeAdapter(list[dto]).validate_python(data),  # type: ignore[valid-type]
            limit=limit_offset.limit,
            offset=limit_offset.offset,
            total=total,
        )
    if not isinstance(data, Sequence | list):
        return cast("ModelT", data)
    limit_offset = _find_filter(LimitOffset, *filters)
    total = total or len(data)
    limit_offset = limit_offset if limit_offset is not None else LimitOffset(limit=len(data), offset=0)
    return OffsetPagination[ModelT](
        items=cast("list[ModelT]", data),
        limit=limit_offset.limit,
        offset=limit_offset.offset,
        total=total,
    )
