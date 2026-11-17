"""Service object implementation for SQLAlchemy.

RepositoryService object is generic on the domain model type which
should be a SQLAlchemy model.
"""

import datetime as dt
from collections.abc import Sequence
from decimal import Decimal
from enum import Enum
from functools import lru_cache, partial
from pathlib import Path, PurePath
from typing import TYPE_CHECKING, Any, Callable, Literal, Optional, Union, cast, get_args, get_origin, overload
from uuid import UUID

from advanced_alchemy.exceptions import AdvancedAlchemyError, ImproperConfigurationError
from advanced_alchemy.filters import CursorFilter, LimitOffsetFilter, StatementFilter
from advanced_alchemy.repository._util import (
    ModelRepositoryMixin,
    is_mapped_model_class,
    resolve_generic_type_args,
)
from advanced_alchemy.repository.typing import PrimaryKeyType
from advanced_alchemy.service.pagination import CursorPagination, OffsetPagination
from advanced_alchemy.typing import (
    ATTRS_INSTALLED,
    CATTRS_INSTALLED,
    MSGSPEC_INSTALLED,
    PYDANTIC_INSTALLED,
    CattrsStructureHandlerNotFoundError,
    cattrs_global_converter,
)
from advanced_alchemy.utils.serialization import (
    BaseModel,
    FilterTypeT,
    ModelDTOT,
    Struct,
    convert,
    fields,
    get_type_adapter,
    is_attrs_schema,
    schema_dump,
)

if TYPE_CHECKING:
    from sqlalchemy import ColumnElement, RowMapping
    from sqlalchemy.engine.row import Row

    from advanced_alchemy.base import ModelProtocol
    from advanced_alchemy.repository.typing import ModelOrRowMappingT

__all__ = ("ResultConverter", "configure_service_subclass", "find_filter", "resolve_item_ids")

DEFAULT_TYPE_DECODERS = [  # pyright: ignore[reportUnknownVariableType]
    (lambda x: x is UUID, lambda t, v: t(v.hex)),  # pyright: ignore[reportUnknownLambdaType,reportUnknownMemberType]
    (lambda x: x is dt.datetime, lambda t, v: t(v.isoformat())),  # pyright: ignore[reportUnknownLambdaType,reportUnknownMemberType]
    (lambda x: x is dt.date, lambda t, v: t(v.isoformat())),  # pyright: ignore[reportUnknownLambdaType,reportUnknownMemberType]
    (lambda x: x is dt.time, lambda t, v: t(v.isoformat())),  # pyright: ignore[reportUnknownLambdaType,reportUnknownMemberType]
    (lambda x: x is Enum, lambda t, v: t(v.value)),  # pyright: ignore[reportUnknownLambdaType,reportUnknownMemberType]
]


def configure_service_subclass(cls: type[Any], service_base: type[Any], default_repo_base: type[Any]) -> None:
    """Resolve and attach generic model and repository types on a service subclass."""
    args = resolve_generic_type_args(cls, service_base)
    model_cls: Optional[type[Any]] = (
        args[0] if len(args) >= 1 and is_mapped_model_class(args[0]) else getattr(cls, "_model_type", None)
    )
    raw_repo = args[1] if len(args) > 1 else None
    origin_repo = get_origin(raw_repo)
    candidate_repo: Any = origin_repo if isinstance(origin_repo, type) else raw_repo
    repo_cls = (
        cast("type[Any]", candidate_repo)
        if isinstance(candidate_repo, type) and issubclass(candidate_repo, ModelRepositoryMixin)
        else None
    )
    if model_cls is None and repo_cls is not None:
        repo_args = get_args(raw_repo)
        model_cls = (
            repo_args[0] if repo_args and is_mapped_model_class(repo_args[0]) else getattr(repo_cls, "model_type", None)
        )
    if model_cls is not None and "_model_type" not in cls.__dict__:
        cls._model_type = model_cls
    if getattr(cls, "repository_type", None) is not None:
        return
    if repo_cls is not None:
        if getattr(repo_cls, "model_type", None) is not None or model_cls is None:
            cls.repository_type = repo_cls
        else:
            cls.repository_type = type(
                f"{model_cls.__name__}{repo_cls.__name__}",
                (repo_cls,),
                {
                    "model_type": model_cls,
                    "__module__": cls.__module__,
                    "__qualname__": f"{cls.__qualname__}.{model_cls.__name__}{repo_cls.__name__}",
                },
            )
    elif model_cls is not None:
        cls.repository_type = type(
            f"{model_cls.__name__}Repository",
            (default_repo_base,),
            {
                "model_type": model_cls,
                "__module__": cls.__module__,
                "__qualname__": f"{cls.__qualname__}.{model_cls.__name__}Repository",
            },
        )


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
    from advanced_alchemy.filters import FilterSet

    for filter_ in filters:
        if isinstance(filter_, filter_type):
            return filter_
        if isinstance(filter_, FilterSet):
            nested = find_filter(filter_type, filter_.to_statement_filters())
            if nested is not None:
                return nested
    return None


