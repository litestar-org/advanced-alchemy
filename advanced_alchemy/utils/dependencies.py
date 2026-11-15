"""Shared utilities for framework dependency-injection wiring.

These primitives are framework-agnostic and reused by framework
``advanced_alchemy.extensions`` provider modules.
"""

import datetime
from collections.abc import Callable, Iterable, Mapping, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal, NamedTuple, Optional, Union, cast
from uuid import UUID

from sqlalchemy import inspect
from sqlalchemy.types import Boolean, Date, DateTime, Integer, Numeric, String, Time, TypeDecorator, Uuid
from sqlalchemy.types import Enum as SAEnum
from sqlalchemy.types import Float as SAFloat
from typing_extensions import NotRequired, TypeAlias, TypedDict, TypeGuard

from advanced_alchemy.exceptions import ImproperConfigurationError
from advanced_alchemy.filters import (
    CollectionFilter,
    ComparisonFilter,
    NotNullFilter,
    NullFilter,
    OrderBy,
    RelationshipFilter,
    RelationshipPath,
    SearchFilter,
    StatementFilter,
)
from advanced_alchemy.operations import validate_identifier
from advanced_alchemy.utils.singleton import SingletonMeta
from advanced_alchemy.utils.text import camelize

__all__ = (
    "ChoiceField",
    "DependencyCache",
    "FieldNameType",
    "FilterConfig",
    "FilterFieldSpec",
    "FilterFieldsSpec",
    "FilterOperator",
    "build_field_filter",
    "build_field_filters",
    "build_order_by_filters",
    "create_field_filter_provider",
    "filter_cache_key",
    "filter_parameter_type",
    "group_filter_fields",
    "make_hashable",
    "normalize_choice_field_types",
    "normalize_field_name_types",
    "normalize_sort_field",
    "normalize_sort_fields",
    "resolve_filter_aliases",
    "resolve_filter_fields",
)

HashableValue = Union[str, int, float, bool, None]
HashableType = Union[HashableValue, tuple[Any, ...], tuple[tuple[str, Any], ...], tuple[HashableValue, ...]]
SortOrder = Literal["asc", "desc"]
SortField = Union[str, set[str], list[str]]
FilterOperator: TypeAlias = Literal[
    "eq",
    "ne",
    "contains",
    "startswith",
    "endswith",
    "gt",
    "ge",
    "lt",
    "le",
    "in",
    "is_null",
]
FilterFieldsSpec: TypeAlias = Union[AbstractSet[str], Sequence[str], Mapping[str, AbstractSet[FilterOperator]]]
FIELD_TUPLE_LENGTH = 2
_FILTER_OPERATOR_ORDER: tuple[FilterOperator, ...] = (
    "eq",
    "ne",
    "contains",
    "startswith",
    "endswith",
    "gt",
    "ge",
    "lt",
    "le",
    "in",
    "is_null",
)
_VALID_FILTER_OPERATORS: frozenset[str] = frozenset(_FILTER_OPERATOR_ORDER)
_STRING_FILTER_OPERATORS: frozenset[str] = frozenset({"contains", "startswith", "endswith"})
_RANGE_FILTER_OPERATORS: frozenset[str] = frozenset({"gt", "ge", "lt", "le"})
_ORDERED_PYTHON_TYPES: tuple[type[Any], ...] = (
    int,
    float,
    Decimal,
    datetime.datetime,
    datetime.date,
    datetime.time,
)


class FieldNameType(NamedTuple):
    """Type for field name and associated type information.

    This allows callers to specify both the field name and the expected type
    for generated filter values.
    """

    name: str
    """Name of the field to filter on."""
    type_hint: Any = str
    """Type of the filter value. Defaults to ``str``."""


@dataclass(frozen=True)
class ChoiceField:
    """Field name and explicit values for generated choice filters."""

    name: str
    """Name of the field to filter on."""
    choices: tuple[Any, ...]
    """Allowed values for the generated choice filter."""

    def __init__(self, name: str, choices: Iterable[Any]) -> None:
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "choices", tuple(choices))


