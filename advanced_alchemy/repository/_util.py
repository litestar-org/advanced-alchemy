# ruff: noqa: PLR0911
import contextlib
import dataclasses
import datetime
import decimal
import hashlib
from collections.abc import Iterable, Mapping, Sequence
from typing import Any, Final, Literal, Optional, Protocol, Union, cast, overload

from sqlalchemy import (
    Column,
    Delete,
    Dialect,
    Select,
    Table,
    UnaryExpression,
    Update,
    and_,
    any_,
    inspect,
    or_,
    tuple_,
)
from sqlalchemy.exc import NoInspectionAvailable
from sqlalchemy.orm import (
    InstrumentedAttribute,
    MapperProperty,
    RelationshipProperty,
    class_mapper,
    joinedload,
    lazyload,
    selectinload,
)
from sqlalchemy.orm.strategy_options import (
    _AbstractLoad,  # pyright: ignore[reportPrivateUsage]
)
from sqlalchemy.sql import ColumnElement, ColumnExpressionArgument
from sqlalchemy.sql.base import ExecutableOption
from sqlalchemy.sql.dml import ReturningDelete, ReturningUpdate
from sqlalchemy.sql.elements import Label
from typing_extensions import TypeAlias

from advanced_alchemy.base import ModelProtocol, model_to_dict
from advanced_alchemy.exceptions import ErrorMessages, RepositoryError
from advanced_alchemy.exceptions import wrap_sqlalchemy_exception as _wrap_sqlalchemy_exception
from advanced_alchemy.filters import (
    InAnyFilter,
    PaginationFilter,
    StatementFilter,
    StatementTypeT,
)
from advanced_alchemy.operations import UpsertStrategy, resolve_column_default
from advanced_alchemy.repository._typing import arrays_equal, is_numpy_array
from advanced_alchemy.repository.typing import MISSING, ModelT, OrderingPair, PrimaryKeyType
from advanced_alchemy.utils.serialization import encode_complex_type, encode_json

DEFAULT_INSERTMANYVALUES_MAX_PARAMETERS: Final = 950

DEFAULT_SAFE_TYPES: Final[set[type[Any]]] = {
    int,
    float,
    str,
    bool,
    bytes,
    decimal.Decimal,
    datetime.date,
    datetime.datetime,
    datetime.time,
    datetime.timedelta,
}