def resolve_item_ids(
    item_ids: list[PrimaryKeyType],
    *,
    model_type: type[Any],
    repository: Any,
    id_attribute: Any = None,
) -> list[PrimaryKeyType]:
    """Resolve model instances in ``item_ids`` without copying id-only input."""
    resolved_item_ids: Optional[list[PrimaryKeyType]] = None
    for index, item in enumerate(item_ids):
        if isinstance(item, model_type):
            if resolved_item_ids is None:
                resolved_item_ids = item_ids[:index]
            if repository.has_composite_pk:
                resolved_item_ids.append(repository.get_primary_key_value(item))
            else:
                resolved_item_ids.append(repository.get_id_attribute_value(item=item, id_attribute=id_attribute))
        elif resolved_item_ids is not None:
            resolved_item_ids.append(item)
    return item_ids if resolved_item_ids is None else resolved_item_ids


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
        data: "Sequence[Row[Any]]",
        total: "int",
    ) -> "OffsetPagination[Row[Any]]": ...

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

    @overload
    def to_schema(
        self,
        data: "Sequence[ModelOrRowMappingT]",
        total: "Optional[int]" = None,
        filters: "Union[Sequence[Union[StatementFilter, ColumnElement[bool]]], Sequence[StatementFilter], None]" = None,
        *,
        schema_type: None = None,
        pagination_type: 'Literal["cursor"]',
    ) -> "CursorPagination[ModelOrRowMappingT]": ...

    @overload
    def to_schema(
        self,
        data: "Union[Sequence[ModelProtocol], Sequence[RowMapping], Sequence[Row[Any]], Sequence[dict[str, Any]]]",
        total: "Optional[int]" = None,
        filters: "Union[Sequence[Union[StatementFilter, ColumnElement[bool]]], Sequence[StatementFilter], None]" = None,
        *,
        schema_type: "type[ModelDTOT]",
        pagination_type: 'Literal["cursor"]',
    ) -> "CursorPagination[ModelDTOT]": ...

    @overload
    def to_schema(
        self,
        data: "Sequence[ModelOrRowMappingT]",
        total: "Optional[int]" = None,
        filters: "Union[Sequence[Union[StatementFilter, ColumnElement[bool]]], Sequence[StatementFilter], None]" = None,
        *,
        schema_type: None = None,
        pagination_type: 'Literal["limit_offset"]',
    ) -> "OffsetPagination[ModelOrRowMappingT]": ...

    @overload
    def to_schema(
        self,
        data: "Union[Sequence[ModelProtocol], Sequence[RowMapping], Sequence[Row[Any]], Sequence[dict[str, Any]]]",
        total: "Optional[int]" = None,
        filters: "Union[Sequence[Union[StatementFilter, ColumnElement[bool]]], Sequence[StatementFilter], None]" = None,
        *,
        schema_type: "type[ModelDTOT]",
        pagination_type: 'Literal["limit_offset"]',
    ) -> "OffsetPagination[ModelDTOT]": ...

    def to_schema(
        self,
        data: "Union[ModelOrRowMappingT, Sequence[ModelOrRowMappingT], ModelProtocol, Sequence[ModelProtocol], RowMapping, Sequence[RowMapping], Row[Any], Sequence[Row[Any]], dict[str, Any], Sequence[dict[str, Any]]]",
        total: "Optional[int]" = None,
        filters: "Union[Sequence[Union[StatementFilter, ColumnElement[bool]]], Sequence[StatementFilter], None]" = None,
        *,
        schema_type: "Optional[type[ModelDTOT]]" = None,
        pagination_type: 'Optional[Literal["limit_offset", "cursor"]]' = None,
    ) -> "Union[ModelOrRowMappingT, OffsetPagination[ModelOrRowMappingT], ModelDTOT, OffsetPagination[ModelDTOT], CursorPagination[ModelOrRowMappingT], CursorPagination[ModelDTOT], OffsetPagination[Row[Any]]]":
        """Convert the object to a response schema.

        When `schema_type` is None, the model is returned with no conversion.

        Args:
            data: The return from one of the service calls.
              Type: :class:`~advanced_alchemy.repository.typing.ModelOrRowMappingT`
            total: The total number of rows in the data.
            filters: :class:`~advanced_alchemy.filters.StatementFilter` | :class:`~sqlalchemy.sql.expression.ColumnElement` collection of route filters.
            schema_type: :class:`~advanced_alchemy.utils.serialization.ModelDTOT` Optional schema type to convert the data to
            pagination_type: Pagination container to build. Omitted, a :class:`~advanced_alchemy.filters.CursorFilter`
                in ``filters`` returns a :class:`~advanced_alchemy.service.pagination.CursorPagination` and anything
                else an :class:`~advanced_alchemy.service.pagination.OffsetPagination`. ``"cursor"`` and
                ``"limit_offset"`` require that container and give type checkers its exact type; ``total`` is
                ignored for cursor pages.

        Raises:
            AdvancedAlchemyError: If `schema_type` is not a valid Pydantic, Msgspec, or attrs schema and all libraries are not installed.
            ImproperConfigurationError: If ``pagination_type`` does not match the pagination filter in ``filters``.

        Returns:
            :class:`~advanced_alchemy.base.ModelProtocol` | :class:`~sqlalchemy.engine.RowMapping` | :class:`~advanced_alchemy.service.pagination.OffsetPagination` | :class:`msgspec.Struct` | :class:`pydantic.BaseModel` | ``attrs`` class
        """
        if filters is None:
            filters = []
        cursor_page = self._to_cursor_page(data, filters, schema_type, pagination_type)
        if cursor_page is not None:
            return cursor_page
        if schema_type is None:
            if not isinstance(data, Sequence):
                return cast("ModelOrRowMappingT", data)  # type: ignore[unreachable,unused-ignore]
            return cast(
                "OffsetPagination[ModelOrRowMappingT]",
                _create_pagination(cast("Sequence[ModelOrRowMappingT]", data), filters, total),
            )
        if MSGSPEC_INSTALLED and issubclass(schema_type, Struct):
            if not isinstance(data, Sequence):
                return cast(
                    "ModelDTOT",
                    convert(
                        obj=data,
                        type=schema_type,
                        from_attributes=True,
                        dec_hook=_DEFAULT_MSGSPEC_DEC_HOOK,
                    ),
                )
            converted_items = convert(
                obj=data,
                type=_get_list_schema_type(schema_type),
                from_attributes=True,
                dec_hook=_DEFAULT_MSGSPEC_DEC_HOOK,
            )
            return cast("OffsetPagination[ModelDTOT]", _create_pagination(converted_items, filters, total))

        if PYDANTIC_INSTALLED and issubclass(schema_type, BaseModel):
            if not isinstance(data, Sequence):
                return cast(
                    "ModelDTOT",
                    get_type_adapter(schema_type).validate_python(data, from_attributes=True),
                )
            validated_items = get_type_adapter(_get_list_schema_type(schema_type)).validate_python(
                data, from_attributes=True
            )
            return cast("OffsetPagination[ModelDTOT]", _create_pagination(validated_items, filters, total))
        if CATTRS_INSTALLED and is_attrs_schema(schema_type):
            cattrs_converter = _get_cattrs_converter()
            if not isinstance(data, Sequence):
                return cast("ModelDTOT", cattrs_converter.structure(schema_dump(data), schema_type))
            structured_items = cattrs_converter.structure(
                [schema_dump(item) for item in data], _get_list_schema_type(cast("Any", schema_type))
            )
            return cast("OffsetPagination[ModelDTOT]", _create_pagination(structured_items, filters, total))

        if ATTRS_INSTALLED and is_attrs_schema(schema_type):
            field_names = _get_attrs_field_names(schema_type)  # type: ignore[arg-type]

            if not isinstance(data, Sequence):
                return cast("ModelDTOT", _convert_attrs_item(data, schema_type, field_names))

            converted_items = [_convert_attrs_item(item, schema_type, field_names) for item in data]
            return cast("OffsetPagination[ModelDTOT]", _create_pagination(converted_items, filters, total))

        if not MSGSPEC_INSTALLED and not PYDANTIC_INSTALLED and not ATTRS_INSTALLED:
            msg = "Either Msgspec, Pydantic, or attrs must be installed to use schema conversion"
            raise AdvancedAlchemyError(msg)

        msg = "`schema_type` should be a valid Pydantic, Msgspec, or attrs schema"
        raise AdvancedAlchemyError(msg)

    def _to_cursor_page(
        self,
        data: Any,
        filters: "Union[Sequence[Union[StatementFilter, ColumnElement[bool]]], Sequence[StatementFilter]]",
        schema_type: "Optional[type[ModelDTOT]]",
        pagination_type: 'Optional[Literal["limit_offset", "cursor"]]',
    ) -> "Optional[CursorPagination[Any]]":
        """Build a cursor page when ``filters`` hold a :class:`CursorFilter`; reject mismatched pagination."""
        cursor_filter = find_filter(CursorFilter, filters)
        if pagination_type == "cursor":
            if cursor_filter is None:
                msg = 'pagination_type="cursor" requires a CursorFilter in filters'
                raise ImproperConfigurationError(msg)
            if not isinstance(data, Sequence):
                msg = 'pagination_type="cursor" requires a sequence of rows'
                raise ImproperConfigurationError(msg)
        elif cursor_filter is None or not isinstance(data, Sequence):
            return None
        elif pagination_type == "limit_offset":
            msg = 'filters contain a CursorFilter; pagination_type="limit_offset" cannot page its rows'
            raise ImproperConfigurationError(msg)
        rows = cast("Sequence[Any]", data)  # type: ignore[redundant-cast]
        page = cursor_filter.build_page(rows, model=getattr(self, "model_type", None))
        items: Sequence[Any] = (
            page.items if schema_type is None else self.to_schema(list(page.items), schema_type=schema_type).items
        )
        return CursorPagination(
            items=items,
            limit=page.limit,
            next_cursor=page.next_cursor,
            previous_cursor=page.previous_cursor,
            has_next=page.has_next,
            has_previous=page.has_previous,
        )


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