FieldDefinition: TypeAlias = Union[str, FieldNameType]
FieldNameConfig: TypeAlias = Union[FieldDefinition, set[FieldDefinition], list[FieldDefinition]]
ChoiceFieldTuple: TypeAlias = tuple[str, Iterable[Any]]
FieldNameTypeTuple: TypeAlias = tuple[str, Any]
ChoiceFieldDefinition: TypeAlias = Union[str, FieldNameType, ChoiceField, FieldNameTypeTuple]
ChoiceFieldConfig: TypeAlias = Union[
    ChoiceFieldDefinition, set[ChoiceFieldDefinition], list[ChoiceFieldDefinition], tuple[ChoiceFieldDefinition, ...]
]


class FilterConfig(TypedDict):
    """Configuration for generating dynamic filters."""

    id_filter: NotRequired[type[Union[UUID, int, str]]]
    """Enable an id filter using the supplied type."""
    id_field: NotRequired[str]
    """Model field storing the primary key or identifier."""
    sort_field: NotRequired[SortField]
    """Default field or fields to use for sorting."""
    sort_order: NotRequired[SortOrder]
    """Default sort order."""
    sort_nulls: NotRequired[Optional[Literal["first", "last"]]]
    """Where NULLs sort in the order-by filter. ``None`` leaves the placement to the database."""
    pagination_type: NotRequired[Literal["limit_offset"]]
    """Pagination mode to enable."""
    pagination_size: NotRequired[int]
    """Default pagination size."""
    search: NotRequired[Union[str, set[str], list[str]]]
    """Fields to enable search on."""
    search_ignore_case: NotRequired[bool]
    """Whether search should be case-insensitive."""
    search_escape_wildcards: NotRequired[bool]
    """Whether ``%`` and ``_`` in the search string match literally. Requires SQL ``ESCAPE`` support."""
    created_at: NotRequired[bool]
    """Enable created-at range filtering."""
    updated_at: NotRequired[bool]
    """Enable updated-at range filtering."""
    not_in_fields: NotRequired[FieldNameConfig]
    """Fields that support not-in collection filters."""
    in_fields: NotRequired[FieldNameConfig]
    """Fields that support in-collection filters."""
    boolean_fields: NotRequired[FieldNameConfig]
    """Fields that support boolean filters."""
    choice_fields: NotRequired[ChoiceFieldConfig]
    """Fields that support choices filters."""
    filter_fields: NotRequired[FilterFieldsSpec]
    """Model columns or dotted relationship paths exposed as operator-suffixed field filters."""
    sort_fields: NotRequired[Union[AbstractSet[str], Sequence[str]]]
    """Allowlisted column or single-valued relationship paths accepted by ``orderBy``."""
    alias_generator: NotRequired[Union[Literal["snake_case", "camel_case"], Callable[[str], str]]]
    """Maps a parameter's snake_case name to its public query parameter.

    Supported by both Litestar and FastAPI.

    Receives ``created_before``, ``page_size``, ``sort_order``, or a model field name for the
    per-field filters. Defaults to :func:`~advanced_alchemy.utils.text.camelize`, which produces the
    names this has always generated (``createdBefore``, ``pageSize``, ``sortOrder``). Pass
    ``"snake_case"`` to keep snake_case instead, or ``"camel_case"`` for explicit camelCase.
    A callable supports application-specific naming conventions.

    An explicit generator must give every parameter a distinct name; one shared between two filters is rejected when the
    dependency is built, because the framework would bind the single value to both.
    """


class DependencyCache(metaclass=SingletonMeta):
    """Singleton cache for dynamically generated dependency providers."""

    def __init__(self) -> None:
        self.dependencies: dict[HashableType, Any] = {}

    def add_dependencies(self, key: HashableType, dependencies: Any) -> None:
        """Cache dependency providers by a precomputed key.

        Args:
            key: Precomputed cache key.
            dependencies: Dependency provider object to cache.
        """
        self.dependencies[key] = dependencies

    def get_dependencies(self, key: HashableType) -> Optional[Any]:
        """Retrieve dependency providers by a precomputed key.

        Args:
            key: Precomputed cache key.

        Returns:
            Cached dependency providers, if present.
        """
        return self.dependencies.get(key)

    def set(self, config: FilterConfig, dependencies: Any) -> None:
        """Cache dependency providers by filter config.

        Args:
            config: Filter configuration used to derive a cache key.
            dependencies: Dependency provider object to cache.
        """
        self.dependencies[make_hashable(config)] = dependencies

    def get(self, config: FilterConfig) -> Optional[Any]:
        """Retrieve dependency providers by filter config.

        Args:
            config: Filter configuration used to derive a cache key.

        Returns:
            Cached dependency providers, if present.
        """
        return self.dependencies.get(make_hashable(config))


