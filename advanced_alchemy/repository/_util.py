# ruff: noqa: PLR0911
import dataclasses
import datetime
import hashlib
from collections.abc import Iterable, Mapping, Sequence
from typing import Any, Generic, Literal, Optional, Protocol, Union, cast, get_args, get_origin, overload

from sqlalchemy import (
    Column,
    Delete,
    Dialect,
    Select,
    UnaryExpression,
    Update,
    and_,
    inspect,
)
from sqlalchemy.exc import NoInspectionAvailable
from sqlalchemy.orm import (
    InstrumentedAttribute,
    Load,
    Mapper,
    MapperProperty,
    RelationshipProperty,
    class_mapper,
    joinedload,
    lazyload,
    object_session,
    selectinload,
)
from sqlalchemy.sql import ColumnElement, ColumnExpressionArgument
from sqlalchemy.sql.base import ExecutableOption
from sqlalchemy.sql.dml import ReturningDelete, ReturningUpdate
from sqlalchemy.sql.elements import Label
from typing_extensions import TypeAlias

from advanced_alchemy.base import ModelProtocol
from advanced_alchemy.exceptions import ErrorMessages, ImproperConfigurationError, NotFoundError
from advanced_alchemy.exceptions import wrap_sqlalchemy_exception as _wrap_sqlalchemy_exception
from advanced_alchemy.filters import (
    InAnyFilter,
    PaginationFilter,
    StatementFilter,
    StatementTypeT,
)
from advanced_alchemy.mixins.softdelete import SoftDeleteMixin
from advanced_alchemy.repository._upsert import (
    DEFAULT_INSERTMANYVALUES_MAX_PARAMETERS,
    DEFAULT_SAFE_TYPES,
    _UpsertPlanningMixin,  # pyright: ignore[reportPrivateUsage]
    compare_values,
    has_upsert_update_intent,
    was_attribute_set,
)
from advanced_alchemy.repository.typing import ModelT, OrderingPair, PrimaryKeyType
from advanced_alchemy.types.file_object.data_type import StoredObject
from advanced_alchemy.utils.dataclass import Empty, EmptyType
from advanced_alchemy.utils.serialization import encode_complex_type, encode_json

__all__ = (
    "DEFAULT_INSERTMANYVALUES_MAX_PARAMETERS",
    "DEFAULT_SAFE_TYPES",
    "ExecutableOptions",
    "FilterableRepository",
    "FilterableRepositoryProtocol",
    "LoadCollection",
    "LoadSpec",
    "ModelRepositoryMixin",
    "SingleLoad",
    "WhereClauseT",
    "_UpsertPlanningMixin",
    "_build_cache_key",
    "column_has_defaults",
    "compare_values",
    "get_abstract_loader_options",
    "get_instrumented_attr",
    "get_primary_key_info",
    "has_upsert_update_intent",
    "model_from_dict",
    "resolve_generic_type_args",
    "snapshot_and_detach_relationships",
    "was_attribute_set",
)

WhereClauseT = ColumnExpressionArgument[bool]
SingleLoad: TypeAlias = Union[
    Load,
    Literal["*"],
    InstrumentedAttribute[Any],
    RelationshipProperty[Any],
    MapperProperty[Any],
]
LoadCollection: TypeAlias = Sequence[Union[SingleLoad, Sequence[SingleLoad]]]
ExecutableOptions: TypeAlias = Sequence[ExecutableOption]
LoadSpec: TypeAlias = Union[LoadCollection, SingleLoad, ExecutableOption, ExecutableOptions]


def _sort_kv_by_key_str(kv: tuple[object, object]) -> str:
    return str(kv[0])


def _sort_normalized_value(value: Any) -> str:
    return encode_json(_canonicalize_cache_key_value(value))


def _normalize_cache_key_value(value: Any) -> Any:
    """Normalize values into a deterministic JSON-serializable form.

    Used for list/list_and_count cache keys.
    """
    if value is None or isinstance(value, (int, float, str, bool)):
        return value

    # Try shared encoder first for scalars (datetime, uuid, bytes, etc)
    if (
        not isinstance(value, (list, tuple, set, frozenset, dict))
        and (encoded := encode_complex_type(value)) is not None
    ):
        return encoded

    if isinstance(value, set):
        value_set = cast("set[Any]", value)  # type: ignore[redundant-cast]
        normalized = [_normalize_cache_key_value(v) for v in value_set]
        normalized.sort(key=_sort_normalized_value)
        return normalized
    if isinstance(value, (list, tuple)):
        value_seq = cast("Sequence[Any]", value)
        return [_normalize_cache_key_value(v) for v in value_seq]
    if isinstance(value, dict):
        value_dict = cast("dict[object, object]", value)
        normalized_dict: dict[str, Any] = {}
        for k, v in sorted(value_dict.items(), key=_sort_kv_by_key_str):
            normalized_dict[str(k)] = _normalize_cache_key_value(v)
        return normalized_dict
    if dataclasses.is_dataclass(value) and not isinstance(value, type):  # pyright: ignore[reportUnknownArgumentType]
        return {
            field.name: _normalize_cache_key_value(getattr(value, field.name)) for field in dataclasses.fields(value)
        }
    if isinstance(value, InstrumentedAttribute):
        return {"__attr__": value.key}
    if isinstance(value, ColumnElement):
        value_expr = cast("ColumnElement[Any]", value)  # type: ignore[redundant-cast]
        return {"__sql__": str(value_expr)}

    return {"__repr__": repr(value)}  # pyright: ignore[reportUnknownArgumentType]


def _canonicalize_cache_key_value(value: Any) -> Any:
    """Convert dict-like objects into a stable, ordered representation."""
    if isinstance(value, Mapping):
        value_map = cast("Mapping[object, object]", value)
        return [
            [str(k), _canonicalize_cache_key_value(v)] for k, v in sorted(value_map.items(), key=_sort_kv_by_key_str)
        ]
    if isinstance(value, list):
        value_list = cast("list[Any]", value)  # type: ignore[redundant-cast]
        return [_canonicalize_cache_key_value(v) for v in value_list]
    return value


