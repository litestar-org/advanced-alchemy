"""Shared utilities for framework dependency-injection wiring.

These primitives are framework-agnostic and reused by framework
``advanced_alchemy.extensions`` provider modules.
"""

import datetime as dt
import os
from collections.abc import Callable, Iterable, Mapping, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Final, Literal, NamedTuple, Optional, Union, cast
from uuid import UUID

from sqlalchemy import inspect
from sqlalchemy.types import Boolean, Date, DateTime, Integer, Numeric, String, Time, TypeDecorator, Uuid
from sqlalchemy.types import Enum as SAEnum
from sqlalchemy.types import Float as SAFloat
from typing_extensions import NotRequired, TypeAlias, TypedDict, TypeGuard

from advanced_alchemy.exceptions import ImproperConfigurationError
from advanced_alchemy.filters import (
    ComparisonFilter,
    CursorFilter,
    CursorKey,
    InCollectionFilter,
    NotNullFilter,
    NullFilter,
    OrderByFilter,
    RelationshipFilter,
    RelationshipPath,
    SearchFilter,
    StatementFilter,
)
from advanced_alchemy.operations import validate_identifier
from advanced_alchemy.utils.singleton import SingletonMeta
from advanced_alchemy.utils.text import camelize

__all__ = (
    "CURSOR_SECRET_ENV_VARS",
    "ChoiceField",
    "CursorDefaults",
    "CursorSettings",
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
    "resolve_cursor_defaults",
    "resolve_cursor_settings",
    "resolve_filter_aliases",
    "resolve_filter_fields",
    "resolve_pagination_bounds",
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
CURSOR_SECRET_ENV_VARS: Final = ("ADVANCED_ALCHEMY_PAGINATION_CURSOR_SECRET", "SECRET_KEY")
"""Environment variables read, in order, for a cursor secret no configuration provides."""
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
    dt.datetime,
    dt.date,
    dt.time,
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
    pagination_type: NotRequired[Literal["limit_offset", "cursor"]]
    """Pagination mode to enable."""
    pagination_size: NotRequired[int]
    """Default pagination size."""
    pagination_max_size: NotRequired[Optional[int]]
    """Maximum allowed pagination size. ``None`` leaves page size unbounded."""
    pagination_cursor_secret: NotRequired[Union[str, bytes, None]]
    """Key that signs cursor tokens, or encrypts them with ``pagination_cursor_encrypted``."""
    pagination_cursor_ttl: NotRequired[Union[float, dt.timedelta, None]]
    """Cursor token lifetime in seconds or as a ``timedelta``."""
    pagination_cursor_encrypted: NotRequired[bool]
    """Encrypt cursor tokens so clients cannot read the key values. Requires a secret."""
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


@dataclass(frozen=True)
class CursorDefaults:
    """Application-wide cursor token options, used where a filter configuration sets none."""

    secret: Optional[bytes] = None
    """Signing or encryption key."""
    ttl: Union[float, dt.timedelta, None] = None
    """Token lifetime."""
    encrypted: Optional[bool] = None
    """Whether tokens are encrypted."""


def resolve_cursor_defaults(configs: Iterable[Any]) -> CursorDefaults:
    """Resolve application-wide cursor token options from an application's SQLAlchemy configurations.

    Args:
        configs: Configurations carrying ``pagination_cursor_secret``, ``pagination_cursor_ttl``,
            and ``pagination_cursor_encrypted``.

    Returns:
        The options the configurations set.

    Raises:
        ImproperConfigurationError: A secret is empty, a TTL is not a positive finite duration,
            or two configurations set different values for one option.
    """
    secrets: set[bytes] = set()
    ttls: dict[float, Union[float, dt.timedelta]] = {}
    encrypted: set[bool] = set()
    for config in configs:
        secret = _cursor_secret_bytes(getattr(config, "pagination_cursor_secret", None))
        if secret is not None:
            secrets.add(secret)
        ttl = _validated_cursor_ttl(getattr(config, "pagination_cursor_ttl", None))
        if ttl is not None:
            ttls[ttl.total_seconds() if isinstance(ttl, dt.timedelta) else float(ttl)] = ttl
        flag = getattr(config, "pagination_cursor_encrypted", None)
        if flag is not None:
            encrypted.add(bool(flag))
    for name, values in (("secret", secrets), ("ttl", ttls), ("encrypted", encrypted)):
        if len(values) > 1:
            msg = f"SQLAlchemy configurations of one application set different pagination_cursor_{name} values"
            raise ImproperConfigurationError(msg)
    return CursorDefaults(
        secret=next(iter(secrets), None),
        ttl=next(iter(ttls.values()), None),
        encrypted=next(iter(encrypted), None),
    )


@dataclass(frozen=True)
class CursorSettings:
    """Cursor pagination settings resolved from :class:`FilterConfig` once, when dependencies are built."""

    allowed_fields: frozenset[str]
    """Column names clients may order by."""
    default_field: Optional[str]
    """Ordering column when the request names none. ``None`` orders by primary key."""
    default_order: SortOrder
    """Direction of the default ordering column."""
    nulls: Optional[Literal["first", "last"]]
    """NULL placement applied to every ordering key."""
    secret: Optional[bytes]
    """Signing or encryption key set by the filter configuration."""
    ttl: Union[float, dt.timedelta, None]
    """Token lifetime set by the filter configuration."""
    encrypted: Optional[bool]
    """Whether tokens are encrypted, when the filter configuration says."""

    def token_options(
        self, defaults: Optional[CursorDefaults] = None, *, require_secret: bool = False
    ) -> tuple[Optional[bytes], Union[float, dt.timedelta, None], bool]:
        """Resolve the secret, lifetime, and encryption flag for issued and accepted tokens.

        Each option comes from the filter configuration, then ``defaults``. The secret then
        falls back to the :data:`CURSOR_SECRET_ENV_VARS` environment variables. Signing and
        encryption keys are derived from the secret inside the cursor codec.

        Args:
            defaults: Application-wide options.
            require_secret: Refuse to issue or accept unsigned tokens.

        Returns:
            The resolved secret, lifetime, and encryption flag.

        Raises:
            ImproperConfigurationError: No secret is configured and one is required or encryption is enabled.
        """
        secret = self.secret
        if secret is None and defaults is not None:
            secret = defaults.secret
        if secret is None:
            secret = _env_cursor_secret()
        ttl = self.ttl
        if ttl is None and defaults is not None:
            ttl = defaults.ttl
        encrypted = self.encrypted
        if encrypted is None:
            encrypted = bool(defaults is not None and defaults.encrypted)
        if secret is None and (require_secret or encrypted):
            msg = (
                "Cursor pagination requires a secret; set pagination_cursor_secret on the SQLAlchemy configuration or "
                f"the filter configuration, or the {CURSOR_SECRET_ENV_VARS[0]} environment variable"
            )
            raise ImproperConfigurationError(msg)
        return secret, ttl, encrypted

    def build(
        self,
        *,
        cursor: Optional[str],
        page_size: int,
        order_by: Union[str, Sequence[str], None] = None,
        sort_order: Optional[SortOrder] = None,
        defaults: Optional[CursorDefaults] = None,
        require_secret: bool = False,
    ) -> CursorFilter:
        """Build the cursor filter for one request.

        Args:
            cursor: Token from the request, or ``None`` for the first page.
            page_size: Validated page size.
            order_by: Requested ordering tokens; ``-name`` sorts descending.
            sort_order: Direction for a single unprefixed ``order_by`` token.
            defaults: Application-wide token options.
            require_secret: Refuse to issue or accept unsigned tokens.

        Returns:
            The request's cursor filter.

        Raises:
            ValueError: The ordering is not allowed or the token is invalid
                (:class:`~advanced_alchemy.exceptions.InvalidCursorError`).
            ImproperConfigurationError: A secret is required and none is configured.
        """
        tokens = [order_by] if isinstance(order_by, str) else order_by
        ordering = build_order_by_filters(
            tokens,
            sort_order,
            allowed_fields=self.allowed_fields,
            default_field=self.default_field,
            default_order=self.default_order,
            nulls=self.nulls,
        )
        keys = [CursorKey(item.field_name, item.sort_order, item.nulls) for item in ordering]
        secret, ttl, encrypted = self.token_options(defaults, require_secret=require_secret)
        return CursorFilter(keys, page_size, cursor, secret, ttl=ttl, encrypted=encrypted)


def resolve_cursor_settings(config: FilterConfig, model: Optional[type[Any]] = None) -> CursorSettings:
    """Validate cursor options in ``config`` and resolve them for per-request use.

    Args:
        config: Filter configuration with ``pagination_type="cursor"``.
        model: Mapped model, used to validate ``sort_fields`` when known.

    Returns:
        Resolved settings.

    Raises:
        ImproperConfigurationError: A sort path crosses a relationship, or the secret or TTL is invalid.
    """
    allowed: set[str] = set()
    if sort_fields := config.get("sort_fields"):
        allowed.update(normalize_sort_fields(sort_fields, model))
    sort_field = config.get("sort_field")
    if sort_field:
        allowed.update([sort_field] if isinstance(sort_field, str) else sort_field)
    if dotted := sorted(name for name in allowed if "." in name):
        msg = f"Cursor pagination orders by columns of the model; relationship sort paths are not supported: {dotted}"
        raise ImproperConfigurationError(msg)
    return CursorSettings(
        allowed_fields=frozenset(allowed),
        default_field=normalize_sort_field(sort_field) if sort_field else None,
        default_order=config.get("sort_order", "desc"),
        nulls=config.get("sort_nulls"),
        secret=_cursor_secret_bytes(config.get("pagination_cursor_secret")),
        ttl=_validated_cursor_ttl(config.get("pagination_cursor_ttl")),
        encrypted=config.get("pagination_cursor_encrypted"),
    )


def _cursor_secret_bytes(secret: Union[str, bytes, None]) -> Optional[bytes]:
    encoded = secret.encode("utf-8") if isinstance(secret, str) else secret
    if encoded == b"":
        msg = "pagination_cursor_secret must not be empty"
        raise ImproperConfigurationError(msg)
    return encoded


def _env_cursor_secret() -> Optional[bytes]:
    for name in CURSOR_SECRET_ENV_VARS:
        if value := os.environ.get(name):
            return value.encode("utf-8")
    return None


def _validated_cursor_ttl(ttl: Union[float, dt.timedelta, None]) -> Union[float, dt.timedelta, None]:
    from advanced_alchemy.filters._cursor import normalize_cursor_ttl

    try:
        normalize_cursor_ttl(ttl)
    except (TypeError, ValueError) as exc:
        msg = f"pagination_cursor_ttl must be a positive finite duration, got {ttl!r}"
        raise ImproperConfigurationError(msg) from exc
    return ttl


def resolve_pagination_bounds(
    config: FilterConfig,
    *,
    default_size: int = 20,
) -> tuple[int, Optional[int]]:
    """Validate and resolve default and maximum pagination sizes from ``config``."""
    raw_max_size: Any = config.get("pagination_max_size")
    max_size: Optional[int]
    if raw_max_size is None:
        max_size = None
    else:
        if not isinstance(raw_max_size, int) or isinstance(raw_max_size, bool) or raw_max_size < 1:
            msg = f"pagination_max_size must be a positive integer, got {raw_max_size!r}"
            raise ImproperConfigurationError(msg)
        max_size = raw_max_size

    raw_default_size: Any = config.get("pagination_size")
    if raw_default_size is not None:
        if not isinstance(raw_default_size, int) or isinstance(raw_default_size, bool) or raw_default_size < 1:
            msg = f"pagination_size must be a positive integer, got {raw_default_size!r}"
            raise ImproperConfigurationError(msg)
        if max_size is not None and raw_default_size > max_size:
            msg = f"pagination_size ({raw_default_size}) cannot exceed pagination_max_size ({max_size})"
            raise ImproperConfigurationError(msg)
        return raw_default_size, max_size

    effective_default = min(default_size, max_size) if max_size is not None else default_size
    return effective_default, max_size


class FilterFieldSpec:
    """Normalized query parameter descriptor derived from ``FilterConfig['filter_fields']``."""

    __slots__ = ("field_path", "leaf_field", "operator", "param_name", "rel_path", "value_type")

    operator: FilterOperator

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
    dt.datetime: ("eq", "ne", "gt", "ge", "lt", "le", "in"),
    dt.date: ("eq", "ne", "gt", "ge", "lt", "le", "in"),
    dt.time: ("eq", "ne", "gt", "ge", "lt", "le", "in"),
    int: ("eq", "ne", "gt", "ge", "lt", "le", "in"),
    float: ("eq", "ne", "gt", "ge", "lt", "le", "in"),
    Decimal: ("eq", "ne", "gt", "ge", "lt", "le", "in"),
}