def make_hashable(value: Any) -> HashableType:
    """Convert a possibly nested value into a hashable representation.

    Args:
        value: Value that needs to be made hashable.

    Returns:
        A hashable representation of ``value``.
    """
    if isinstance(value, Mapping):
        mapping = cast("Mapping[Any, Any]", value)  # type: ignore[redundant-cast]
        items = [(str(key), make_hashable(mapping[key])) for key in sorted(mapping.keys(), key=str)]
        return tuple(items)
    if isinstance(value, list):
        values = cast("Iterable[Any]", value)
        return tuple(make_hashable(item) for item in values)
    if isinstance(value, set):
        values = cast("Iterable[Any]", value)
        hashable_items = [make_hashable(item) for item in values]
        filtered_items = [item for item in hashable_items if item is not None]
        return tuple(sorted(filtered_items, key=str))
    if isinstance(value, tuple):
        values = cast("tuple[Any, ...]", value)  # type: ignore[redundant-cast]
        return tuple(make_hashable(item) for item in values)
    if isinstance(value, (str, int, float, bool, type(None))):
        return value
    return str(value)


def normalize_field_name_types(field_definitions: FieldNameConfig) -> set[FieldNameType]:
    """Normalize field-name filter config to ``FieldNameType`` values."""
    raw_fields = {field_definitions} if isinstance(field_definitions, (str, FieldNameType)) else set(field_definitions)
    return {
        FieldNameType(name=field_definition, type_hint=str) if isinstance(field_definition, str) else field_definition
        for field_definition in raw_fields
    }


def _literal_type(choices: tuple[Any, ...]) -> Any:
    """Build a runtime ``Literal`` type from configured choices."""
    return cast("Any", Literal).__getitem__(choices)


def _is_choice_field_tuple(value: Any) -> TypeGuard[ChoiceFieldTuple]:
    """Return whether ``value`` is a ``(field_name, choices)`` config tuple."""
    if not isinstance(value, tuple) or isinstance(value, FieldNameType):
        return False
    tuple_value = cast("tuple[Any, ...]", value)  # type: ignore[redundant-cast]
    return (
        len(tuple_value) == FIELD_TUPLE_LENGTH
        and isinstance(tuple_value[0], str)
        and not isinstance(tuple_value[1], type)
        and isinstance(tuple_value[1], Iterable)
        and not isinstance(tuple_value[1], (str, bytes))
    )


def _is_field_name_type_tuple(value: Any) -> TypeGuard[FieldNameTypeTuple]:
    """Return whether ``value`` is a ``(field_name, type_hint)`` config tuple."""
    if not isinstance(value, tuple) or isinstance(value, FieldNameType):
        return False
    tuple_value = cast("tuple[Any, ...]", value)  # type: ignore[redundant-cast]
    return (
        len(tuple_value) == FIELD_TUPLE_LENGTH
        and isinstance(tuple_value[0], str)
        and not _is_choice_field_tuple(value)
        and not isinstance(tuple_value[1], (str, bytes))
    )


def _field_type_from_choices(name: str, choices: Iterable[Any]) -> FieldNameType:
    """Build a field definition from explicit choice values."""
    choices_tuple = tuple(choices)
    if not choices_tuple:
        msg = "ChoiceField choices must not be empty"
        raise ValueError(msg)
    return FieldNameType(name=name, type_hint=_literal_type(choices_tuple))


def normalize_choice_field_types(field_definitions: ChoiceFieldConfig) -> tuple[FieldNameType, ...]:
    """Normalize choice filter config to ``FieldNameType`` values."""
    raw_fields: tuple[ChoiceFieldDefinition, ...]
    if (
        isinstance(field_definitions, (str, FieldNameType, ChoiceField))
        or _is_choice_field_tuple(field_definitions)
        or _is_field_name_type_tuple(field_definitions)
    ):
        raw_fields = (field_definitions,)
    elif isinstance(field_definitions, set):
        raw_fields = tuple(sorted(field_definitions, key=str))
    else:
        raw_fields = tuple(field_definitions)
    normalized_fields: dict[str, FieldNameType] = {}
    for field_definition in raw_fields:
        if isinstance(field_definition, str):
            normalized_field = FieldNameType(name=field_definition, type_hint=str)
        elif isinstance(field_definition, FieldNameType):
            normalized_field = field_definition
        elif isinstance(field_definition, ChoiceField):
            normalized_field = _field_type_from_choices(field_definition.name, field_definition.choices)
        elif _is_choice_field_tuple(field_definition):
            normalized_field = _field_type_from_choices(field_definition[0], field_definition[1])
        elif _is_field_name_type_tuple(field_definition):
            normalized_field = FieldNameType(name=field_definition[0], type_hint=field_definition[1])
        else:
            msg = "Choice field tuple must be (field_name, type_hint) or (field_name, choices)"
            raise ValueError(msg)
        normalized_fields.setdefault(normalized_field.name, normalized_field)
    return tuple(normalized_fields.values())