def _build_cache_key(  # pyright: ignore[reportUnusedFunction]
    *,
    model_name: str,
    version_token: str,
    method: str,
    filters: Sequence[Union[StatementFilter, ColumnElement[bool]]],
    kwargs: dict[str, Any],
    order_by: Optional[Union[list[OrderingPair], OrderingPair]],
    execution_options: dict[str, Any],
    uniquify: bool,
    count_with_window_function: Optional[bool] = None,
    bind_group: Optional[str] = None,
    include_deleted: bool = False,
) -> Optional[str]:
    """Build a stable cache key for list/list_and_count operations.

    Returns None if the query specification includes non-cacheable filter
    expressions (e.g., raw SQLAlchemy boolean expressions).
    """
    normalized_filters: list[dict[str, Any]] = []
    for filter_ in filters:
        if isinstance(filter_, ColumnElement):
            return None
        normalized_filters.append({"type": filter_.__class__.__name__, "data": _normalize_cache_key_value(filter_)})

    normalized_order_by: Optional[list[Any]] = None
    if order_by is not None:
        order_items = order_by if isinstance(order_by, list) else [order_by]
        normalized_order_by = []
        for item in order_items:
            if isinstance(item, UnaryExpression):
                normalized_order_by.append({"expr": str(item)})
            else:
                col, desc = item
                normalized_order_by.append({"col": _normalize_cache_key_value(col), "desc": bool(desc)})

    payload: dict[str, Any] = {
        "method": method,
        "model": model_name,
        "version": version_token,
        "filters": normalized_filters,
        "kwargs": _normalize_cache_key_value(kwargs),
        "order_by": normalized_order_by,
        "execution_options": _normalize_cache_key_value(execution_options),
        "uniquify": uniquify,
        "include_deleted": bool(include_deleted),
    }
    if count_with_window_function is not None:
        payload["count_with_window_function"] = bool(count_with_window_function)
    if bind_group is not None:
        payload["bind_group"] = bind_group

    try:
        encoded = encode_json(_canonicalize_cache_key_value(payload)).encode("utf-8")
    except TypeError:  # pragma: no cover
        return None

    digest = hashlib.sha256(encoded).hexdigest()
    return f"{model_name}:{method}:{digest}"


OrderByT: TypeAlias = Union[
    str,
    InstrumentedAttribute[Any],
    RelationshipProperty[Any],
]

# NOTE: For backward compatibility with Litestar - this is imported from here within the litestar codebase.
wrap_sqlalchemy_exception = _wrap_sqlalchemy_exception

DEFAULT_ERROR_MESSAGE_TEMPLATES: ErrorMessages = {
    "integrity": "There was a data validation error during processing",
    "foreign_key": "A foreign key is missing or invalid",
    "multiple_rows": "Multiple matching rows found",
    "duplicate_key": "A record matching the supplied data already exists.",
    "other": "There was an error during data processing",
    "check_constraint": "The data failed a check constraint during processing",
    "not_found": "The requested resource was not found",
}
"""Default error messages for repository errors."""


def get_instrumented_attr(
    model: type[ModelProtocol],
    key: Union[str, InstrumentedAttribute[Any]],
) -> InstrumentedAttribute[Any]:
    """Get an instrumented attribute from a model.

    Args:
        model: SQLAlchemy model class.
        key: Either a string attribute name or an :class:`sqlalchemy.orm.InstrumentedAttribute`.

    Returns:
        :class:`sqlalchemy.orm.InstrumentedAttribute`: The instrumented attribute from the model.
    """
    if isinstance(key, str):
        return cast("InstrumentedAttribute[Any]", getattr(model, key))
    return key


def get_primary_key_info(
    model: type[ModelProtocol],
) -> tuple[tuple["Column[Any]", ...], tuple[str, ...]]:
    """Extract primary key columns and attribute names from a SQLAlchemy model.

    This function safely inspects a model to retrieve its primary key information,
    handling cases where the model may not be properly mapped (e.g., mock objects
    in tests).

    Args:
        model: SQLAlchemy model class to inspect.

    Returns:
        A tuple of (pk_columns, pk_attr_names) where:
            - pk_columns: Tuple of Column objects representing the primary key
            - pk_attr_names: Tuple of ORM attribute names for the primary key columns

        Returns empty tuples if the model cannot be inspected (e.g., unmapped models).

    Example:
        >>> pk_columns, pk_attr_names = get_primary_key_info(UserRole)
        >>> # For a model with composite key (user_id, role_id):
        >>> # pk_columns = (Column('user_id', ...), Column('role_id', ...))
        >>> # pk_attr_names = ('user_id', 'role_id')
    """
    try:
        mapper = inspect(model)
    except NoInspectionAvailable:
        return (), ()
    else:
        pk_columns: tuple[Column[Any], ...] = tuple(mapper.primary_key)  # type: ignore[union-attr]
        pk_attr_names: tuple[str, ...] = tuple(
            mapper.get_property_by_column(col).key  # type: ignore[union-attr]
            for col in pk_columns
        )
        return pk_columns, pk_attr_names


def validate_composite_pk_value(
    pk_value: Any,
    pk_attr_names: tuple[str, ...],
    model_name: str,
) -> tuple[Any, ...]:
    """Validate and normalize a composite primary key value to a tuple.

    Args:
        pk_value: Primary key value (must be tuple or dict for composite PKs).
        pk_attr_names: Tuple of ORM attribute names for the PK columns.
        model_name: Model class name for error messages.

    Returns:
        Validated tuple of PK values in column order.

    Raises:
        TypeError: If pk_value is not a tuple or dict.
        ValueError: If tuple length is wrong, dict is missing keys, or any value is None.
    """
    num_pk_columns = len(pk_attr_names)

    if isinstance(pk_value, tuple):
        pk_tuple = cast("tuple[Any, ...]", pk_value)  # type: ignore[redundant-cast]
        if len(pk_tuple) != num_pk_columns:
            msg = (
                f"Composite primary key for {model_name} has "
                f"{num_pk_columns} columns {list(pk_attr_names)}, "
                f"but {len(pk_tuple)} values provided: {pk_tuple!r}"
            )
            raise ValueError(msg)
        # Validate no None values
        for i, val in enumerate(pk_tuple):
            if val is None:
                msg = f"Primary key value for '{pk_attr_names[i]}' cannot be None in composite key for {model_name}"
                raise ValueError(msg)
        return pk_tuple

    if isinstance(pk_value, dict):
        pk_dict = cast("dict[str, Any]", pk_value)
        provided_keys = set(pk_dict.keys())
        required_keys = set(pk_attr_names)
        missing_keys = required_keys - provided_keys
        if missing_keys:
            msg = (
                f"Composite primary key for {model_name} requires "
                f"attributes {sorted(required_keys)}, but missing: {sorted(missing_keys)}"
            )
            raise ValueError(msg)
        # Validate no None values and build tuple
        result_values: list[Any] = []
        for attr_name in pk_attr_names:
            val = pk_dict[attr_name]
            if val is None:
                msg = f"Primary key value for '{attr_name}' cannot be None in composite key for {model_name}"
                raise ValueError(msg)
            result_values.append(val)
        return tuple(result_values)

    # Not a valid type for composite PK
    pk_type_name = type(pk_value).__name__
    msg = (
        f"Composite primary key for {model_name} requires tuple or dict, "
        f"got {pk_type_name}: {pk_value!r}. Expected columns: {list(pk_attr_names)}"
    )
    raise TypeError(msg)