WhereClauseT = ColumnExpressionArgument[bool]
SingleLoad: TypeAlias = Union[
    _AbstractLoad,
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
        return _normalize_cache_key_value(dataclasses.asdict(value))
    if isinstance(value, InstrumentedAttribute):
        return {"__attr__": value.key}
    if isinstance(value, ColumnElement):
        # Safe fallback for non-dataclass expressions in ordering/kwargs.
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
    }
    if count_with_window_function is not None:
        payload["count_with_window_function"] = bool(count_with_window_function)

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
    default_loader_options: Union[list[_AbstractLoad], None] = None,
    default_options_have_wildcards: bool = False,
    merge_with_default: bool = True,
    inherit_lazy_relationships: bool = True,
    cycle_count: int = 0,
) -> tuple[list[_AbstractLoad], bool]:
    """Generate SQLAlchemy loader options for eager loading relationships.

    Args:
        loader_options :class:`~advanced_alchemy.repository.typing.LoadSpec`|:class:`None`  Specification for how to load relationships. Can be:
            - None: Use defaults
            - :class:`sqlalchemy.orm.strategy_options._AbstractLoad`: Direct SQLAlchemy loader option
            - :class:`sqlalchemy.orm.InstrumentedAttribute`: Model relationship attribute
            - :class:`sqlalchemy.orm.RelationshipProperty`: SQLAlchemy relationship
            - str: "*" for wildcard loading
            - :class:`typing.Sequence` of the above
        default_loader_options: :class:`typing.Sequence` of :class:`sqlalchemy.orm.strategy_options._AbstractLoad` loader options to start with.
        default_options_have_wildcards: Whether the default options contain wildcards.
        merge_with_default: Whether to merge the default options with the loader options.
        inherit_lazy_relationships: Whether to inherit the ``lazy`` configuration from the model's relationships.
        cycle_count: Number of times this function has been called recursively.

    Returns:
        tuple[:class:`list`[:class:`sqlalchemy.orm.strategy_options._AbstractLoad`], bool]: A tuple containing:
            - :class:`list` of :class:`sqlalchemy.orm.strategy_options._AbstractLoad` SQLAlchemy loader option objects
            - Boolean indicating if any wildcard loaders are present
    """
    loads: list[_AbstractLoad] = []
    if cycle_count == 0 and not inherit_lazy_relationships:
        loads.append(lazyload("*"))
    if cycle_count == 0 and merge_with_default and default_loader_options is not None:
        loads.extend(default_loader_options)
    options_have_wildcards = default_options_have_wildcards
    if loader_options is None:
        return (loads, options_have_wildcards)
    if isinstance(loader_options, _AbstractLoad):
        return ([loader_options], options_have_wildcards)
    if isinstance(loader_options, InstrumentedAttribute):
        loader_options = [loader_options.property]
    if isinstance(loader_options, RelationshipProperty):
        class_ = loader_options.class_attribute
        return (
            [selectinload(class_)]
            if loader_options.uselist
            else [joinedload(class_, innerjoin=loader_options.innerjoin)],
            options_have_wildcards if loader_options.uselist else True,
        )
    if isinstance(loader_options, str) and loader_options == "*":
        options_have_wildcards = True
        return ([joinedload("*")], options_have_wildcards)
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


class FilterableRepositoryProtocol(Protocol[ModelT]):
    """Protocol defining the interface for filterable repositories.

    This protocol defines the required attributes and methods that any
    filterable repository implementation must provide.
    """

    model_type: type[ModelT]
    """The SQLAlchemy model class this repository manages."""


