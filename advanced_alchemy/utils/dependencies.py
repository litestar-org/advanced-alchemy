"""Shared utilities for framework dependency-injection wiring.

These primitives are framework-agnostic and reused by framework
``advanced_alchemy.extensions`` provider modules.
"""

from collections.abc import Iterable, Mapping
from typing import Any, NamedTuple, Optional, Union, cast
from uuid import UUID

from typing_extensions import Literal, NotRequired, TypedDict

from advanced_alchemy.utils.singleton import SingletonMeta

__all__ = ("DependencyCache", "FieldNameType", "FilterConfig", "make_hashable")

HashableValue = Union[str, int, float, bool, None]
HashableType = Union[HashableValue, tuple[Any, ...], tuple[tuple[str, Any], ...], tuple[HashableValue, ...]]
SortOrder = Literal["asc", "desc"]


class FieldNameType(NamedTuple):
    """Type for field name and associated type information.

    This allows callers to specify both the field name and the expected type
    for generated filter values.
    """

    name: str
    """Name of the field to filter on."""
    type_hint: type[Any] = str
    """Type of the filter value. Defaults to ``str``."""


class FilterConfig(TypedDict):
    """Configuration for generating dynamic filters."""

    id_filter: NotRequired[type[Union[UUID, int, str]]]
    """Enable an id filter using the supplied type."""
    id_field: NotRequired[str]
    """Model field storing the primary key or identifier."""
    sort_field: NotRequired[Union[str, set[str], list[str]]]
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
    not_in_fields: NotRequired[Union[FieldNameType, set[FieldNameType], list[Union[str, FieldNameType]]]]
    """Fields that support not-in collection filters."""
    in_fields: NotRequired[Union[FieldNameType, set[FieldNameType], list[Union[str, FieldNameType]]]]
    """Fields that support in-collection filters."""


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
    if isinstance(value, (list, set)):
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