def is_composite_pk(pk_columns: tuple[Any, ...]) -> bool:
    """Check if a primary key has multiple columns.

    Args:
        pk_columns: Tuple of primary key Column objects.

    Returns:
        True if the model has 2 or more primary key columns, False otherwise.

    Example:
        >>> is_composite_pk(repo._pk_columns)  # Single PK model
        False
        >>> is_composite_pk(
        ...     repo._pk_columns
        ... )  # Model with (user_id, role_id) PK
        True
    """
    return len(pk_columns) > 1


def extract_pk_value_from_instance(
    instance: ModelProtocol,
    pk_attr_names: tuple[str, ...],
) -> PrimaryKeyType:
    """Extract the primary key value(s) from a model instance.

    Args:
        instance: Model instance to extract primary key from.
        pk_attr_names: Tuple of ORM attribute names for the PK columns.

    Returns:
        - For single PK: scalar value (int, str, UUID, etc.)
        - For composite PK: tuple of values in column order

    Example:
        # Single primary key
        >>> user = User(id=123, name="Alice")
        >>> extract_pk_value_from_instance(user, ("id",))
        123

        # Composite primary key
        >>> assignment = UserRole(user_id=1, role_id=5)
        >>> extract_pk_value_from_instance(
        ...     assignment, ("user_id", "role_id")
        ... )
        (1, 5)
    """
    if len(pk_attr_names) == 1:
        return getattr(instance, pk_attr_names[0])
    return tuple(getattr(instance, attr_name) for attr_name in pk_attr_names)


def pk_values_present(
    instance: ModelProtocol,
    pk_attr_names: tuple[str, ...],
) -> bool:
    """Check if all primary key values are set on an instance.

    Args:
        instance: Model instance to check.
        pk_attr_names: Tuple of ORM attribute names for the PK columns.

    Returns:
        True if all PK values are non-None, False otherwise.

    Example:
        >>> user = User(id=123)
        >>> pk_values_present(user, ("id",))
        True

        >>> user = User(id=None)
        >>> pk_values_present(user, ("id",))
        False
    """
    return all(getattr(instance, attr_name, None) is not None for attr_name in pk_attr_names)


def normalize_pk_to_tuple(
    pk_value: PrimaryKeyType,
    pk_attr_names: tuple[str, ...],
    model_name: str,
) -> tuple[Any, ...]:
    """Normalize a primary key value to tuple format.

    This function converts various PK input formats (scalar, tuple, dict) to
    a consistent tuple format for internal processing.

    Args:
        pk_value: Primary key value (scalar, tuple, or dict).
        pk_attr_names: Tuple of ORM attribute names for the PK columns.
        model_name: Model class name for error messages.

    Returns:
        Tuple representation of the primary key.

    Raises:
        ValueError: If composite PK is passed a scalar value.

    Example:
        # Single PK - wraps scalar in tuple
        >>> normalize_pk_to_tuple(123, ("id",), "User")
        (123,)

        # Composite PK - tuple passes through
        >>> normalize_pk_to_tuple(
        ...     (1, 5), ("user_id", "role_id"), "UserRole"
        ... )
        (1, 5)

        # Composite PK - dict converted to tuple
        >>> normalize_pk_to_tuple(
        ...     {"user_id": 1, "role_id": 5},
        ...     ("user_id", "role_id"),
        ...     "UserRole",
        ... )
        (1, 5)
    """
    if len(pk_attr_names) == 1:
        # Single PK - wrap scalar in tuple
        return (pk_value,)

    if isinstance(pk_value, tuple):
        return cast("tuple[Any, ...]", pk_value)  # type: ignore[redundant-cast]
    if isinstance(pk_value, dict):
        pk_dict = cast("dict[str, Any]", pk_value)
        return tuple(pk_dict[attr_name] for attr_name in pk_attr_names)

    # Scalar passed for composite PK - error
    pk_type_name = type(pk_value).__name__
    msg = f"Composite primary key for {model_name} requires tuple or dict, got {pk_type_name}: {pk_value!r}"
    raise ValueError(msg)


def _convert_relationship_value(
    value: Any,
    related_model: type[ModelT],
    is_collection: bool,
) -> Any:
    """Convert a relationship value, handling dicts, lists, and instances.

    Args:
        value: The value to convert (dict, list, model instance, or None).
        related_model: The SQLAlchemy model class for the relationship.
        is_collection: Whether this is a collection relationship (uselist=True).

    Returns:
        Converted value appropriate for the relationship type.
    """
    if value is None:
        return None

    if is_collection:
        # One-to-many or many-to-many: expect a list
        if not isinstance(value, (list, tuple)):
            # Single item provided for collection - wrap in list
            value = [value]
        return [
            model_from_dict(related_model, **item) if isinstance(item, dict) else item
            for item in value  # pyright: ignore[reportUnknownVariableType]
        ]
    # One-to-one or many-to-one: expect single value
    if isinstance(value, dict):
        return model_from_dict(related_model, **value)
    return value