def normalize_sort_field(sort_field: SortField) -> str:
    """Return a scalar default field for a configured sort field value."""
    if isinstance(sort_field, str):
        return sort_field
    if isinstance(sort_field, list):
        return sort_field[0]
    return min(sort_field)


class FilterFieldSpec:
    """Normalized query parameter descriptor derived from ``FilterConfig['filter_fields']``."""

    __slots__ = ("field_path", "leaf_field", "operator", "param_name", "rel_path", "value_type")

    def __init__(
        self,
        *,
        field_path: str,
        rel_path: tuple[str, ...],
        leaf_field: str,
        operator: FilterOperator,
        param_name: str,
        value_type: Any,
    ) -> None:
        self.field_path = field_path
        self.rel_path = rel_path
        self.leaf_field = leaf_field
        self.operator = operator
        self.param_name = param_name
        self.value_type = value_type


def _safe_python_type(column_type: Any) -> Optional[Any]:
    """Return ``column_type.python_type`` when implemented, otherwise ``None``."""
    try:
        return column_type.python_type
    except (NotImplementedError, AttributeError):
        return None


def _resolve_model_column(model: Any, field_path: str) -> tuple[tuple[str, ...], str, Any, bool]:
    """Resolve a column or dotted relationship path on ``model``."""
    parts = field_path.split(".")
    if not field_path or any(not part for part in parts):
        msg = f"Invalid field path {field_path!r}"
        raise ImproperConfigurationError(msg)
    for index, part in enumerate(parts):
        try:
            validate_identifier(part, "relationship" if index < len(parts) - 1 else "column")
        except ValueError as exc:
            raise ImproperConfigurationError(str(exc)) from exc

    rel_path = tuple(parts[:-1])
    leaf_name = parts[-1]
    current_cls: Any = model
    for hop in rel_path:
        mapper = _inspect_mapper(current_cls, field_path)
        rel_prop = mapper.relationships.get(hop)
        if rel_prop is None:
            msg = f"Unknown relationship {hop!r} on model {current_cls.__name__} for filter_fields entry {field_path!r}"
            raise ImproperConfigurationError(msg)
        current_cls = rel_prop.mapper.class_

    leaf_mapper = _inspect_mapper(current_cls, field_path)
    column_prop = leaf_mapper.column_attrs.get(leaf_name)
    if column_prop is not None and column_prop.columns:
        column = column_prop.columns[0]
        return rel_path, leaf_name, column.type, bool(getattr(column, "nullable", False))

    descriptor = leaf_mapper.all_orm_descriptors.get(leaf_name)
    expression = getattr(descriptor, "expression", None) if descriptor is not None else None
    if expression is not None and hasattr(expression, "type"):
        return rel_path, leaf_name, expression.type, bool(getattr(expression, "nullable", True))

    msg = f"Unknown column {leaf_name!r} on model {current_cls.__name__} for filter_fields entry {field_path!r}"
    raise ImproperConfigurationError(msg)


def _inspect_mapper(model: Any, field_path: str) -> Any:
    """Return the SQLAlchemy mapper for ``model`` or raise ``ImproperConfigurationError``."""
    model_info = inspect(model, raiseerr=False)
    if model_info is None or not hasattr(model_info, "mapper"):
        msg = f"Expected a SQLAlchemy mapped model to resolve {field_path!r}, got {model!r}"
        raise ImproperConfigurationError(msg)
    return model_info.mapper


def _infer_column_type_and_ops(column_type: Any, *, nullable: bool) -> tuple[Any, tuple[FilterOperator, ...]]:
    """Infer Python parameter type and default filter operators from a SQLAlchemy column type."""
    py_type, ops = _classify_column_type(column_type)
    if nullable and "is_null" not in ops:
        ops = (*ops, "is_null")
    return py_type, ops


