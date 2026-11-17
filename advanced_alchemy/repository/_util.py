# ruff: noqa: PLR0911
import dataclasses
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
    Mapper,
    MapperProperty,
    RelationshipProperty,
    class_mapper,
    joinedload,
    lazyload,
    object_session,
    selectinload,
)
from sqlalchemy.orm.decl_base import _declarative_constructor  # pyright: ignore[reportPrivateUsage]
from sqlalchemy.orm.interfaces import LoaderOption
from sqlalchemy.sql import ColumnElement, ColumnExpressionArgument
from sqlalchemy.sql.base import ExecutableOption
from sqlalchemy.sql.dml import ReturningDelete, ReturningUpdate
from sqlalchemy.sql.elements import Label
from typing_extensions import TypeAlias

from advanced_alchemy.base import ModelProtocol
from advanced_alchemy.exceptions import ErrorMessages, ImproperConfigurationError, NotFoundError
from advanced_alchemy.exceptions import wrap_sqlalchemy_exception as _wrap_sqlalchemy_exception
from advanced_alchemy.filters import (
    CursorFilter,
    InAnyFilter,
    LimitOffsetFilter,
    OrderByFilter,
    PaginationFilter,
    StatementFilter,
    StatementTypeT,
)
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
    "allows_explicit_none_update",
    "column_has_defaults",
    "compare_values",
    "get_abstract_loader_options",
    "get_instrumented_attr",
    "get_primary_key_info",
    "has_upsert_update_intent",
    "is_mapped_model_class",
    "mark_explicit_none_update",
    "model_from_dict",
    "partial_model_from_dict",
    "resolve_generic_type_args",
    "snapshot_and_detach_relationships",
    "supports_partial_hydration",
    "was_attribute_set",
)

_EXPLICIT_NONE_UPDATE_KEY = "_aa_explicit_none_update"