def model_from_dict(model: type[ModelT], /, **kwargs: Any) -> ModelT:
    """Create an ORM model instance from a dictionary of attributes.

    This function recursively converts nested dictionaries into their
    corresponding SQLAlchemy model instances for relationship attributes.

    Args:
        model: The SQLAlchemy model class to instantiate.
        **kwargs: Keyword arguments containing model attribute values.
            For relationship attributes, values can be:
            - None: Sets the relationship to None
            - dict: Recursively converted to the related model instance
            - list[dict]: Each dict converted to related model instances
            - Model instance: Passed through unchanged

    Returns:
        ModelT: A new instance of the model populated with the provided values.

    Example:
        Basic usage with nested relationships::

            data = {
                "name": "John Doe",
                "profile": {"bio": "Developer"},
                "addresses": [
                    {"street": "123 Main St"},
                    {"street": "456 Oak Ave"},
                ],
            }
            user = model_from_dict(User, **data)
            # user.profile is a Profile instance
            # user.addresses is a list of Address instances
    """
    mapper = class_mapper(model)
    mapper_attrs = mapper.attrs
    converted_data: dict[str, Any] = {}

    # Iterate over kwargs instead of mapper.attrs for better performance
    # when only a subset of attributes is provided (O(InputKeys) vs O(TotalColumns))
    for key, value in kwargs.items():
        # Skip keys that aren't mapped attributes (e.g., extra fields)
        if key not in mapper_attrs:
            continue

        attr = mapper_attrs[key]

        # Check if this attribute is a relationship
        if isinstance(attr, RelationshipProperty):
            related_model: type[ModelT] = attr.mapper.class_
            converted_data[key] = _convert_relationship_value(
                value=value,
                related_model=related_model,
                is_collection=attr.uselist or False,
            )
        else:
            # Regular column attribute - pass through
            converted_data[key] = value

    return model(**converted_data)


def get_abstract_loader_options(
    loader_options: Union[LoadSpec, None],
    default_loader_options: Union[list[Load], None] = None,
    default_options_have_wildcards: bool = False,
    merge_with_default: bool = True,
    inherit_lazy_relationships: bool = True,
    cycle_count: int = 0,
) -> tuple[list[Load], bool]:
    """Generate SQLAlchemy loader options for eager loading relationships.

    Args:
        loader_options :class:`~advanced_alchemy.repository.typing.LoadSpec`|:class:`None`  Specification for how to load relationships. Can be:
            - None: Use defaults
            - :class:`sqlalchemy.orm.Load`: Direct SQLAlchemy loader option
            - :class:`sqlalchemy.orm.InstrumentedAttribute`: Model relationship attribute
            - :class:`sqlalchemy.orm.RelationshipProperty`: SQLAlchemy relationship
            - str: "*" for wildcard loading
            - :class:`typing.Sequence` of the above
        default_loader_options: :class:`typing.Sequence` of :class:`sqlalchemy.orm.Load` loader options to start with.
        default_options_have_wildcards: Whether the default options contain wildcards.
        merge_with_default: Whether to merge the default options with the loader options.
        inherit_lazy_relationships: Whether to inherit the ``lazy`` configuration from the model's relationships.
        cycle_count: Number of times this function has been called recursively.

    Returns:
        tuple[:class:`list`[:class:`sqlalchemy.orm.Load`], bool]: A tuple containing:
            - :class:`list` of :class:`sqlalchemy.orm.Load` SQLAlchemy loader option objects
            - Boolean indicating if any wildcard loaders are present
    """
    loads: list[Load] = []
    if cycle_count == 0 and not inherit_lazy_relationships:
        loads.append(cast("Load", lazyload("*")))
    if cycle_count == 0 and merge_with_default and default_loader_options is not None:
        loads.extend(default_loader_options)
    options_have_wildcards = default_options_have_wildcards
    if loader_options is None:
        return (loads, options_have_wildcards)
    if isinstance(loader_options, Load):
        return ([loader_options], options_have_wildcards)
    if isinstance(loader_options, InstrumentedAttribute):
        loader_options = [loader_options.property]
    if isinstance(loader_options, RelationshipProperty):
        class_ = loader_options.class_attribute
        return (
            [cast("Load", selectinload(class_))]
            if loader_options.uselist
            else [cast("Load", joinedload(class_, innerjoin=loader_options.innerjoin))],
            options_have_wildcards if loader_options.uselist else True,
        )
    if isinstance(loader_options, str) and loader_options == "*":
        options_have_wildcards = True
        return ([cast("Load", joinedload("*"))], options_have_wildcards)
    if isinstance(loader_options, (list, tuple)):
        for attribute in loader_options:  # pyright: ignore[reportUnknownVariableType]
            if isinstance(attribute, (list, tuple)):
                load_chain, options_have_wildcards = get_abstract_loader_options(
                    loader_options=attribute,  # pyright: ignore[reportUnknownArgumentType]
                    default_options_have_wildcards=options_have_wildcards,
                    inherit_lazy_relationships=inherit_lazy_relationships,
                    merge_with_default=merge_with_default,
                    cycle_count=cycle_count + 1,
                )
                loader = load_chain[-1]
                for sub_load in load_chain[-2::-1]:
                    loader = sub_load.options(loader)
                loads.append(loader)
            else:
                load_chain, options_have_wildcards = get_abstract_loader_options(
                    loader_options=attribute,  # pyright: ignore[reportUnknownArgumentType]
                    default_options_have_wildcards=options_have_wildcards,
                    inherit_lazy_relationships=inherit_lazy_relationships,
                    merge_with_default=merge_with_default,
                    cycle_count=cycle_count + 1,
                )
                loads.extend(load_chain)
    return (loads, options_have_wildcards)


def resolve_generic_type_args(cls: type[Any], target_origin: type[Any]) -> tuple[Any, ...]:
    """Extract concrete generic type arguments for ``target_origin`` from ``cls.__mro__``.

    Args:
        cls: The subclass being inspected.
        target_origin: The generic base class or protocol to match.

    Returns:
        Tuple of type arguments from the first matching generic base with concrete arguments.
    """
    for current_cls in cls.__mro__:
        for base in getattr(current_cls, "__orig_bases__", ()):
            origin = get_origin(base)
            if origin is not None and isinstance(origin, type) and issubclass(origin, target_origin):
                args = get_args(base)
                if args and any(isinstance(arg, type) or isinstance(get_origin(arg), type) for arg in args):
                    return args
    return ()


