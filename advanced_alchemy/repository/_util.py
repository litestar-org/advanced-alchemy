from collections.abc import Iterable, Sequence
from typing import Any, Literal, Optional, Protocol, Union, cast, overload

from sqlalchemy import (
    Column,
    Delete,
    Dialect,
    Select,
    UnaryExpression,
    Update,
    inspect,
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
    _AbstractLoad,  # pyright: ignore[reportPrivateUsage]  # pyright: ignore[reportPrivateUsage]
)
from sqlalchemy.sql import ColumnElement, ColumnExpressionArgument
from sqlalchemy.sql.base import ExecutableOption
from sqlalchemy.sql.dml import ReturningDelete, ReturningUpdate
from sqlalchemy.sql.elements import Label
from typing_extensions import TypeAlias

from advanced_alchemy.base import ModelProtocol
from advanced_alchemy.exceptions import ErrorMessages
from advanced_alchemy.exceptions import wrap_sqlalchemy_exception as _wrap_sqlalchemy_exception
from advanced_alchemy.filters import (
    InAnyFilter,
    PaginationFilter,
    StatementFilter,
    StatementTypeT,
)
from advanced_alchemy.repository._typing import arrays_equal, is_numpy_array
from advanced_alchemy.repository.typing import ModelT, OrderingPair, PrimaryKeyType

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


def model_from_dict(model: type[ModelT], **kwargs: Any) -> ModelT:
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