_SA_TYPE_TABLE: tuple[tuple[Any, Optional[type[Any]], tuple[FilterOperator, ...]], ...] = (
    (Uuid, UUID, ("eq", "ne", "in")),
    (DateTime, dt.datetime, ("eq", "ne", "gt", "ge", "lt", "le", "in")),
    (Date, dt.date, ("eq", "ne", "gt", "ge", "lt", "le", "in")),
    (Time, dt.time, ("eq", "ne", "gt", "ge", "lt", "le", "in")),
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
            built = InCollectionFilter(field_name=spec.leaf_field, values=value) if value else None
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
) -> list[OrderByFilter]:
    """Parse repeatable ``orderBy`` tokens (`-col` descending) against ``allowed_fields``."""
    if not order_by_values:
        if default_field is None:
            return []
        return [OrderByFilter(field_name=default_field, sort_order=sort_order or default_order, nulls=nulls)]

    filters: list[OrderByFilter] = []
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
        filters.append(OrderByFilter(field_name=field_name, sort_order=direction, nulls=nulls))
    return filters


def _collect_filter_parameter_names(config: FilterConfig, model: Optional[type[Any]]) -> list[str]:
    """Collect canonical unaliased parameter names implied by ``config``."""
    names: list[str] = []
    for key, parameters in (
        ("id_filter", ("ids",)),
        ("created_at", ("created_before", "created_after")),
        ("updated_at", ("updated_before", "updated_after")),
        ("search", ("search_string", "search_ignore_case")),
    ):
        if config.get(key):
            names.extend(parameters)
    pagination_type = config.get("pagination_type")
    if pagination_type == "cursor":
        names.extend(("cursor", "page_size"))
    elif pagination_type:
        names.extend(("current_page", "page_size"))
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