_DEFAULT_MSGSPEC_DEC_HOOK = partial(
    _default_msgspec_deserializer,
    type_decoders=DEFAULT_TYPE_DECODERS,
)


_CATTRS_SCALAR_TYPES: "tuple[type[Any], ...]" = (UUID, dt.datetime, dt.date, dt.time, dt.timedelta, Decimal)


def _structure_cattrs_scalar(value: Any, target_type: Any) -> Any:
    """Structure a scalar column value into ``target_type`` for ``cattrs``.

    Values that already have the target type, which is the case for anything loaded
    from the database, are returned unchanged.

    Args:
        value: The value to structure.
        target_type: The scalar type declared on the attrs field.

    Returns:
        ``value`` as an instance of ``target_type``.
    """
    if isinstance(value, target_type):
        return value
    if isinstance(value, str) and hasattr(target_type, "fromisoformat"):
        return target_type.fromisoformat(value)
    if target_type is dt.timedelta:
        return dt.timedelta(seconds=float(value))
    constructor: Callable[[Any], Any] = target_type
    return constructor(value)


@lru_cache(maxsize=1)
def _get_cattrs_converter() -> Any:
    """Return the ``cattrs`` converter used to build attrs schemas.

    The converter is a copy of the ``cattrs`` global converter taken on first use, so
    hooks registered on the global converter beforehand are honored. Structure hooks
    are added for the scalar column types ``cattrs`` has no built-in handler for.

    Returns:
        A configured ``cattrs`` converter.
    """
    converter = cattrs_global_converter.copy()
    for scalar_type in _CATTRS_SCALAR_TYPES:
        try:
            converter.get_structure_hook(scalar_type)
        except CattrsStructureHandlerNotFoundError:
            converter.register_structure_hook(scalar_type, _structure_cattrs_scalar)
    return converter


@lru_cache(maxsize=256)
def _get_list_schema_type(schema_type: "type[Any]") -> Any:
    """Return and cache ``list[schema_type]`` generic alias."""
    return list[schema_type]  # type: ignore[valid-type]


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
    converted: Any = schema_type(**filtered_dict)
    return cast("ModelDTOT", converted)


def _create_pagination(items: Any, filters: Any, total: "Optional[int]") -> "OffsetPagination[Any]":
    """Create OffsetPagination with consistent limit_offset logic.

    Args:
        items: Items to paginate.
        filters: Filters to extract LimitOffsetFilter from.
        total: Total count or None.

    Returns:
        OffsetPagination instance.
    """
    limit_offset = find_filter(LimitOffsetFilter, filters=filters) or LimitOffsetFilter(limit=len(items), offset=0)
    return OffsetPagination(
        items=items,
        limit=limit_offset.limit,
        offset=limit_offset.offset,
        total=total if total is not None else len(items),
    )