_PYTHON_TYPE_OPS: dict[Any, tuple[FilterOperator, ...]] = {
    UUID: ("eq", "ne", "in"),
    datetime.datetime: ("eq", "ne", "gt", "ge", "lt", "le", "in"),
    datetime.date: ("eq", "ne", "gt", "ge", "lt", "le", "in"),
    datetime.time: ("eq", "ne", "gt", "ge", "lt", "le", "in"),
    int: ("eq", "ne", "gt", "ge", "lt", "le", "in"),
    float: ("eq", "ne", "gt", "ge", "lt", "le", "in"),
    Decimal: ("eq", "ne", "gt", "ge", "lt", "le", "in"),
}

_SA_TYPE_TABLE: tuple[tuple[Any, Optional[type[Any]], tuple[FilterOperator, ...]], ...] = (
    (Uuid, UUID, ("eq", "ne", "in")),
    (DateTime, datetime.datetime, ("eq", "ne", "gt", "ge", "lt", "le", "in")),
    (Date, datetime.date, ("eq", "ne", "gt", "ge", "lt", "le", "in")),
    (Time, datetime.time, ("eq", "ne", "gt", "ge", "lt", "le", "in")),
    ((Integer, SAFloat, Numeric), None, ("eq", "ne", "gt", "ge", "lt", "le", "in")),
    (String, str, ("eq", "ne", "contains", "startswith", "endswith", "in")),
)


def _classify_sa_column_type(column_type: Any) -> Optional[tuple[Any, tuple[FilterOperator, ...]]]:
    """Match SQLAlchemy type classes and ``TypeDecorator`` wrappers into filter metadata."""
    for sa_types, default_py, ops in _SA_TYPE_TABLE:
        if isinstance(column_type, sa_types):
            if default_py is not None:
                return (default_py, ops)
            inferred_num = int if isinstance(column_type, Integer) else float
            return (inferred_num, ops)
    if isinstance(column_type, TypeDecorator):
        impl = getattr(cast("Any", column_type), "impl", None)
        if impl is not None and impl is not column_type:
            return _classify_column_type(impl)
    return None


def _classify_column_type(column_type: Any) -> tuple[Any, tuple[FilterOperator, ...]]:
    """Classify a SQLAlchemy ``TypeEngine`` instance into Python type and operators."""
    py_type = _safe_python_type(column_type)
    if isinstance(column_type, Boolean):
        return (bool, ("eq",))
    if isinstance(column_type, SAEnum):
        enum_cls = getattr(column_type, "enum_class", None)
        resolved_enum = enum_cls if isinstance(enum_cls, type) else str
        return (resolved_enum, ("eq", "ne", "in"))
    if py_type in _PYTHON_TYPE_OPS:
        return (py_type, _PYTHON_TYPE_OPS[py_type])
    if type(column_type).__name__ in {"GUID", "UUID"}:
        return (UUID, ("eq", "ne", "in"))
    matched = _classify_sa_column_type(column_type)
    if matched is not None:
        return matched
    fallback_type = py_type if isinstance(py_type, type) else str
    return (fallback_type, ("eq", "ne", "in"))


def _validate_and_order_filter_ops(
    field_path: str,
    py_type: Any,
    inferred_ops: tuple[FilterOperator, ...],
    requested_ops: Optional[Iterable[FilterOperator]],
) -> tuple[FilterOperator, ...]:
    """Validate optional explicit operator narrowing against inferred column capabilities."""
    if requested_ops is None:
        return inferred_ops
    requested_list = list(requested_ops)
    for operator in requested_list:
        if operator not in _VALID_FILTER_OPERATORS:
            msg = f"Unsupported filter operator {operator!r} for field {field_path!r}"
            raise ImproperConfigurationError(msg)
        if operator in _STRING_FILTER_OPERATORS and py_type is not str:
            msg = f"String filter operator {operator!r} is not supported for non-text field {field_path!r}"
            raise ImproperConfigurationError(msg)
        if operator in _RANGE_FILTER_OPERATORS and py_type not in _ORDERED_PYTHON_TYPES:
            msg = f"Range filter operator {operator!r} is not supported for field {field_path!r}"
            raise ImproperConfigurationError(msg)
    requested_set = set(requested_list)
    return tuple(op_name for op_name in _FILTER_OPERATOR_ORDER if op_name in requested_set)


