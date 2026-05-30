"""Shared utilities for framework dependency-injection wiring.

These primitives are framework-agnostic and reused by framework
``advanced_alchemy.extensions`` provider modules.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, NamedTuple, Optional, Union, cast
from uuid import UUID

from typing_extensions import Literal, NotRequired, TypeAlias, TypedDict

from advanced_alchemy.utils.singleton import SingletonMeta

__all__ = (
    "ChoiceField",
    "DependencyCache",
    "FieldNameType",
    "FilterConfig",
    "make_hashable",
    "normalize_choice_field_types",
    "normalize_field_name_types",
    "normalize_sort_field",
)

HashableValue = Union[str, int, float, bool, None]
HashableType = Union[HashableValue, tuple[Any, ...], tuple[tuple[str, Any], ...], tuple[HashableValue, ...]]
SortOrder = Literal["asc", "desc"]
SortField = Union[str, set[str], list[str]]


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
ChoiceFieldDefinition: TypeAlias = Union[str, FieldNameType, ChoiceField]
ChoiceFieldConfig: TypeAlias = Union[ChoiceFieldDefinition, set[ChoiceFieldDefinition], list[ChoiceFieldDefinition]]


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
    pagination_type: NotRequired[Literal["limit_offset"]]
    """Pagination mode to enable."""
    pagination_size: NotRequired[int]
    """Default pagination size."""
    search: NotRequired[Union[str, set[str], list[str]]]
    """Fields to enable search on."""
    search_ignore_case: NotRequired[bool]
    """Whether search should be case-insensitive."""
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


def normalize_choice_field_types(field_definitions: ChoiceFieldConfig) -> tuple[FieldNameType, ...]:
    """Normalize choice filter config to ``FieldNameType`` values."""
    raw_fields: tuple[ChoiceFieldDefinition, ...]
    if isinstance(field_definitions, (str, FieldNameType, ChoiceField)):
        raw_fields = (field_definitions,)
    elif isinstance(field_definitions, set):
        raw_fields = tuple(sorted(field_definitions, key=str))
    else:
        raw_fields = tuple(field_definitions)
    normalized_fields: dict[str, FieldNameType] = {}
    for field_definition in raw_fields:
        if isinstance(field_definition, str):
            normalized_field = FieldNameType(name=field_definition, type_hint=str)
        elif isinstance(field_definition, ChoiceField):
            if not field_definition.choices:
                msg = "ChoiceField choices must not be empty"
                raise ValueError(msg)
            normalized_field = FieldNameType(
                name=field_definition.name,
                type_hint=_literal_type(field_definition.choices),
            )
        else:
            normalized_field = field_definition
        normalized_fields.setdefault(normalized_field.name, normalized_field)
    return tuple(normalized_fields.values())


def normalize_sort_field(sort_field: SortField) -> str:
    """Return a scalar default field for a configured sort field value."""
    if isinstance(sort_field, str):
        return sort_field
    if isinstance(sort_field, list):
        return sort_field[0]
    return sorted(sort_field)[0]