class FilterableRepository(FilterableRepositoryProtocol[ModelT]):
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
                statement = filter_.append_to_statement(statement, self.model_type)
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
        for key, val in dict(kwargs).items():
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

    def _type_must_use_in_instead_of_any(self, matched_values: Sequence[Any], field_type: Any = None) -> bool:
        """Determine if ``field.in_()`` should be used instead of ``any_()`` for compatibility.

        Uses SQLAlchemy's type introspection to detect types that may have DBAPI
        serialization issues with the ``ANY()`` operator. Checks if actual values match
        the column's expected ``python_type``; mismatches indicate complex types that
        need the safer ``IN()`` operator. Falls back to Python type checking when
        SQLAlchemy type information is unavailable.

        Args:
            matched_values: Values to be used in the filter.
            field_type: Optional SQLAlchemy TypeEngine from the column.

        Returns:
            bool: True if ``field.in_()`` should be used instead of ``any_()``.
        """
        if not matched_values:
            return False

        if field_type is not None:
            try:
                expected_python_type = getattr(field_type, "python_type", None)
                if expected_python_type is not None:
                    for value in matched_values:
                        if value is not None and not isinstance(value, expected_python_type):
                            return True
            except (AttributeError, NotImplementedError):
                return True

        return any(value is not None and type(value) not in DEFAULT_SAFE_TYPES for value in matched_values)

    def _get_insertmanyvalues_max_parameters(self, chunk_size: Optional[int] = None) -> int:
        if chunk_size is not None:
            if chunk_size < 1:
                msg = "chunk_size must be greater than zero"
                raise ValueError(msg)
            return chunk_size
        dialect_limit = getattr(self._dialect, "insertmanyvalues_max_parameters", None)
        if isinstance(dialect_limit, int) and not isinstance(dialect_limit, bool) and dialect_limit > 0:
            return dialect_limit
        return DEFAULT_INSERTMANYVALUES_MAX_PARAMETERS

    def _get_upsert_chunk_size(self, column_count: int, chunk_size: Optional[int]) -> int:
        """Calculate native-upsert rows per chunk using dialect parameter and page limits."""
        parameter_limited_rows = max(1, self._get_insertmanyvalues_max_parameters(chunk_size) // max(1, column_count))
        dialect_page_size = getattr(self._dialect, "insertmanyvalues_page_size", None)
        if isinstance(dialect_page_size, int) and not isinstance(dialect_page_size, bool) and dialect_page_size > 0:
            return min(parameter_limited_rows, dialect_page_size)
        return parameter_limited_rows

    def _build_upsert_match_filter(
        self, row_chunk: Sequence[dict[str, Any]], match_fields: Sequence[str]
    ) -> ColumnElement[bool]:
        """Build the smallest exact-key predicate supported by the dialect."""
        match_columns = [get_instrumented_attr(self.model_type, field_name) for field_name in match_fields]
        if len(match_columns) == 1:
            match_values = [row[match_fields[0]] for row in row_chunk]
            use_in = not self._prefer_any or self._type_must_use_in_instead_of_any(match_values, match_columns[0].type)
            return match_columns[0].in_(match_values) if use_in else any_(match_values) == match_columns[0]  # type: ignore[arg-type]
        if self._dialect.name != "mssql":
            match_values = [tuple(row[field_name] for field_name in match_fields) for row in row_chunk]
            return tuple_(*match_columns).in_(match_values)
        return or_(
            *[
                and_(*[column == row[field_name] for column, field_name in zip(match_columns, match_fields)])
                for row in row_chunk
            ]
        )

    @staticmethod
    def _has_duplicate_match_keys(data: Sequence[ModelT], match_fields: Sequence[str]) -> bool:
        """Detect duplicate source keys, which dialects treat differently.

        A single native statement containing two rows with the same conflict key
        raises on some backends (postgresql: "cannot affect row a second time")
        and silently last-writer-wins on others. The ORM fallback merges such
        rows deterministically, so duplicated keys route the batch there.
        """
        hashable_match_keys: set[tuple[Any, ...]] = set()
        unhashable_match_keys: list[tuple[Any, ...]] = []
        for datum in data:
            match_key = tuple(getattr(datum, field_name, MISSING) for field_name in match_fields)
            if any(value is MISSING or value is None for value in match_key):
                continue
            try:
                is_duplicate = match_key in hashable_match_keys
            except TypeError:
                is_duplicate = any(
                    len(existing_key) == len(match_key)
                    and all(
                        compare_values(existing_value, key_value)
                        for existing_value, key_value in zip(existing_key, match_key)
                    )
                    for existing_key in unhashable_match_keys
                )
                if not is_duplicate:
                    unhashable_match_keys.append(match_key)
            else:
                if not is_duplicate:
                    hashable_match_keys.add(match_key)
            if is_duplicate:
                return True
        return False

    def _requires_orm_upsert(self, data: Sequence[ModelT]) -> bool:
        """Detect batches whose semantics depend on the ORM unit of work.

        Native Core DML never runs mapper-level events, relationship
        save-update cascades, or the FileObject flush listeners. Models and
        instances relying on any of those take the ORM fallback so their
        behavior matches ``add_many`` and ``update_many``.
        """
        from advanced_alchemy.types.file_object import StoredObject

        mapper = self.model_type.__mapper__
        if len(mapper.tables) > 1:
            return True
        if any(
            ancestor.dispatch.before_insert
            or ancestor.dispatch.after_insert
            or ancestor.dispatch.before_update
            or ancestor.dispatch.after_update
            for ancestor in mapper.iterate_to_root()
        ):
            return True
        if any(isinstance(column.type, StoredObject) for column in mapper.columns):
            return True
        relationship_keys = [relationship.key for relationship in mapper.relationships]
        if not relationship_keys:
            return False
        return any(datum.__dict__.get(key) for datum in data for key in relationship_keys)

    def _resolve_upsert_update_columns(
        self,
        data: Sequence[ModelT],
        strategy: UpsertStrategy,
    ) -> Optional[list[str]]:
        """Resolve columns that have uniform update intent across the batch.

        Native DML bypasses ORM default/onupdate handling. Only explicitly set
        attributes and Python ``onupdate`` columns should be copied into an
        existing row; insert-only defaults such as ``created_at`` must not be
        overwritten. Rows with different update shapes use the ORM fallback so
        an omitted value in one row cannot be replaced by another row's default.
        """
        if not data:
            return []
        table = cast("Table", self.model_type.__table__)
        if any(
            col.onupdate is not None and hasattr(getattr(col.onupdate, "arg", None), "_compiler_dispatch")
            for col in table.columns
        ):
            return None
        protected_columns = set(strategy.conflict_columns)
        protected_columns.update(column.key for column in table.primary_key.columns)
        update_column_sets: list[set[str]] = []
        for datum in data:
            instance_state = inspect(datum)
            update_column_sets.append(
                {
                    column.key
                    for column in table.columns
                    if column.key not in protected_columns
                    and (has_upsert_update_intent(datum, instance_state, column.key) or column.onupdate is not None)
                }
            )
        first_update_column_set = update_column_sets[0]
        if any(update_column_set != first_update_column_set for update_column_set in update_column_sets[1:]):
            return None
        return [column.key for column in table.columns if column.key in first_update_column_set]

    def _rows_require_fallback_upsert(
        self,
        input_rows: Sequence[dict[str, Any]],
        strategy: UpsertStrategy,
        match_fields: Sequence[str],
    ) -> bool:
        """Detect row shapes whose portable semantics require the ORM fallback.

        ``MERGE`` (oracle/mssql) and ``INSERT OR UPDATE`` (spanner) do not
        transparently invoke server-side ``Sequence`` / ``Identity`` defaults
        the way ``INSERT ... ON CONFLICT`` does on postgresql: a hand-built
        statement that omits an autoincrement PK column will produce a NULL
        violation. When the resolved strategy is one of those kinds and any
        row is missing a PK column, fall back to the ORM-managed
        SELECT+partition path so the sequence/identity machinery runs
        normally.
        """
        if not input_rows:
            return False
        first_row_columns = set(input_rows[0])
        if any(set(row) != first_row_columns for row in input_rows[1:]):
            return True
        if any(field not in row or row[field] is None for row in input_rows for field in match_fields):
            return True
        if strategy.kind not in {"merge", "insert_or_update"}:
            return False
        table = cast("Table", self.model_type.__table__)
        primary_key_columns = {column.key for column in table.primary_key.columns}
        if any(not primary_key_columns.issubset(row.keys()) for row in input_rows):
            return True
        sql_default_columns = {
            column.key
            for column in table.columns
            if column.default is not None and hasattr(getattr(column.default, "arg", None), "_compiler_dispatch")
        }
        return any(not sql_default_columns.issubset(row.keys()) for row in input_rows)

    def _extract_upsert_row(self, instance: ModelT) -> dict[str, Any]:
        """Convert a model instance to a row dict suitable for native upsert execution.

        Invokes Python-side callable defaults for columns missing from the
        instance (UUID factories on PK columns, ``default=datetime.utcnow``
        audit timestamps, etc.) because the native dispatch path bypasses
        SQLAlchemy's ORM flush where these defaults normally fire.

        Columns whose default is server-managed (``Sequence``, ``Identity``,
        ``server_default``) are omitted from the row when their value is
        ``None`` so the database supplies them.
        """
        model_values = model_to_dict(instance)
        table = cast("Table", self.model_type.__table__)
        prepared_row = dict(model_values)
        instance_state = inspect(instance)
        for column in table.columns:
            has_update_intent = has_upsert_update_intent(instance, instance_state, column.key)
            if column.onupdate is not None and not has_update_intent:
                onupdate_value = getattr(column.onupdate, "arg", None)
                if callable(onupdate_value):
                    prepared_row[column.key] = resolve_column_default(onupdate_value)
                    continue
                if onupdate_value is not None:
                    prepared_row[column.key] = onupdate_value
                    continue
            if has_update_intent:
                prepared_row[column.key] = getattr(instance, column.key)
                continue
            if prepared_row.get(column.key) is not None:
                continue
            value_default = column.onupdate if column.onupdate is not None else column.default
            default_value = getattr(value_default, "arg", None) if value_default is not None else None
            if hasattr(default_value, "_compiler_dispatch"):
                prepared_row.pop(column.key, None)
                continue
            if callable(default_value):
                prepared_row[column.key] = resolve_column_default(default_value)
                continue
            if value_default is not None and default_value is not None:
                prepared_row[column.key] = default_value
                continue
            if column.primary_key or value_default is not None or column.server_default is not None:
                prepared_row.pop(column.key, None)
        return prepared_row

    @staticmethod
    def _normalize_match_value(value: Any) -> Any:
        """Fold the common collation-insensitive comparisons databases apply to text keys."""
        if isinstance(value, str):
            return value.casefold().rstrip()
        return value

    @classmethod
    def _order_upsert_results(
        cls,
        instances: Sequence[ModelT],
        input_rows: Sequence[dict[str, Any]],
        match_fields: Sequence[str],
    ) -> list[ModelT]:
        """Restore input ordering because RETURNING/OUTPUT order is undefined.

        Pairs by exact match-key equality first. Rows the database matched
        under a collation-insensitive comparison (``'foo'`` upserted onto a
        stored ``'FOO'``) get a second, normalized pass; a pairing that is
        still ambiguous raises instead of returning a misaligned list.
        """
        instances_by_match_key: dict[tuple[Any, ...], ModelT] = {}
        unhashable_instances: list[tuple[tuple[Any, ...], ModelT]] = []
        for instance in instances:
            match_key = tuple(getattr(instance, field_name) for field_name in match_fields)
            try:
                instances_by_match_key[match_key] = instance
            except TypeError:
                unhashable_instances.append((match_key, instance))

        ordered_instances: list[Optional[ModelT]] = []
        matched_instance_ids: set[int] = set()
        for row in input_rows:
            match_key = tuple(row[field_name] for field_name in match_fields)
            try:
                matched_instance: Optional[ModelT] = instances_by_match_key.get(match_key)
            except TypeError:
                matched_instance = next(
                    (
                        candidate_instance
                        for candidate_key, candidate_instance in unhashable_instances
                        if len(candidate_key) == len(match_key)
                        and all(
                            compare_values(candidate_value, key_value)
                            for candidate_value, key_value in zip(candidate_key, match_key)
                        )
                    ),
                    None,
                )
            if matched_instance is not None:
                matched_instance_ids.add(id(matched_instance))
            ordered_instances.append(matched_instance)

        unmatched_positions = [position for position, instance in enumerate(ordered_instances) if instance is None]
        leftover_instances = [instance for instance in instances if id(instance) not in matched_instance_ids]
        if not unmatched_positions and not leftover_instances:
            return cast("list[ModelT]", ordered_instances)
        ambiguity_msg = (
            "upsert_many could not unambiguously pair hydrated rows with input rows; "
            "verify that the batch keys are unique under the database's comparison rules"
        )
        if len(unmatched_positions) != len(leftover_instances):
            raise RepositoryError(ambiguity_msg)
        leftovers_by_normalized_key: dict[tuple[Any, ...], list[ModelT]] = {}
        for instance in leftover_instances:
            normalized_key = tuple(
                cls._normalize_match_value(getattr(instance, field_name)) for field_name in match_fields
            )
            with contextlib.suppress(TypeError):
                leftovers_by_normalized_key.setdefault(normalized_key, []).append(instance)
        for position in unmatched_positions:
            row = input_rows[position]
            normalized_key = tuple(cls._normalize_match_value(row[field_name]) for field_name in match_fields)
            try:
                candidates = leftovers_by_normalized_key.get(normalized_key, [])
            except TypeError:
                candidates = []
            if len(candidates) != 1:
                raise RepositoryError(ambiguity_msg)
            ordered_instances[position] = candidates.pop()
        return cast("list[ModelT]", ordered_instances)


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
    # Label objects (from column_property) don't have default/onupdate attributes
    # Return False for these as they represent computed values, not defaulted columns
    if isinstance(column, Label):
        return False
    # Use defensive attribute checking for safety with other column-like objects
    return (
        getattr(column, "default", None) is not None
        or getattr(column, "server_default", None) is not None
        or getattr(column, "onupdate", None) is not None
        or getattr(column, "server_onupdate", None) is not None
    )


def was_attribute_set(instance: Any, mapper: Any, attr_name: str) -> bool:
    """Check if an attribute was explicitly set on a model instance.

    This function distinguishes between attributes that were explicitly set
    (even to None) versus attributes that are simply uninitialized and defaulting
    to None. This is crucial for partial updates where only modified fields
    should be copied.

    Args:
        instance: The model instance to check.
        mapper: The SQLAlchemy mapper/inspector for the instance.
        attr_name: The name of the attribute to check.

    Returns:
        bool: True if the attribute was explicitly set, False if uninitialized.
    """
    try:
        # Get the attribute state
        attr_state = mapper.attrs.get(attr_name)
        if attr_state is None:
            return False

        # Check if the attribute has history (was modified)
        # For a new transient instance, modified attributes will have history
        history = attr_state.history
        if history.has_changes():
            return True

        # For attributes with no history, check if they're in the instance dict
        # This handles the case where an attribute was set during __init__
        return hasattr(instance, "__dict__") and attr_name in instance.__dict__
    except (AttributeError, KeyError):  # pragma: no cover
        # If we can't determine, assume it was set to be safe
        return True


def has_upsert_update_intent(instance: Any, instance_state: Any, attribute_name: str) -> bool:
    """Check whether an attribute on an instance should be included in an upsert update.

    Distinguishes constructor input on transient instances from unmodified
    attributes on persistent instances.

    Args:
        instance: The model instance to inspect.
        instance_state: The SQLAlchemy inspection state for the instance.
        attribute_name: The attribute name to check.

    Returns:
        bool: True if the attribute has update intent, False otherwise.
    """
    if instance_state.transient:
        return was_attribute_set(instance, instance_state, attribute_name)
    attribute_state = instance_state.attrs.get(attribute_name)
    return bool(attribute_state is not None and attribute_state.history.has_changes())


def compare_values(existing_value: Any, new_value: Any) -> bool:
    """Safely compare two values, handling numpy arrays and other special types.

    This function handles the comparison of values that may include numpy arrays
    (such as pgvector's Vector type) which cannot be directly compared using
    standard equality operators due to their element-wise comparison behavior.

    Args:
        existing_value: The current value to compare.
        new_value: The new value to compare against.

    Returns:
        bool: True if values are equal, False otherwise.
    """
    # Handle None comparisons
    if existing_value is None and new_value is None:
        return True
    if existing_value is None or new_value is None:
        return False

    # Handle numpy arrays or array-like objects
    if is_numpy_array(existing_value) or is_numpy_array(new_value):
        # Both values must be arrays for them to be considered equal
        if not (is_numpy_array(existing_value) and is_numpy_array(new_value)):
            return False
        return arrays_equal(existing_value, new_value)

    # Standard equality comparison for all other types
    try:
        return bool(existing_value == new_value)
    except (ValueError, TypeError):
        # If comparison fails for any reason, consider them different
        # This is a safe fallback that will trigger updates when unsure
        return False