def resolve_filter_fields(
    filter_fields: FilterFieldsSpec,
    model: Optional[type[Any]],
) -> tuple[FilterFieldSpec, ...]:
    """Expand ``FilterConfig['filter_fields']`` into normalized field filter specs."""
    if model is None:
        msg = "FilterConfig 'filter_fields' requires a SQLAlchemy model; pass model=... or use create_service_dependencies(...)"
        raise ImproperConfigurationError(msg)

    field_entries: list[tuple[str, Optional[Iterable[FilterOperator]]]]
    if isinstance(filter_fields, Mapping):
        typed_mapping = cast("Mapping[str, Iterable[FilterOperator]]", filter_fields)
        field_entries = list(typed_mapping.items())
    elif isinstance(filter_fields, AbstractSet):
        field_entries = [(field_name, None) for field_name in sorted(filter_fields)]
    else:
        field_entries = [(field_name, None) for field_name in filter_fields]

    specs: list[FilterFieldSpec] = []
    for field_path, explicit_ops in field_entries:
        rel_path, leaf_field, column_type, nullable = _resolve_model_column(model, field_path)
        py_type, inferred_ops = _infer_column_type_and_ops(column_type, nullable=nullable)
        ops = _validate_and_order_filter_ops(field_path, py_type, inferred_ops, explicit_ops)
        base_param = field_path.replace(".", "_")
        specs.extend(
            FilterFieldSpec(
                field_path=field_path,
                rel_path=rel_path,
                leaf_field=leaf_field,
                operator=operator,
                param_name=f"{base_param}_{operator}",
                value_type=py_type,
            )
            for operator in ops
        )
    return tuple(specs)


def _validate_sort_field_path(field_path: str, model: Optional[type[Any]]) -> None:
    """Validate identifier segments and model traversal for one ``sort_fields`` entry."""
    parts = field_path.split(".")
    if not field_path or any(not part for part in parts):
        msg = f"Invalid sort_fields entry {field_path!r}"
        raise ImproperConfigurationError(msg)
    for index, part in enumerate(parts):
        segment_kind = "relationship" if index < len(parts) - 1 else "column"
        try:
            validate_identifier(part, segment_kind)
        except ValueError as exc:
            raise ImproperConfigurationError(str(exc)) from exc
    if model is None:
        return
    current_cls: Any = model
    for hop in parts[:-1]:
        mapper = _inspect_mapper(current_cls, field_path)
        rel_prop = mapper.relationships.get(hop)
        if rel_prop is None:
            msg = f"Unknown relationship {hop!r} on model {current_cls.__name__} for sort_fields entry {field_path!r}"
            raise ImproperConfigurationError(msg)
        if rel_prop.uselist:
            msg = f"sort_fields entry {field_path!r} traverses collection relationship {hop!r}; only to-one paths are sortable"
            raise ImproperConfigurationError(msg)
        current_cls = rel_prop.mapper.class_
    _resolve_model_column(current_cls, parts[-1])


def normalize_sort_fields(
    sort_fields: Union[AbstractSet[str], Sequence[str]],
    model: Optional[type[Any]] = None,
) -> tuple[str, ...]:
    """Normalize and validate ``FilterConfig['sort_fields']``."""
    raw_fields = sorted(sort_fields) if isinstance(sort_fields, AbstractSet) else list(sort_fields)
    normalized: list[str] = []
    seen: set[str] = set()
    for field_path in raw_fields:
        _validate_sort_field_path(field_path, model)
        if field_path not in seen:
            seen.add(field_path)
            normalized.append(field_path)
    return tuple(normalized)


def group_filter_fields(
    specs: Sequence[FilterFieldSpec],
) -> tuple[tuple[tuple[str, ...], str, tuple[FilterFieldSpec, ...]], ...]:
    """Group field parameter specs so shared relationship paths compile to one ``RelationshipFilter``."""
    grouped: dict[tuple[tuple[str, ...], str], list[FilterFieldSpec]] = {}
    for spec in specs:
        key = (spec.rel_path, "" if spec.rel_path else spec.field_path)
        grouped.setdefault(key, []).append(spec)
    return tuple((rel_path, local_field, tuple(group)) for (rel_path, local_field), group in grouped.items())