class FilterableRepositoryProtocol(Protocol[ModelT]):
    """Protocol defining the interface for filterable repositories.

    This protocol defines the required attributes and methods that any
    filterable repository implementation must provide.
    """

    model_type: type[ModelT]
    """The SQLAlchemy model class this repository manages."""


class ModelRepositoryMixin(FilterableRepositoryProtocol[ModelT], Generic[ModelT]):
    """Shared model metadata, primary-key introspection, and attribute helpers for repositories."""

    model_type: type[ModelT]
    """The SQLAlchemy model class this repository manages."""
    id_attribute: Any = "id"
    """Name of the unique identifier for the model."""
    match_fields: Optional[Union[list[str], str]] = None
    """Default fields used for matching existing instances during upsert operations."""
    error_messages: Optional[ErrorMessages] = None
    """Default error messages for the repository."""
    wrap_exceptions: bool = True
    """Wrap SQLAlchemy exceptions in a ``RepositoryError``."""
    include_deleted: bool = False
    """Include soft-deleted records (`SoftDeleteMixin`) in read queries by default."""
    _pk_columns: tuple[Column[Any], ...] = ()
    _pk_attr_names: tuple[str, ...] = ()

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if "model_type" not in cls.__dict__:
            args = resolve_generic_type_args(cls, ModelRepositoryMixin)
            if args and isinstance(args[0], type):
                cls.model_type = cast("type[ModelT]", args[0])

    @property
    def _has_soft_delete(self) -> bool:
        """Return ``True`` when ``self.model_type`` subclasses :class:`SoftDeleteMixin`."""
        model_cls = getattr(self, "model_type", None)
        return isinstance(model_cls, type) and issubclass(model_cls, SoftDeleteMixin)

    def _resolve_include_deleted(self, include_deleted: Optional[bool] = None) -> bool:
        """Resolve the ``include_deleted`` flag, preferring the method parameter over instance default."""
        return bool(self.include_deleted if include_deleted is None else include_deleted)

    def _should_filter_soft_deleted(self, include_deleted: Optional[bool] = None) -> bool:
        """Return ``True`` when soft-deleted rows should be excluded from a query."""
        return self._has_soft_delete and not self._resolve_include_deleted(include_deleted)

    def _require_soft_delete(self, operation: Optional[str] = None) -> None:
        """Raise :exc:`ImproperConfigurationError` if ``self.model_type`` does not inherit :class:`SoftDeleteMixin`."""
        _ = operation
        if not self._has_soft_delete:
            model_name = getattr(getattr(self, "model_type", None), "__name__", str(getattr(self, "model_type", None)))
            msg = f"Model {model_name} does not inherit from SoftDeleteMixin"
            raise ImproperConfigurationError(msg)

    def _requires_orm_delete(self) -> bool:
        """Return ``True`` if ``self.model_type`` requires ORM ``session.delete()`` instead of bulk ``DELETE``."""
        model_cls = getattr(self, "model_type", None)
        if not isinstance(model_cls, type):
            return False
        try:
            mapper: Mapper[Any] = class_mapper(model_cls)
        except (NoInspectionAvailable, ValueError, TypeError):
            return False
        if len(mapper.tables) > 1:
            return True
        if any(isinstance(col.type, StoredObject) for col in mapper.columns):
            return True
        if any("delete" in rel.cascade and not rel.passive_deletes for rel in mapper.relationships):
            return True
        dispatch_obj: Any = mapper.dispatch
        before_delete_listeners: Iterable[Any] = getattr(dispatch_obj, "before_delete", ())
        after_delete_listeners: Iterable[Any] = getattr(dispatch_obj, "after_delete", ())
        custom_listeners: list[Any] = [
            fn
            for fn in (*before_delete_listeners, *after_delete_listeners)
            if not getattr(fn, "__module__", "").startswith("advanced_alchemy.")
        ]
        return bool(custom_listeners)

    @classmethod
    def _iter_cascaded_soft_delete_children(cls, instance: Any) -> list[Any]:
        """Return loaded :class:`SoftDeleteMixin` child instances on cascade-configured relationships."""
        try:
            state = inspect(instance)
        except NoInspectionAvailable:
            return []
        if state is None:
            return []
        children: list[Any] = []
        for rel in state.mapper.relationships:
            if not ("delete" in rel.cascade or rel.info.get("soft_delete_cascade") is True):
                continue
            target_cls = rel.mapper.class_
            if not (isinstance(target_cls, type) and issubclass(target_cls, SoftDeleteMixin)):
                continue
            if rel.key not in state.dict:
                continue
            rel_value = state.dict.get(rel.key)
            if rel_value is None:
                continue
            if isinstance(rel_value, (list, tuple, set)):
                children.extend(
                    child for child in cast("Iterable[Any]", rel_value) if isinstance(child, SoftDeleteMixin)
                )
            elif isinstance(rel_value, SoftDeleteMixin):
                children.append(rel_value)
        return children

    @classmethod
    def _apply_soft_delete_to_instance(
        cls,
        instance: Any,
        deleted_at: Optional[datetime.datetime] = None,
        *,
        cascade: bool = True,
        visited: Optional[set[int]] = None,
    ) -> None:
        """Mark ``instance`` (and active cascaded :class:`SoftDeleteMixin` children when ``cascade=True``) deleted."""
        if visited is None:
            visited = set()
        obj_id = id(instance)
        if obj_id in visited:
            return
        visited.add(obj_id)
        effective_deleted_at = deleted_at or datetime.datetime.now(datetime.timezone.utc)
        if isinstance(instance, SoftDeleteMixin) and instance.deleted_at is None:
            instance.mark_deleted(effective_deleted_at)
        if cascade:
            for child in cls._iter_cascaded_soft_delete_children(instance):
                cls._apply_soft_delete_to_instance(
                    child,
                    deleted_at=effective_deleted_at,
                    cascade=cascade,
                    visited=visited,
                )

    @classmethod
    def _apply_restore_to_instance(
        cls,
        instance: Any,
        *,
        parent_deleted_at: Optional[datetime.datetime] = None,
        cascade: bool = True,
        visited: Optional[set[int]] = None,
    ) -> None:
        """Restore ``instance`` (and cascaded :class:`SoftDeleteMixin` children deleted at or after ``parent_deleted_at``)."""
        if visited is None:
            visited = set()
        obj_id = id(instance)
        if obj_id in visited:
            return
        visited.add(obj_id)
        effective_parent_ts = parent_deleted_at
        if isinstance(instance, SoftDeleteMixin):
            if effective_parent_ts is None:
                effective_parent_ts = instance.deleted_at
            instance.restore()
        if cascade:
            for child in cls._iter_cascaded_soft_delete_children(instance):
                child_deleted_at = getattr(child, "deleted_at", None)
                if child_deleted_at is not None and (
                    effective_parent_ts is None or child_deleted_at >= effective_parent_ts
                ):
                    cls._apply_restore_to_instance(
                        child,
                        parent_deleted_at=effective_parent_ts,
                        cascade=cascade,
                        visited=visited,
                    )

    def _ensure_pk_info(self) -> tuple[tuple[Column[Any], ...], tuple[str, ...]]:
        """Ensure primary key column and attribute tuples are initialized for ``self.model_type``."""
        pk_columns = self.__dict__.get("_pk_columns")
        pk_attr_names = self.__dict__.get("_pk_attr_names")
        if pk_columns is None or pk_attr_names is None:
            model_cls = getattr(self, "model_type", None)
            if model_cls is not None:
                pk_columns, pk_attr_names = get_primary_key_info(model_cls)
            else:
                pk_columns, pk_attr_names = (), ()
            self._pk_columns = pk_columns
            self._pk_attr_names = pk_attr_names
        return pk_columns, pk_attr_names

    @property
    def pk_attr_names(self) -> tuple[str, ...]:
        """Get primary key attribute names.

        Returns:
            Tuple of ORM attribute names for primary key columns.
        """
        return self._ensure_pk_info()[1]

    @property
    def has_composite_pk(self) -> bool:
        """Check if model has a composite (multi-column) primary key.

        Returns:
            True if the model has 2 or more primary key columns, False otherwise.
        """
        return is_composite_pk(self._ensure_pk_info()[0])

    def get_primary_key_value(self, instance: ModelT) -> PrimaryKeyType:
        """Extract the primary key value(s) from a model instance.

        Args:
            instance: Model instance to extract primary key from.

        Returns:
            Scalar value for single PK, or tuple of values in column order for composite PK.
        """
        return extract_pk_value_from_instance(instance, self.pk_attr_names)

    def has_primary_key_values(self, instance: ModelT) -> bool:
        """Check if all primary key values are set on an instance.

        Args:
            instance: Model instance to check.

        Returns:
            True if all PK values are non-None, False otherwise.
        """
        return pk_values_present(instance, self.pk_attr_names)

    def set_primary_key_value(self, instance: ModelT, pk_value: PrimaryKeyType) -> ModelT:
        """Set the primary key value(s) on a model instance.

        Args:
            instance: Model instance to update.
            pk_value: Scalar PK value, or tuple/dict for composite PKs.

        Returns:
            The updated model instance.
        """
        pk_attr_names = self.pk_attr_names
        if self.has_composite_pk:
            pk_tuple = validate_composite_pk_value(pk_value, pk_attr_names, self.model_type.__name__)
            for attr_name, val in zip(pk_attr_names, pk_tuple):
                setattr(instance, attr_name, val)
            return instance
        if pk_attr_names:
            setattr(instance, pk_attr_names[0], pk_value)
            return instance
        return self.set_id_attribute_value(pk_value, instance)

    def _normalize_pk_to_tuple(self, pk_value: PrimaryKeyType) -> tuple[Any, ...]:
        """Normalize a primary key value to a tuple for consistent storage key generation."""
        return normalize_pk_to_tuple(pk_value, self.pk_attr_names, self.model_type.__name__)

    def _normalize_pk_values_to_tuples(self, item_ids: list[PrimaryKeyType]) -> list[tuple[Any, ...]]:
        """Normalize a list of composite primary key values to tuples."""
        pk_attr_names = self.pk_attr_names
        model_name = self.model_type.__name__
        return [validate_composite_pk_value(pk_value, pk_attr_names, model_name) for pk_value in item_ids]

    def _build_pk_filter(self, pk_value: PrimaryKeyType) -> ColumnElement[bool]:
        """Build a WHERE clause for primary key lookup."""
        pk_columns, pk_attr_names = self._ensure_pk_info()
        if len(pk_columns) == 0:
            id_attr = get_instrumented_attr(self.model_type, self.id_attribute)
            result: ColumnElement[bool] = id_attr == pk_value
            return result
        if len(pk_columns) == 1:
            if isinstance(pk_value, tuple):
                msg = (
                    f"Model {self.model_type.__name__} has a single primary key column '{pk_attr_names[0]}'. "
                    f"Expected a scalar value, got tuple: {pk_value!r}"
                )
                raise ValueError(msg)
            if isinstance(pk_value, dict):
                msg = (
                    f"Model {self.model_type.__name__} has a single primary key column '{pk_attr_names[0]}'. "
                    f"Expected a scalar value, got dict: {pk_value!r}"
                )
                raise ValueError(msg)
            single_pk_result: ColumnElement[bool] = pk_columns[0] == pk_value
            return single_pk_result
        pk_tuple = validate_composite_pk_value(pk_value, pk_attr_names, self.model_type.__name__)
        return and_(*[col == val for col, val in zip(pk_columns, pk_tuple)])

    def _get_object_ids(self, existing_objs: Sequence[ModelT]) -> list[PrimaryKeyType]:
        """Extract primary key values from a sequence of model instances."""
        return [self.get_primary_key_value(datum) for datum in existing_objs if self.has_primary_key_values(datum)]

    def _get_match_fields(
        self,
        match_fields: Optional[Union[list[str], str]] = None,
        id_attribute: Optional[str] = None,
    ) -> Optional[list[str]]:
        """Resolve match_fields from method argument or repository default."""
        id_attribute = id_attribute or self.id_attribute
        match_fields = match_fields or self.match_fields
        if isinstance(match_fields, str):
            match_fields = [match_fields]
        return match_fields

    @staticmethod
    def _get_error_messages(
        error_messages: Optional[Union[ErrorMessages, EmptyType]] = Empty,
        default_messages: Optional[Union[ErrorMessages, EmptyType]] = Empty,
    ) -> Optional[ErrorMessages]:
        """Merge default and per-call error message templates."""
        if error_messages is Empty or error_messages is None:
            if isinstance(default_messages, dict) and all(
                key in default_messages for key in DEFAULT_ERROR_MESSAGE_TEMPLATES
            ):
                return default_messages
            error_messages = None
        if default_messages == Empty:
            default_messages = None
        messages = cast("ErrorMessages", dict(DEFAULT_ERROR_MESSAGE_TEMPLATES))
        if default_messages and isinstance(default_messages, dict):
            messages.update(default_messages)
        if error_messages:
            messages.update(cast("ErrorMessages", error_messages))  # type: ignore[unused-ignore,redundant-cast]
        return messages

    @classmethod
    def get_id_attribute_value(
        cls,
        item: Union[ModelT, type[ModelT]],
        id_attribute: Optional[Union[str, InstrumentedAttribute[Any]]] = None,
    ) -> Any:
        """Get value of attribute named as :attr:`id_attribute` on ``item``.

        Args:
            item: Anything that should have an attribute named as :attr:`id_attribute` value.
            id_attribute: Allows customization of the unique identifier to use for model fetching.
                Defaults to `None`, but can reference any surrogate or candidate key for the table.

        Returns:
            The value of attribute on ``item`` named as :attr:`id_attribute`.
        """
        if isinstance(id_attribute, InstrumentedAttribute):
            id_attribute = id_attribute.key
        return getattr(item, id_attribute if id_attribute is not None else cls.id_attribute)

    @classmethod
    def set_id_attribute_value(
        cls,
        item_id: Any,
        item: ModelT,
        id_attribute: Optional[Union[str, InstrumentedAttribute[Any]]] = None,
    ) -> ModelT:
        """Return the ``item`` after the ID is set to the appropriate attribute.

        Args:
            item_id: Value of ID to be set on instance
            item: Anything that should have an attribute named as :attr:`id_attribute` value.
            id_attribute: Allows customization of the unique identifier to use for model fetching.
                Defaults to `None`, but can reference any surrogate or candidate key for the table.

        Returns:
            Item with ``item_id`` set to :attr:`id_attribute`
        """
        if isinstance(id_attribute, InstrumentedAttribute):
            id_attribute = id_attribute.key
        setattr(item, id_attribute if id_attribute is not None else cls.id_attribute, item_id)
        return item

    @staticmethod
    def check_not_found(item_or_none: Optional[ModelT]) -> ModelT:
        """Raise :exc:`advanced_alchemy.exceptions.NotFoundError` if ``item_or_none`` is ``None``.

        Args:
            item_or_none: Item (:class:`T <T>`) to be tested for existence.

        Raises:
            NotFoundError: If ``item_or_none`` is ``None``

        Returns:
            The item, if it exists.
        """
        if item_or_none is None:
            msg = "No item found when one was expected"
            raise NotFoundError(msg)
        return item_or_none