WhereClauseT = ColumnExpressionArgument[bool]
SingleLoad: TypeAlias = Union[
    LoaderOption,
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
    """
    try:
        mapper: Optional[Mapper[Any]] = inspect(model)
    except NoInspectionAvailable:
        return (), ()
    else:
        if mapper is None:
            return (), ()
        pk_columns: tuple[Column[Any], ...] = cast("tuple[Column[Any], ...]", mapper.primary_key)
        pk_attr_names: tuple[str, ...] = tuple(mapper.get_property_by_column(col).key for col in pk_columns)
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
        result_values: list[Any] = []
        for attr_name in pk_attr_names:
            val = pk_dict[attr_name]
            if val is None:
                msg = f"Primary key value for '{attr_name}' cannot be None in composite key for {model_name}"
                raise ValueError(msg)
            result_values.append(val)
        return tuple(result_values)

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
    """
    if len(pk_attr_names) == 1:
        return (pk_value,)

    if isinstance(pk_value, tuple):
        return cast("tuple[Any, ...]", pk_value)  # type: ignore[redundant-cast]
    if isinstance(pk_value, dict):
        pk_dict = cast("dict[str, Any]", pk_value)
        return tuple(pk_dict[attr_name] for attr_name in pk_attr_names)

    pk_type_name = type(pk_value).__name__
    msg = f"Composite primary key for {model_name} requires tuple or dict, got {pk_type_name}: {pk_value!r}"
    raise ValueError(msg)


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
    """
    return _hydrate_model_dict(model, kwargs, partial=False)


def partial_model_from_dict(model: type[ModelT], /, **kwargs: Any) -> ModelT:
    """Create a partial ORM model instance without invoking ``model.__init__``.

    Used for partial updates so omitted attributes remain uninitialized across
    standard declarative models, ``MappedAsDataclass`` models (including models
    with required non-default fields), and ``SQLModel`` table models.

    Args:
        model: The SQLAlchemy model class to instantiate.
        **kwargs: Keyword arguments containing only the attributes to update.

    Returns:
        ModelT: A transient model instance with only ``kwargs`` populated.
    """
    return _hydrate_model_dict(model, kwargs, partial=True)


def supports_partial_hydration(model: type[Any]) -> bool:
    """Return whether ``model`` can be hydrated for partial updates without calling ``__init__``.

    Models using the default declarative constructor produce identical results either way, and
    ``MappedAsDataclass`` and ``SQLModel`` table models require partial hydration so omitted fields
    are not filled with constructor defaults. Models that define their own ``__init__`` keep calling
    it so derived attributes computed in the constructor are still applied on update.

    Args:
        model: The SQLAlchemy model class to inspect.

    Returns:
        bool: True if partial hydration preserves the model's constructor behavior.
    """
    original_init = class_mapper(model).class_manager.original_init
    if original_init is _declarative_constructor:
        return True
    if getattr(original_init, "__module__", "").startswith("sqlmodel"):
        return True
    init_code = getattr(original_init, "__code__", None)
    return dataclasses.is_dataclass(model) and getattr(init_code, "co_filename", None) == "<string>"


def get_abstract_loader_options(
    loader_options: Union[LoadSpec, None],
    default_loader_options: Union[Sequence[ExecutableOption], None] = None,
    default_options_have_wildcards: bool = False,
    merge_with_default: bool = True,
    inherit_lazy_relationships: bool = True,
    cycle_count: int = 0,
) -> tuple[list[ExecutableOption], bool]:
    """Generate SQLAlchemy statement options for eager loading relationships and loader criteria.

    Args:
        loader_options: Specification for how to load relationships. Can be:
            - None: Use defaults
            - :class:`sqlalchemy.sql.base.ExecutableOption`: Direct SQLAlchemy loader or criteria option
            - :class:`sqlalchemy.orm.InstrumentedAttribute`: Model relationship attribute
            - :class:`sqlalchemy.orm.RelationshipProperty`: SQLAlchemy relationship
            - str: "*" for wildcard loading
            - :class:`typing.Sequence` of the above
        default_loader_options: Sequence of :class:`sqlalchemy.sql.base.ExecutableOption` options to start with.
        default_options_have_wildcards: Whether the default options require ``Result.unique()``.
        merge_with_default: Whether to merge the default options with ``loader_options``.
        inherit_lazy_relationships: Whether to inherit the ``lazy`` configuration from the model's relationships.
        cycle_count: Number of times this function has been called recursively.

    Returns:
        tuple[list[:class:`sqlalchemy.sql.base.ExecutableOption`], bool]: A tuple containing:
            - :class:`list` of :class:`sqlalchemy.sql.base.ExecutableOption` statement options
            - Boolean indicating whether ``Result.unique()`` is required for joined collection loads
    """
    loads: list[ExecutableOption] = []
    if cycle_count == 0 and not inherit_lazy_relationships:
        loads.append(lazyload("*"))
    if cycle_count == 0 and merge_with_default and default_loader_options is not None:
        loads.extend(default_loader_options)
    requires_unique = default_options_have_wildcards
    if loader_options is None:
        return (loads, requires_unique)
    if isinstance(loader_options, ExecutableOption):
        loads.append(loader_options)
        return (loads, requires_unique or _joins_collection(loader_options, fallback=requires_unique))
    if isinstance(loader_options, InstrumentedAttribute):
        loader_options = loader_options.property
    if isinstance(loader_options, RelationshipProperty):
        class_ = loader_options.class_attribute
        loads.append(
            selectinload(class_) if loader_options.uselist else joinedload(class_, innerjoin=loader_options.innerjoin)
        )
        return (loads, requires_unique)
    if isinstance(loader_options, str) and loader_options == "*":
        loads.append(joinedload("*"))
        return (loads, True)
    if isinstance(loader_options, (list, tuple)):
        for attribute in loader_options:  # pyright: ignore[reportUnknownVariableType]
            if isinstance(attribute, (list, tuple)):
                load_chain, requires_unique = get_abstract_loader_options(
                    loader_options=attribute,  # pyright: ignore[reportUnknownArgumentType]
                    default_options_have_wildcards=requires_unique,
                    inherit_lazy_relationships=inherit_lazy_relationships,
                    merge_with_default=merge_with_default,
                    cycle_count=cycle_count + 1,
                )
                if not load_chain:
                    continue
                loader = load_chain[-1]
                for sub_load in load_chain[-2::-1]:
                    loader = cast("Any", sub_load).options(loader)
                loads.append(loader)
            else:
                load_chain, requires_unique = get_abstract_loader_options(
                    loader_options=attribute,  # pyright: ignore[reportUnknownArgumentType]
                    default_options_have_wildcards=requires_unique,
                    inherit_lazy_relationships=inherit_lazy_relationships,
                    merge_with_default=merge_with_default,
                    cycle_count=cycle_count + 1,
                )
                loads.extend(load_chain)
    return (loads, requires_unique)


def is_mapped_model_class(candidate: Any) -> bool:
    """Return whether ``candidate`` is a mapped SQLAlchemy model class."""
    if candidate is Any or not isinstance(candidate, type):
        return False
    try:
        return inspect(candidate, raiseerr=False) is not None
    except (NoInspectionAvailable, TypeError, ValueError):
        return False


def resolve_generic_type_args(
    cls: type[Any],
    target_origin: type[Any],
    *,
    own_bases_only: bool = False,
) -> tuple[Any, ...]:
    """Extract concrete generic type arguments for ``target_origin`` from ``cls``.

    Propagates ``TypeVar`` substitutions across intermediate user generic base classes
    even when type parameter positions are reordered.

    Args:
        cls: The subclass being inspected.
        target_origin: The generic base class or protocol to match.
        own_bases_only: When ``True``, inspect only ``cls.__orig_bases__`` instead of walking ``__mro__``.

    Returns:
        Tuple of type arguments bound to ``target_origin``.
    """

    def substitute(args: tuple[Any, ...], mapping: Mapping[Any, Any]) -> tuple[Any, ...]:
        resolved_items: list[Any] = []
        for arg in args:
            if arg in mapping:
                resolved_items.append(mapping[arg])
            else:
                origin = get_origin(arg)
                sub_args = get_args(arg)
                if origin is not None and sub_args:
                    new_sub = substitute(sub_args, mapping)
                    copy_with = getattr(arg, "copy_with", None)
                    resolved_items.append(copy_with(new_sub) if callable(copy_with) else arg)
                else:
                    resolved_items.append(arg)
        return tuple(resolved_items)

    def has_concrete(args: tuple[Any, ...]) -> bool:
        return bool(
            args
            and any(arg is not Any and (isinstance(arg, type) or isinstance(get_origin(arg), type)) for arg in args)
        )

    def resolve_bases(bases: Iterable[Any], mapping: Mapping[Any, Any]) -> tuple[Any, ...]:
        for base in bases:
            origin = get_origin(base)
            if origin is None or not isinstance(origin, type) or not issubclass(origin, target_origin):
                continue
            raw_args = substitute(get_args(base), mapping)
            if origin is target_origin and has_concrete(raw_args):
                return raw_args
            params = getattr(origin, "__parameters__", ())
            next_mapping = {**mapping, **dict(zip(params, raw_args))}
            nested = resolve_bases(origin.__dict__.get("__orig_bases__", ()), next_mapping)
            if nested:
                return nested
            if has_concrete(raw_args):
                return raw_args
        return ()

    classes: Iterable[type[Any]] = (cls,) if own_bases_only else cls.__mro__
    for current_cls in classes:
        resolved = resolve_bases(current_cls.__dict__.get("__orig_bases__", ()), {})
        if resolved:
            return resolved
    return ()


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


def mark_explicit_none_update(instance: Any) -> None:
    """Mark a transient update model so explicit ``None`` values write to columns with defaults."""
    try:
        state = inspect(instance, raiseerr=False)
    except (NoInspectionAvailable, TypeError, ValueError):
        return
    if state is not None and hasattr(state, "info"):
        state.info[_EXPLICIT_NONE_UPDATE_KEY] = True


def allows_explicit_none_update(state: Any) -> bool:
    """Return whether ``state`` was marked by ``Service.update(..., item_id=...)`` to write explicit ``None``."""
    info: Any = getattr(state, "info", None)
    if not isinstance(info, Mapping):
        return False
    return bool(cast("Mapping[str, Any]", info).get(_EXPLICIT_NONE_UPDATE_KEY))


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
        snapshotted, related_items = _snapshot_relationship_items(raw_value)
        values[relationship.key] = snapshotted

        back_attr = relationship.back_populates
        if is_transient and back_attr and raw_value is not None:
            _detach_transient_backrefs(instance, related_items, back_attr)
    return values


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
    _pk_columns: tuple[Column[Any], ...] = ()
    _pk_attr_names: tuple[str, ...] = ()

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if "model_type" in cls.__dict__:
            return
        args = resolve_generic_type_args(
            cls,
            ModelRepositoryMixin,
            own_bases_only=getattr(cls, "model_type", None) is not None,
        )
        if args and is_mapped_model_class(args[0]):
            cls.model_type = cast("type[ModelT]", args[0])

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
        statement: Select[Any],
    ) -> Select[Any]: ...

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
        from advanced_alchemy.filters import FilterSet

        filtersets: list[FilterSet[Any]] = [
            cast("Any", filter_) for filter_ in filters if isinstance(filter_, FilterSet)
        ]
        if any(filterset.model_type is not self.model_type for filterset in filtersets):
            msg = "FilterSet model does not match the repository model"
            raise ValueError(msg)
        expanded = order_cursor_filter_last(_expand_filtersets(filters))
        for filter_ in expanded:
            if isinstance(filter_, (PaginationFilter,)):
                if apply_pagination:
                    statement = filter_.append_to_statement(statement, self.model_type)
            elif isinstance(filter_, (InAnyFilter,)):
                statement = filter_.append_to_statement(statement, self.model_type, prefer_any=self._prefer_any)
            elif isinstance(filter_, ColumnElement):
                statement = cast("StatementTypeT", statement.where(filter_))
            else:
                statement = filter_.append_to_statement(statement, self.model_type)
        if isinstance(statement, Select) and filtersets:
            statement = cast(
                "StatementTypeT",
                _filterset_loader_options(
                    statement,
                    filtersets,
                    self._dialect,
                    paginated=any(isinstance(f, PaginationFilter) for f in expanded)
                    or getattr(statement, "_limit_clause", None) is not None
                    or getattr(statement, "_offset_clause", None) is not None,
                ),
            )
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


def has_cursor_filter(filters: Sequence[Union[StatementFilter, ColumnElement[bool]]]) -> bool:
    """Return whether ``filters``, including FilterSet contents, contain a :class:`CursorFilter`."""
    return any(isinstance(filter_, CursorFilter) for filter_ in _expand_filtersets(filters))


def order_cursor_filter_last(
    filters: Sequence[Union[StatementFilter, ColumnElement[bool]]],
) -> list[Union[StatementFilter, ColumnElement[bool]]]:
    """Validate cursor pagination and move the :class:`CursorFilter` after every other filter.

    The cursor filter owns ordering and limits, so it cannot be combined with
    :class:`OrderByFilter`, :class:`LimitOffsetFilter`, or another cursor filter.

    Args:
        filters: Expanded filters.

    Returns:
        The filters with any cursor filter last.

    Raises:
        ImproperConfigurationError: Pagination filters conflict.
    """
    cursors = [filter_ for filter_ in filters if isinstance(filter_, CursorFilter)]
    if not cursors:
        return list(filters)
    if len(cursors) > 1:
        msg = "Only one CursorFilter can be applied to a query"
        raise ImproperConfigurationError(msg)
    if any(isinstance(filter_, (OrderByFilter, LimitOffsetFilter)) for filter_ in filters):
        msg = "CursorFilter owns ordering and limits; remove OrderByFilter and LimitOffsetFilter from the query"
        raise ImproperConfigurationError(msg)
    return [*(filter_ for filter_ in filters if not isinstance(filter_, CursorFilter)), cursors[0]]


def _hydrate_model_dict(model: type[ModelT], kwargs: Mapping[str, Any], *, partial: bool = False) -> ModelT:
    mapper = class_mapper(model)
    mapper_attrs = mapper.attrs
    converted_data: dict[str, Any] = {}

    for key, value in kwargs.items():
        if key not in mapper_attrs:
            continue

        attr = mapper_attrs[key]
        if isinstance(attr, RelationshipProperty):
            related_model: type[ModelT] = attr.mapper.class_
            converted_data[key] = _convert_relationship_value(
                value=value,
                related_model=related_model,
                is_collection=attr.uselist or False,
            )
        else:
            converted_data[key] = value

    if partial:
        instance: ModelT = mapper.class_manager.new_instance()
        for key, value in converted_data.items():
            setattr(instance, key, value)
        return instance

    return model(**converted_data)


def _snapshot_relationship_items(raw_value: Any) -> tuple[Any, list[Any]]:
    if isinstance(raw_value, Mapping):
        mapping = cast("dict[Any, Any]", raw_value)
        return dict(mapping), list(mapping.values())
    if isinstance(raw_value, (list, set)):
        items = cast("Iterable[Any]", raw_value)
        return (set(items) if isinstance(raw_value, set) else list(items)), list(items)
    return raw_value, [raw_value]


def _detach_transient_backrefs(instance: Any, related_items: Sequence[Any], back_attr: str) -> None:
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
        if not isinstance(value, (list, tuple)):
            value = [value]
        return [
            model_from_dict(related_model, **item) if isinstance(item, dict) else item
            for item in value  # pyright: ignore[reportUnknownVariableType]
        ]
    if isinstance(value, dict):
        return model_from_dict(related_model, **value)
    return value


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


def _contains_column_element(value: Any) -> bool:
    """Return True if a filter or nested container embeds a raw SQLAlchemy expression."""
    if isinstance(value, ColumnElement):
        return True
    if dataclasses.is_dataclass(value) and not isinstance(value, type):  # pyright: ignore[reportUnknownArgumentType]
        return any(_contains_column_element(getattr(value, field.name)) for field in dataclasses.fields(value))
    if isinstance(value, (list, tuple, set, frozenset)):
        return any(_contains_column_element(item) for item in cast("Iterable[Any]", value))
    if isinstance(value, dict):
        value_map = cast("dict[object, object]", value)
        return any(_contains_column_element(item) for item in value_map.values())
    return False


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


def _expand_filtersets(
    filters: Sequence[Union[StatementFilter, ColumnElement[bool]]],
) -> list[Union[StatementFilter, ColumnElement[bool]]]:
    from advanced_alchemy.filters import FilterSet

    expanded: list[Union[StatementFilter, ColumnElement[bool]]] = []
    for filter_ in filters:
        if isinstance(filter_, FilterSet):
            expanded.extend(filter_.to_statement_filters())
        else:
            expanded.append(filter_)
    return expanded


def _loader_path(option: Any) -> tuple[Any, ...]:
    path = getattr(getattr(option, "path", None), "path", ())
    return tuple(cast("Any", part) for part in path if isinstance(part, RelationshipProperty))


def _filterset_loader_options(
    statement: Select[Any], filtersets: Sequence[Any], dialect: Any, *, paginated: bool
) -> Select[Any]:
    """Merge inferred loaders without replacing caller strategies or criteria.

    SQLAlchemy stores chained strategies in Load.context. Clone inferred options and
    retain only unclaimed strategy paths, so explicit parents can keep their strategy
    while inferred descendants are still eagerly loaded.
    """
    entity_result = False
    for description in statement.column_descriptions:
        entity = inspect(description.get("expr"), raiseerr=False)
        if entity is not None and hasattr(entity, "mapper"):
            entity_result = True
            break
    if not entity_result:
        return statement
    explicit_paths: set[tuple[Any, ...]] = set()
    wildcard_paths: set[tuple[Any, ...]] = set()
    for option in getattr(statement, "_with_options", ()):
        for entry in getattr(option, "context", (option,)):
            if getattr(entry, "strategy", None):
                path = _loader_path(entry)
                raw_path = getattr(getattr(entry, "path", None), "path", getattr(entry, "path", ()))
                if any("relationship:" in str(part) for part in raw_path):
                    wildcard_paths.add(path)
                elif path:
                    explicit_paths.add(path)
    options: list[ExecutableOption] = []
    claimed: set[tuple[Any, ...]] = set()
    subquery_loading = False
    for filterset in filtersets:
        for option in filterset.inferred_load(dialect):
            # Retain inferred descendants under explicit parent loading strategies.
            contexts: list[Any] = []
            for entry in getattr(option, "context", ()):
                path = _loader_path(entry)
                blocked = any(len(path) > len(prefix) and path[: len(prefix)] == prefix for prefix in wildcard_paths)
                if not blocked and path not in explicit_paths and path not in claimed:
                    contexts.append(entry)
                    claimed.add(path)
                    subquery_loading |= ("lazy", "subquery") in (getattr(entry, "strategy", ()) or ())
            if contexts:
                clone = option._generate()  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
                clone.context = tuple(contexts)
                options.append(clone)
    missing_mssql_order = getattr(dialect, "name", dialect) == "mssql" and not getattr(
        statement, "_order_by_clauses", ()
    )
    if paginated and (subquery_loading or missing_mssql_order):
        statement = statement.order_by(*inspect(filtersets[0].model_type).primary_key)
    return statement.options(*options)


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
) -> Optional[str]:
    """Build a stable cache key for list/list_and_count operations.

    Returns None if the query specification includes non-cacheable filter
    expressions (e.g., raw SQLAlchemy boolean expressions).
    """
    from advanced_alchemy.filters import FilterSet

    if any(isinstance(filter_, FilterSet) and filter_.load for filter_ in filters):
        return None
    normalized_filters: list[dict[str, Any]] = []
    for filter_ in _expand_filtersets(filters):
        if _contains_column_element(filter_):
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
    if bind_group is not None:
        payload["bind_group"] = bind_group

    try:
        encoded = encode_json(_canonicalize_cache_key_value(payload)).encode("utf-8")
    except TypeError:  # pragma: no cover
        return None

    digest = hashlib.sha256(encoded).hexdigest()
    return f"{model_name}:{method}:{digest}"


def _strategy_is_joined(strategy: Any) -> bool:
    if not isinstance(strategy, Iterable):
        return False
    return ("lazy", "joined") in strategy  # pyright: ignore[reportUnknownArgumentType]


def _joins_collection(option: ExecutableOption, *, fallback: bool = False) -> bool:
    if not isinstance(option, LoaderOption):
        return False
    has_strategy = hasattr(option, "strategy")
    has_context = hasattr(option, "context")
    if not has_strategy and not has_context:
        return fallback
    strategy: Any = getattr(option, "strategy", None)
    path: Any = getattr(option, "path", None)
    if _strategy_is_joined(strategy) and path == ("relationship:_sa_default",):
        return True
    context: Any = getattr(option, "context", ())
    if isinstance(context, Iterable):
        for entry in context:  # pyright: ignore[reportUnknownVariableType]
            if not _strategy_is_joined(getattr(entry, "strategy", None)):  # pyright: ignore[reportUnknownArgumentType]
                continue
            entry_path: Any = getattr(entry, "path", None)  # pyright: ignore[reportUnknownArgumentType]
            path_tuple: Any = getattr(entry_path, "path", entry_path)  # pyright: ignore[reportUnknownArgumentType]
            if isinstance(path_tuple, Sequence) and len(path_tuple) >= 2:  # noqa: PLR2004  # pyright: ignore[reportUnknownArgumentType]
                prop: Any = path_tuple[-2]  # pyright: ignore[reportUnknownVariableType]
                if getattr(prop, "uselist", False):  # pyright: ignore[reportUnknownArgumentType]
                    return True
    return False