def filter_parameter_type(spec: FilterFieldSpec) -> Any:
    """Return the framework query parameter type annotation for a ``FilterFieldSpec``."""
    if spec.operator == "is_null":
        return Optional[bool]
    if spec.operator in _STRING_FILTER_OPERATORS:
        return Optional[str]
    if spec.operator == "in":
        return Optional[cast("Any", list).__class_getitem__(spec.value_type)]
    return Optional[spec.value_type]


def build_field_filter(
    spec: FilterFieldSpec,
    value: Any,
    *,
    ignore_case: bool = True,
    escape_wildcards: bool = False,
) -> Optional[StatementFilter]:
    """Build a :class:`~advanced_alchemy.filters.StatementFilter` for one field query value."""
    built: Optional[StatementFilter] = None
    if value is not None:
        if spec.operator == "is_null":
            built = NullFilter(field_name=spec.leaf_field) if value else NotNullFilter(field_name=spec.leaf_field)
        elif spec.operator == "contains":
            built = SearchFilter(
                field_name=spec.leaf_field,
                value=str(value),
                ignore_case=ignore_case,
                escape_wildcards=escape_wildcards,
            )
        elif spec.operator in {"startswith", "endswith"}:
            cmp_op = f"{'i' if ignore_case else ''}{spec.operator}"
            built = ComparisonFilter(field_name=spec.leaf_field, operator=cmp_op, value=value)
        elif spec.operator == "in":
            built = CollectionFilter(field_name=spec.leaf_field, values=value) if value else None
        else:
            built = ComparisonFilter(field_name=spec.leaf_field, operator=spec.operator, value=value)
    return built


def build_field_filters(
    specs: Sequence[FilterFieldSpec],
    values: Mapping[str, Any],
    *,
    rel_path: tuple[str, ...],
    ignore_case: bool = True,
    escape_wildcards: bool = False,
) -> Optional[Union[list[StatementFilter], RelationshipFilter]]:
    """Build direct filters or one grouped :class:`~advanced_alchemy.filters.RelationshipFilter`."""
    resolved = [
        filter_obj
        for spec in specs
        if (
            filter_obj := build_field_filter(
                spec,
                values.get(spec.param_name),
                ignore_case=ignore_case,
                escape_wildcards=escape_wildcards,
            )
        )
        is not None
    ]
    if not resolved:
        return None
    if not rel_path:
        return resolved
    rel_arg: RelationshipPath = rel_path[0] if len(rel_path) == 1 else rel_path
    return RelationshipFilter(relationship=rel_arg, filters=resolved)


def create_field_filter_provider(
    specs: Sequence[FilterFieldSpec],
    *,
    rel_path: tuple[str, ...],
    alias_for: Callable[[str], str],
    annotation_factory: Callable[[FilterFieldSpec, str], Any],
    name: str,
    ignore_case: bool = True,
    escape_wildcards: bool = False,
) -> Callable[..., Any]:
    """Construct a signatured dependency callable for a local or relationship field filter group."""
    import inspect

    return_annotation: Any = Optional[RelationshipFilter] if rel_path else Optional[list[StatementFilter]]

    def provide_field_filters(**kwargs: Any) -> Any:
        return build_field_filters(
            specs,
            kwargs,
            rel_path=rel_path,
            ignore_case=ignore_case,
            escape_wildcards=escape_wildcards,
        )

    parameters: list[inspect.Parameter] = []
    annotations: dict[str, Any] = {"return": return_annotation}
    for spec in specs:
        alias = alias_for(spec.param_name)
        annotation = annotation_factory(spec, alias)
        parameters.append(
            inspect.Parameter(
                name=spec.param_name,
                kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
                default=None,
                annotation=annotation,
            )
        )
        annotations[spec.param_name] = annotation

    provide_field_filters.__name__ = name
    provide_field_filters.__signature__ = inspect.Signature(  # type: ignore[attr-defined]
        parameters=parameters,
        return_annotation=return_annotation,
    )
    provide_field_filters.__annotations__ = annotations
    return provide_field_filters