class FilterableRepository(
    ModelRepositoryMixin[ModelT],
    _UpsertPlanningMixin[ModelT],
    FilterableRepositoryProtocol[ModelT],
):
    """Default implementation of a filterable repository.

    Provides core filtering, ordering and pagination functionality for
    SQLAlchemy models.
    """

    model_type: type[ModelT]
    """The SQLAlchemy model class this repository manages."""
    prefer_any_dialects: Optional[tuple[str]] = ("postgresql",)
    """List of dialects that prefer to use ``field.id = ANY(:1)`` instead of ``field.id IN (...)``."""
    order_by: Optional[Union[list[OrderingPair], OrderingPair]] = None
    """List or single :class:`~advanced_alchemy.repository.typing.OrderingPair` to use for sorting."""
    _prefer_any: bool = False
    """Whether to prefer ANY() over IN() in queries."""
    _dialect: Dialect
    """The SQLAlchemy :class:`sqlalchemy.dialects.Dialect` being used."""

    @overload
    def _apply_filters(
        self,
        *filters: Union[StatementFilter, ColumnElement[bool]],
        apply_pagination: bool = True,
        statement: Select[tuple[ModelT]],
    ) -> Select[tuple[ModelT]]: ...

    @overload
    def _apply_filters(
        self,
        *filters: Union[StatementFilter, ColumnElement[bool]],
        apply_pagination: bool = True,
        statement: Delete,
    ) -> Delete: ...

    @overload
    def _apply_filters(
        self,
        *filters: Union[StatementFilter, ColumnElement[bool]],
        apply_pagination: bool = True,
        statement: Union[ReturningDelete[tuple[ModelT]], ReturningUpdate[tuple[ModelT]]],
    ) -> Union[ReturningDelete[tuple[ModelT]], ReturningUpdate[tuple[ModelT]]]: ...

    @overload
    def _apply_filters(
        self,
        *filters: Union[StatementFilter, ColumnElement[bool]],
        apply_pagination: bool = True,
        statement: Update,
    ) -> Update: ...

    def _apply_filters(
        self,
        *filters: Union[StatementFilter, ColumnElement[bool]],
        apply_pagination: bool = True,
        statement: StatementTypeT,
    ) -> StatementTypeT:
        """Apply filters to a SQL statement.

        Args:
            *filters: Filter conditions to apply.
            apply_pagination: Whether to apply pagination filters.
            statement: The base SQL statement to filter.

        Returns:
            StatementTypeT: The filtered SQL statement.
        """
        for filter_ in filters:
            if isinstance(filter_, (PaginationFilter,)):
                if apply_pagination:
                    statement = filter_.append_to_statement(statement, self.model_type)
            elif isinstance(filter_, (InAnyFilter,)):
                statement = filter_.append_to_statement(statement, self.model_type, prefer_any=self._prefer_any)
            elif isinstance(filter_, ColumnElement):
                statement = cast("StatementTypeT", statement.where(filter_))
            else:
                statement = filter_.append_to_statement(statement, self.model_type)
        return statement

    def _filter_select_by_kwargs(
        self,
        statement: StatementTypeT,
        kwargs: Union[dict[Any, Any], Iterable[tuple[Any, Any]]],
    ) -> StatementTypeT:
        """Filter a statement using keyword arguments.

        Args:
            statement: :class:`sqlalchemy.sql.Select` The SQL statement to filter.
            kwargs: Dictionary or iterable of tuples containing filter criteria.
                Keys should be model attribute names, values are what to filter for.

        Returns:
            StatementTypeT: The filtered SQL statement.
        """
        if isinstance(kwargs, dict):
            for key, val in kwargs.items():  # pyright: ignore[reportUnknownVariableType]
                field = get_instrumented_attr(self.model_type, key)  # pyright: ignore[reportArgumentType]
                statement = cast("StatementTypeT", statement.where(field == val))  # pyright: ignore[reportUnknownArgumentType]
        else:
            for key, val in kwargs:
                field = get_instrumented_attr(self.model_type, key)
                statement = cast("StatementTypeT", statement.where(field == val))
        return statement

    def _apply_order_by(
        self,
        statement: StatementTypeT,
        order_by: Union[
            OrderingPair,
            list[OrderingPair],
        ],
    ) -> StatementTypeT:
        """Apply ordering to a SQL statement.

        Args:
            statement: The SQL statement to order.
            order_by: Ordering specification. Either a single tuple or list of tuples where:
                - First element is the field name or :class:`sqlalchemy.orm.InstrumentedAttribute` to order by
                - Second element is a boolean indicating descending (True) or ascending (False)

        Returns:
            StatementTypeT: The ordered SQL statement.
        """
        if not isinstance(order_by, list):
            order_by = [order_by]
        for order_field in order_by:
            if isinstance(order_field, UnaryExpression):
                statement = statement.order_by(order_field)  # type: ignore
            else:
                field = get_instrumented_attr(self.model_type, order_field[0])
                statement = self._order_by_attribute(statement, field, order_field[1])
        return statement

    @staticmethod
    def _order_by_attribute(
        statement: StatementTypeT,
        field: InstrumentedAttribute[Any],
        is_desc: bool,
    ) -> StatementTypeT:
        """Apply ordering by a single attribute to a SQL statement.

        Args:
            statement: The SQL statement to order.
            field: The model attribute to order by.
            is_desc: Whether to order in descending (True) or ascending (False) order.

        Returns:
            StatementTypeT: The ordered SQL statement.
        """
        if isinstance(statement, Select):
            statement = cast("StatementTypeT", statement.order_by(field.desc() if is_desc else field.asc()))
        return statement


def column_has_defaults(column: Any) -> bool:
    """Check if a column has any type of default value or update handler.

    This includes:
    - Python-side defaults (column.default)
    - Server-side defaults (column.server_default)
    - Python-side onupdate handlers (column.onupdate)
    - Server-side onupdate handlers (column.server_onupdate)

    Args:
        column: SQLAlchemy column object to check

    Returns:
        bool: True if the column has any type of default or update handler
    """
    if isinstance(column, Label):
        return False
    return (
        getattr(column, "default", None) is not None
        or getattr(column, "server_default", None) is not None
        or getattr(column, "onupdate", None) is not None
        or getattr(column, "server_onupdate", None) is not None
    )


def snapshot_and_detach_relationships(instance: Any, mapper: Any) -> dict[str, Any]:
    """Capture explicitly-set relationship values on ``instance`` and undo any
    backref pollution those assignments caused on already-persistent related objects.

    A common ``to_model_on_update`` pattern builds a transient instance and assigns
    already-persistent related objects (or a collection of them) to one of its
    relationships, purely so the caller can copy that value onto the real,
    session-attached instance afterwards. Because ``back_populates``/``backref``
    synchronization is a Python-side event that fires regardless of session state,
    the transient instance still gets appended into the related object's own
    collection - even though it is never added to the session. The next autoflush
    then tries to write that pairing, fails because the transient side has no
    identity, and emits ``SAWarning: ... not in session ...`` for it.

    This snapshots each explicitly-set relationship value before removing
    ``instance`` from the corresponding back-populated collection/attribute on
    every already-persistent related object, so the stale pairing never reaches a
    flush. Only relationships declared with ``back_populates`` on a transient
    ``instance`` are touched; persistent instances and one-directional
    relationships are left untouched.

    Args:
        instance: The (possibly transient) instance to inspect.
        mapper: The SQLAlchemy instance-state/mapper for ``instance``.

    Returns:
        A mapping of relationship name to the value that was explicitly set on
        ``instance``, captured before any backref cleanup.
    """
    values: dict[str, Any] = {}
    is_transient = object_session(instance) is None
    for relationship in mapper.mapper.relationships:
        if not was_attribute_set(instance, mapper, relationship.key):
            continue
        raw_value: Any = instance.__dict__.get(relationship.key)
        related_items: list[Any]
        if isinstance(raw_value, Mapping):
            mapping = cast("dict[Any, Any]", raw_value)
            values[relationship.key] = dict(mapping)
            related_items = list(mapping.values())
        elif isinstance(raw_value, (list, set)):
            items = cast("Iterable[Any]", raw_value)
            values[relationship.key] = list(items)
            related_items = list(items)
        else:
            values[relationship.key] = raw_value
            related_items = [raw_value]

        back_attr = relationship.back_populates
        if not is_transient or not back_attr or raw_value is None:
            continue
        for related in related_items:
            related_state: Any = inspect(related, raiseerr=False)  # pyright: ignore[reportUnknownVariableType]
            if related is None or related_state is None:
                continue
            back_value: Any = related.__dict__.get(back_attr)
            if isinstance(back_value, (list, set)) and instance in back_value:
                cast("Any", back_value).remove(instance)
            elif back_value is instance:
                setattr(related, back_attr, None)
            else:
                pending: Any = getattr(related_state, "_pending_mutations", None)  # pyright: ignore[reportUnknownArgumentType]
                added_items: Any = getattr(pending.get(back_attr), "added_items", None) if pending else None
                if added_items is not None and instance in added_items:
                    added_items.discard(instance)
    return values