def build_order_by_filters(
    order_by_values: Optional[Sequence[str]],
    sort_order: Optional[SortOrder],
    *,
    allowed_fields: AbstractSet[str],
    default_field: Optional[str] = None,
    default_order: SortOrder = "desc",
    nulls: Optional[Literal["first", "last"]] = None,
) -> list[OrderBy]:
    """Parse repeatable ``orderBy`` tokens (`-col` descending) against ``allowed_fields``."""
    if not order_by_values:
        if default_field is None:
            return []
        return [OrderBy(field_name=default_field, sort_order=sort_order or default_order, nulls=nulls)]

    filters: list[OrderBy] = []
    for raw in order_by_values:
        if not raw:
            msg = "Sort field name must not be empty"
            raise ValueError(msg)
        if raw.startswith("-"):
            field_name = raw[1:]
            direction: SortOrder = "desc"
        elif raw.startswith("+"):
            field_name = raw[1:]
            direction = "asc"
        else:
            field_name = raw
            direction = sort_order if len(order_by_values) == 1 and sort_order is not None else "asc"

        if field_name not in allowed_fields:
            allowed_display = ", ".join(sorted(allowed_fields))
            msg = f"Invalid sort field {field_name!r}; allowed fields are: {allowed_display}"
            raise ValueError(msg)
        filters.append(OrderBy(field_name=field_name, sort_order=direction, nulls=nulls))
    return filters


def _collect_filter_parameter_names(config: FilterConfig, model: Optional[type[Any]]) -> list[str]:
    """Collect canonical unaliased parameter names implied by ``config``."""
    names: list[str] = []
    for key, parameters in (
        ("id_filter", ("ids",)),
        ("created_at", ("created_before", "created_after")),
        ("updated_at", ("updated_before", "updated_after")),
        ("pagination_type", ("current_page", "page_size")),
        ("search", ("search_string", "search_ignore_case")),
    ):
        if config.get(key):
            names.extend(parameters)
    if config.get("sort_field") or config.get("sort_fields"):
        names.extend(("order_by", "sort_order"))
    for key, suffix in (("not_in_fields", "_not_in"), ("in_fields", "_in"), ("boolean_fields", "")):
        if fields := config.get(key):
            names.extend(field.name + suffix for field in normalize_field_name_types(cast("FieldNameConfig", fields)))
    if choices := config.get("choice_fields"):
        names.extend(field.name for field in normalize_choice_field_types(choices))
    if filter_fields := config.get("filter_fields"):
        names.extend(spec.param_name for spec in resolve_filter_fields(filter_fields, model))
    return names


def _resolve_single_filter_alias(scoped_name: str, generator: Any) -> Any:
    """Resolve one query parameter alias given the configured preset or callable."""
    if isinstance(generator, str):
        return scoped_name if generator == "snake_case" else camelize(scoped_name)
    return camelize(scoped_name) if generator is None else generator(scoped_name)


def resolve_filter_aliases(
    config: FilterConfig, *, prefix: Optional[str] = None, model: Optional[type[Any]] = None
) -> dict[str, str]:
    """Resolve public query names once, validating only opt-in custom naming."""
    clean_prefix = prefix.rstrip("_") if prefix else ""
    names = _collect_filter_parameter_names(config, model)
    generator = config.get("alias_generator")
    if isinstance(generator, str) and generator not in {"snake_case", "camel_case"}:
        msg = f"Unknown filter alias preset {generator!r}; expected snake_case or camel_case"
        raise ImproperConfigurationError(msg)
    resolved: dict[str, str] = {}
    claimed: set[str] = set()
    for name in names:
        scoped_name = f"{clean_prefix}_{name}" if clean_prefix else name
        alias = _resolve_single_filter_alias(scoped_name, generator)
        if generator is not None and (not isinstance(alias, str) or not alias or alias in claimed):
            msg = f"Filter parameter {name!r} has an invalid or duplicate query parameter {alias!r}"
            raise ImproperConfigurationError(msg)
        claimed.add(alias)
        resolved[name] = alias
    return resolved


def filter_cache_key(
    namespace: str,
    config: FilterConfig,
    defaults: Any,
    aliases: dict[str, str],
    model: Optional[type[Any]] = None,
) -> tuple[Any, ...]:
    """Cache effective configuration and names, retaining complete values for equality."""
    values = {key: value for key, value in config.items() if key != "alias_generator"}
    default_values = tuple(
        (name, getattr(defaults, name))
        for name in sorted({name for cls in type(defaults).__mro__ for name in getattr(cls, "__annotations__", {})})
    )
    model_key = f"{model.__module__}.{model.__qualname__}:{id(model)}" if model is not None else None
    return namespace, model_key, make_hashable(values), make_hashable(default_values), make_hashable(aliases)
