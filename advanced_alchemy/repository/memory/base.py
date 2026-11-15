import builtins
import contextlib
import datetime
import re
from collections import defaultdict
from collections.abc import Callable, Collection, Mapping, Sequence
from inspect import isclass, signature
from typing import TYPE_CHECKING, Any, Generic, List, Literal, Optional, Union, cast, overload

from sqlalchemy import BooleanClauseList, ColumnElement, and_, inspect
from sqlalchemy.orm import InstrumentedAttribute, RelationshipProperty, Session, class_mapper, object_mapper
from sqlalchemy.orm.exc import UnmappedClassError
from sqlalchemy.sql import operators as sa_op
from sqlalchemy.sql.elements import BinaryExpression, BindParameter, False_, Null, True_, UnaryExpression
from typing_extensions import TypeVar

from advanced_alchemy.exceptions import AdvancedAlchemyError, RepositoryError
from advanced_alchemy.filters import (
    BeforeAfter,
    BooleanFilter,
    CollectionFilter,
    ComparisonFilter,
    FilterGroup,
    LimitOffset,
    MultiFilter,
    NotInCollectionFilter,
    NotInSearchFilter,
    NotNullFilter,
    NullFilter,
    OnBeforeAfter,
    OrderBy,
    RelationshipFilter,
    SearchFilter,
    StatementFilter,
)
from advanced_alchemy.operations import validate_identifier
from advanced_alchemy.repository.typing import _MISSING, MISSING, ModelT  # pyright: ignore[reportPrivateUsage]
from advanced_alchemy.utils.deprecation import warn_deprecation

if TYPE_CHECKING:
    from collections.abc import Iterable

    from sqlalchemy.orm import Mapper


CollectionT = TypeVar("CollectionT")
T = TypeVar("T")
AnyObject = TypeVar("AnyObject", bound="Any")


class _NotSet:
    pass


class InMemoryStore(Generic[T]):
    def __init__(self) -> None:
        self._store: dict[Any, T] = {}

    def _resolve_key(self, key: Any) -> Any:
        """Test different key representations

        Args:
            key: The key to test

        Raises:
            KeyError: Raised if key is not present

        Returns:
            The key representation that is present in the store
        """
        for key_ in (key, str(key)):
            if key_ in self._store:
                return key_
        raise KeyError

    def key(self, obj: T) -> Any:
        return hash(obj)

    def add(self, obj: T) -> T:
        if (key := self.key(obj)) not in self._store:
            self._store[key] = obj
            return obj
        raise KeyError

    def update(self, obj: T) -> T:
        key = self._resolve_key(self.key(obj))
        self._store[key] = obj
        return obj

    @overload
    def get(self, key: Any, default: type[_NotSet] = _NotSet) -> T: ...

    @overload
    def get(self, key: Any, default: AnyObject) -> "Union[T, AnyObject]": ...

    def get(
        self, key: Any, default: "Union[AnyObject, type[_NotSet]]" = _NotSet
    ) -> "Union[T, AnyObject]":  # pragma: no cover
        """Get the object identified by `key`, or return `default` if set or raise a `KeyError` otherwise

        Args:
            key: The key to test
            default: Value to return if key is not present. Defaults to _NotSet.

        Raises:
            KeyError: Raised if key is not present

        Returns:
            The object identified by key
        """
        try:
            key = self._resolve_key(key)
        except KeyError as error:
            if isclass(default) and not issubclass(default, _NotSet):  # pyright: ignore[reportUnnecessaryIsInstance]
                return cast("AnyObject", default)
            raise KeyError from error
        return self._store[key]

    def get_or_none(self, key: Any, default: Any = None) -> "Union[T, None]":
        with contextlib.suppress(KeyError):
            return self.get(key)
        return cast("Union[T, None]", default)

    def remove(self, key: Any) -> T:
        return self._store.pop(self._resolve_key(key))

    def get_all(self) -> List[T]:
        return list(self._store.values())

    def list(self) -> List[T]:
        """.. deprecated:: 1.10.0
        Use :meth:`get_all` instead.
        """
        warn_deprecation(
            version="1.10.0",
            deprecated_name="list",
            kind="method",
            removal_in="2.0.0",
            alternative="get_all",
        )
        return self.get_all()

    def remove_all(self) -> None:
        self._store = {}

    def __contains__(self, obj: T) -> bool:
        try:
            self._resolve_key(self.key(obj))
        except KeyError:
            return False
        else:
            return True

    def __bool__(self) -> bool:
        return bool(self._store)


class MultiStore(Generic[T]):
    def __init__(self, store_type: "type[InMemoryStore[T]]") -> None:
        self.store_type = store_type
        self._store: defaultdict[Any, InMemoryStore[T]] = defaultdict(store_type)

    def add(self, identity: Any, obj: T) -> T:
        return self._store[identity].add(obj)

    def store(self, identity: Any) -> "InMemoryStore[T]":
        return self._store[identity]

    def identity(self, obj: T) -> Any:
        return type(obj)

    def remove_all(self) -> None:
        self._store = defaultdict(self.store_type)


class SQLAlchemyInMemoryStore(InMemoryStore[ModelT]):
    id_attribute: str = "id"

    def _update_relationship(self, data: ModelT, ref: ModelT) -> None:  # pragma: no cover
        """Set relationship data fields targeting ref class to ref.

        Example:
        ```python
            class Parent(Base):
                child = relationship("Child")

            class Child(Base):
                pass
        ```

        If data and ref are respectively a `Parent` and `Child` instances,
        then `data.child` will be set to `ref`

        Args:
            data: Model instance on which to update relationships
            ref: Target model instance to set on data relationships
        """
        ref_mapper = object_mapper(ref)
        data_mapper = object_mapper(data)
        for relationship in data_mapper.relationships:
            local = next(iter(relationship.local_columns))
            remote = next(iter(relationship.remote_side))
            if not local.key or not remote.key:
                msg = f"Cannot update relationship {relationship} for model {ref_mapper.class_}"
                raise AdvancedAlchemyError(msg)
            local_attr = data_mapper.get_property_by_column(local).key
            remote_attr = (
                relationship.mapper.get_property_by_column(remote).key if relationship.secondary is None else remote.key
            )
            value = getattr(data, relationship.key)
            if not value and relationship.mapper.class_ is ref_mapper.class_:
                if relationship.uselist:
                    for elem in value:
                        if local_value := getattr(data, local_attr):
                            setattr(elem, remote_attr, local_value)
                else:
                    setattr(data, relationship.key, ref)

    def _update_fks(self, data: ModelT) -> None:  # pragma: no cover
        """Update foreign key fields according to their corresponding relationships.

        This make sure that `data.child_id` == `data.child.id`
        or `data.children[0].parent_id` == `data.id`

        Args:
            data: Instance to be updated
        """
        ref_mapper = object_mapper(data)
        for relationship in ref_mapper.relationships:
            if value := getattr(data, relationship.key):
                local = next(iter(relationship.local_columns))
                remote = next(iter(relationship.remote_side))
                if not local.key or not remote.key:
                    msg = f"Cannot update relationship {relationship} for model {ref_mapper.class_}"
                    raise AdvancedAlchemyError(msg)
                local_attr = ref_mapper.get_property_by_column(local).key
                remote_attr = (
                    relationship.mapper.get_property_by_column(remote).key
                    if relationship.secondary is None
                    else remote.key
                )
                if relationship.uselist:
                    for elem in value:
                        if local_value := getattr(data, local_attr):
                            setattr(elem, remote_attr, local_value)
                        self._update_relationship(elem, data)
                    # Remove duplicates added by orm when updating list items
                    if isinstance(value, list):
                        setattr(data, relationship.key, type(value)(set(value)))  # pyright: ignore[reportUnknownArgumentType]
                else:
                    if remote_value := getattr(value, remote_attr):
                        setattr(data, local_attr, remote_value)
                    self._update_relationship(value, data)

    def _set_defaults(self, data: ModelT) -> None:  # pragma: no cover
        """Set fields with dynamic defaults.

        Args:
            data: Instance to be updated
        """
        for elem in object_mapper(data).c:
            default = getattr(elem, "default", MISSING)
            value = getattr(data, elem.key, MISSING)
            # If value is MISSING, it may be a declared_attr whose name can't be
            # determined from the column/relationship element returned
            if value is not MISSING and not value and not isinstance(default, _MISSING) and default is not None:
                if default.is_scalar:
                    default_value: Any = default.arg
                elif default.is_callable:
                    default_callable = default.arg.__func__ if isinstance(default.arg, staticmethod) else default.arg  # pyright: ignore[reportUnknownMemberType]
                    if (
                        # Eager test because inspect.signature() does not
                        # recognize builtins
                        hasattr(builtins, default_callable.__name__)
                        # If present, context contains information about the current
                        # statement and can be used to access values from other columns.
                        # As we can't reproduce such context in Pydantic, we don't want
                        # include a default_factory in that case.
                        or "context" not in signature(default_callable).parameters
                    ):
                        default_value = default.arg({})  # pyright: ignore
                    else:
                        continue
                else:
                    continue
                setattr(data, elem.key, default_value)

    @staticmethod
    def changed_attrs(data: ModelT) -> "Iterable[str]":  # pragma: no cover
        res: List[str] = []
        mapper = inspect(data)
        if mapper is None:
            msg = f"Cannot inspect {data.__class__} model"
            raise AdvancedAlchemyError(msg)
        attrs = class_mapper(data.__class__).column_attrs
        for attr in attrs:
            hist = getattr(mapper.attrs, attr.key).history
            if hist.has_changes():
                res.append(attr.key)
        return res

    def key(self, obj: ModelT) -> str:
        """Generate a store key from a model instance.

        Supports both single and composite primary keys.

        Args:
            obj: Model instance to generate key from.

        Returns:
            String key for storage. For composite keys, returns tuple representation.
        """
        mapper = object_mapper(obj)
        pk_columns = mapper.primary_key

        if len(pk_columns) == 1:
            # Single PK - use simple string representation
            return str(getattr(obj, mapper.get_property_by_column(pk_columns[0]).key))

        # Composite PK - use tuple of all PK values
        pk_values = tuple(getattr(obj, mapper.get_property_by_column(col).key) for col in pk_columns)
        return str(pk_values)

    def add(self, obj: ModelT) -> ModelT:
        self._set_defaults(obj)
        self._update_fks(obj)
        return super().add(obj)

    def update(self, obj: ModelT) -> ModelT:
        existing = self.get(self.key(obj))
        for attr in self.changed_attrs(obj):
            setattr(existing, attr, getattr(obj, attr))
        self._update_fks(existing)
        return super().update(existing)


class SQLAlchemyMultiStore(MultiStore[ModelT]):
    @staticmethod
    def _new_instances(instance: ModelT) -> "Iterable[ModelT]":
        session = Session()
        session.add(instance)
        relations = list(session.new)
        session.expunge_all()
        return relations

    def _set_relationships_for_fks(self, data: ModelT) -> None:  # pragma: no cover
        """Set relationships matching newly added foreign keys on the instance.

        Example:
            ```python
                class Parent(Base):
                    id: Mapped[UUID]

                class Child(Base):
                    id: Mapped[UUID]
                    parent_id: Mapped[UUID] = mapped_column(ForeignKey("parent.id"))
                    parent: Mapped[Parent] = relationship(Parent)
            ```
            If `data` is a Child instance and `parent_id` is set, `parent` will be set
            to the matching Parent instance if found in the repository

        Args:
            data: The model to update
        """
        obj_mapper = object_mapper(data)
        mappers: dict[str, Mapper[Any]] = {}
        column_relationships: dict[ColumnElement[Any], RelationshipProperty[Any]] = {}

        for mapper in obj_mapper.registry.mappers:
            for table in mapper.tables:
                mappers[table.name] = mapper

        for relationship in obj_mapper.relationships:
            for column in relationship.local_columns:
                column_relationships[column] = relationship
        # sourcery skip: assign-if-exp
        if state := inspect(data):
            new_attrs: dict[str, Any] = state.dict
        else:
            new_attrs = {}

        for column in obj_mapper.columns:
            if not column.foreign_keys:
                continue
            attr_name = obj_mapper.get_property_by_column(column).key
            if attr_name not in new_attrs:
                continue
            remote_mapper = mappers[next(iter(column.foreign_keys))._table_key()]  # noqa: SLF001 # pyright: ignore[reportPrivateUsage]
            try:
                obj = self.store(remote_mapper.class_).get(new_attrs.get(attr_name))
            except KeyError:
                continue

            with contextlib.suppress(KeyError):
                setattr(data, column_relationships[column].key, obj)

    def add(self, identity: Any, obj: ModelT) -> ModelT:
        for relation in self._new_instances(obj):
            instance_type = self.identity(relation)
            self._set_relationships_for_fks(relation)
            if relation in self.store(instance_type):
                continue
            self.store(instance_type).add(relation)
        return obj


def _like_to_regex(pattern_text: str, *, case_sensitive: bool) -> re.Pattern[str]:
    """Compile a SQL LIKE pattern using ``%`` and ``_`` into a regex."""
    parts: list[str] = []
    for char in pattern_text:
        if char == "%":
            parts.append(".*")
        elif char == "_":
            parts.append(".")
        else:
            parts.append(re.escape(char))
    flags = re.DOTALL if case_sensitive else (re.IGNORECASE | re.DOTALL)
    return re.compile(f"^{''.join(parts)}$", flags)


def _cmp_gt(attr: Any, expected: Any) -> bool:
    return bool(attr > expected)


def _cmp_ge(attr: Any, expected: Any) -> bool:
    return bool(attr >= expected)


def _cmp_lt(attr: Any, expected: Any) -> bool:
    return bool(attr < expected)


def _cmp_le(attr: Any, expected: Any) -> bool:
    return bool(attr <= expected)


def _cmp_between(attr: Any, expected: Any) -> bool:
    return bool(expected[0] <= attr <= expected[1])


def _cmp_like(attr: Any, expected: Any) -> bool:
    return isinstance(attr, str) and _like_to_regex(str(expected), case_sensitive=True).match(attr) is not None


def _cmp_ilike(attr: Any, expected: Any) -> bool:
    return isinstance(attr, str) and _like_to_regex(str(expected), case_sensitive=False).match(attr) is not None


def _cmp_startswith(attr: Any, expected: Any) -> bool:
    return isinstance(attr, str) and attr.startswith(str(expected))


def _cmp_istartswith(attr: Any, expected: Any) -> bool:
    return isinstance(attr, str) and attr.lower().startswith(str(expected).lower())


def _cmp_endswith(attr: Any, expected: Any) -> bool:
    return isinstance(attr, str) and attr.endswith(str(expected))


def _cmp_iendswith(attr: Any, expected: Any) -> bool:
    return isinstance(attr, str) and attr.lower().endswith(str(expected).lower())


def _elem_is(left_val: Any, right_val: Any) -> bool:
    return left_val is right_val


def _elem_is_not(left_val: Any, right_val: Any) -> bool:
    return left_val is not right_val


def _elem_eq(left_val: Any, right_val: Any) -> bool:
    return left_val is not None and right_val is not None and bool(left_val == right_val)


def _elem_ne(left_val: Any, right_val: Any) -> bool:
    return left_val is not None and right_val is not None and bool(left_val != right_val)


def _elem_in(left_val: Any, right_val: Any) -> bool:
    return left_val in right_val


def _elem_notin(left_val: Any, right_val: Any) -> bool:
    return left_val not in right_val


_COMPARISON_NON_NULL_OPS: dict[str, Callable[[Any, Any], bool]] = {
    "gt": _cmp_gt,
    "ge": _cmp_ge,
    "lt": _cmp_lt,
    "le": _cmp_le,
    "between": _cmp_between,
    "like": _cmp_like,
    "ilike": _cmp_ilike,
    "startswith": _cmp_startswith,
    "istartswith": _cmp_istartswith,
    "endswith": _cmp_endswith,
    "iendswith": _cmp_iendswith,
}

_BINARY_ELEMENT_OPS: dict[Any, Callable[[Any, Any], bool]] = {
    sa_op.is_: _elem_is,
    sa_op.is_not: _elem_is_not,
    sa_op.eq: _elem_eq,
    sa_op.ne: _elem_ne,
    sa_op.in_op: _elem_in,
    sa_op.notin_op: _elem_notin,
}

_BINARY_ORDERED_OPS: dict[Any, Callable[[Any, Any], bool]] = {
    sa_op.lt: _cmp_lt,
    sa_op.le: _cmp_le,
    sa_op.gt: _cmp_gt,
    sa_op.ge: _cmp_ge,
}


class InMemoryFilterEvaluator:
    """Stateless in-memory evaluator mirroring SQL :class:`~advanced_alchemy.filters.StatementFilter` semantics."""

    __slots__ = ()

    @staticmethod
    def extract_field_name(field: Any) -> str:
        """Extract attribute name from a string or ``InstrumentedAttribute``."""
        if isinstance(field, str):
            return field
        if isinstance(field, InstrumentedAttribute):
            return field.key
        msg = f"{type(field)} columns are not supported in mock repositories (in-memory filtering)"
        raise RepositoryError(msg)

    @staticmethod
    def resolve_attr_value(item: Any, field_name: str) -> Any:
        """Resolve scalar or dotted to-one attribute value on ``item``."""
        current = item
        for part in field_name.split("."):
            if current is None:
                return None
            current = getattr(current, part)
        return current

    @staticmethod
    def apply_limit_offset(result: List[ModelT], limit: int, offset: int) -> List[ModelT]:
        """Slice ``result`` honoring ``offset`` and ``limit`` bounds."""
        return result[offset : offset + limit]

    @classmethod
    def filter_in_collection(
        cls,
        result: List[ModelT],
        field_name: Any,
        values: Collection[Any],
    ) -> List[ModelT]:
        """Filter items whose scalar field or relationship PK belongs to ``values``."""
        if not values:
            return []
        field_str = cls.extract_field_name(field_name)
        rel_filter = cls._relationship_collection_filter(result, field_str, values, negate=False)
        if rel_filter is not None:
            return cls.filter_by_relationship(result, rel_filter)
        return [item for item in result if cls.resolve_attr_value(item, field_str) in values]

    @classmethod
    def filter_not_in_collection(
        cls,
        result: List[ModelT],
        field_name: Any,
        values: Collection[Any],
    ) -> List[ModelT]:
        """Exclude items whose scalar field or relationship PK belongs to ``values``."""
        if not values:
            return result
        field_str = cls.extract_field_name(field_name)
        rel_filter = cls._relationship_collection_filter(result, field_str, values, negate=True)
        if rel_filter is not None:
            return cls.filter_by_relationship(result, rel_filter)
        return [item for item in result if cls.resolve_attr_value(item, field_str) not in values]

    @staticmethod
    def _relationship_collection_filter(
        result: List[ModelT],
        field_str: str,
        values: Collection[Any],
        *,
        negate: bool,
    ) -> Optional[RelationshipFilter]:
        """Convert relationship ``CollectionFilter``/``NotInCollectionFilter`` to a ``RelationshipFilter``."""
        if not result:
            return None
        info = inspect(type(result[0]), raiseerr=False)
        if info is None or not hasattr(info, "mapper"):
            return None
        rel_prop = info.mapper.relationships.get(field_str)
        if rel_prop is None:
            return None
        pk_cols = rel_prop.mapper.primary_key
        if len(pk_cols) != 1 or not pk_cols[0].key:
            msg = (
                f"Relationship collection filtering on '{field_str}' requires a single-column primary key "
                f"on related model {rel_prop.mapper.class_.__name__}"
            )
            raise ValueError(msg)
        return RelationshipFilter(
            relationship=field_str,
            filters=[
                CollectionFilter(field_name=rel_prop.mapper.get_property_by_column(pk_cols[0]).key, values=values)
            ],
            negate=negate,
        )

    @classmethod
    def filter_on_datetime(
        cls,
        result: List[ModelT],
        field_name: Any,
        before: Optional[datetime.datetime] = None,
        after: Optional[datetime.datetime] = None,
        on_or_before: Optional[datetime.datetime] = None,
        on_or_after: Optional[datetime.datetime] = None,
    ) -> List[ModelT]:
        """Filter items satisfying all non-None datetime boundaries."""
        if before is None and after is None and on_or_before is None and on_or_after is None:
            return result
        field_str = cls.extract_field_name(field_name)
        matched: List[ModelT] = []
        for item in result:
            attr = cls.resolve_attr_value(item, field_str)
            if attr is None:
                continue
            if before is not None and attr >= before:
                continue
            if after is not None and attr <= after:
                continue
            if on_or_before is not None and attr > on_or_before:
                continue
            if on_or_after is not None and attr < on_or_after:
                continue
            matched.append(item)
        return matched

    @classmethod
    def filter_by_like(
        cls,
        result: List[ModelT],
        field_name: Union[str, set[str]],
        value: str,
        ignore_case: bool,
        escape_wildcards: bool = False,
    ) -> List[ModelT]:
        """Filter items matching substring ``value`` while preserving input order."""
        pattern_value = re.escape(value) if escape_wildcards else value
        flags = (re.IGNORECASE | re.DOTALL) if ignore_case else re.DOTALL
        pattern = re.compile(rf".*{pattern_value}.*", flags)
        fields = (field_name,) if isinstance(field_name, str) else tuple(field_name)
        return [
            item
            for item in result
            if any(
                isinstance((attr := cls.resolve_attr_value(item, field)), str) and pattern.match(attr) is not None
                for field in fields
            )
        ]

    @classmethod
    def filter_by_not_like(
        cls,
        result: List[ModelT],
        field_name: Union[str, set[str]],
        value: str,
        ignore_case: bool,
        escape_wildcards: bool = False,
    ) -> List[ModelT]:
        """Exclude items matching substring ``value`` while preserving input order."""
        pattern_value = re.escape(value) if escape_wildcards else value
        flags = (re.IGNORECASE | re.DOTALL) if ignore_case else re.DOTALL
        pattern = re.compile(rf".*{pattern_value}.*", flags)
        fields = (field_name,) if isinstance(field_name, str) else tuple(field_name)
        return [
            item
            for item in result
            if not any(
                isinstance((attr := cls.resolve_attr_value(item, field)), str) and pattern.match(attr) is not None
                for field in fields
            )
        ]

    @classmethod
    def order_by(
        cls,
        result: List[ModelT],
        field_name: Any,
        sort_desc: bool = False,
        nulls: Optional[Literal["first", "last"]] = None,
    ) -> List[ModelT]:
        """Order ``result`` by ``field_name`` with SQL-parity NULL placement."""
        attribute = cls.extract_field_name(field_name)
        missing = [item for item in result if cls.resolve_attr_value(item, attribute) is None]
        present = sorted(
            (item for item in result if cls.resolve_attr_value(item, attribute) is not None),
            key=lambda item: cls.resolve_attr_value(item, attribute),
            reverse=sort_desc,
        )
        if not missing:
            return present
        default_nulls: Literal["first", "last"] = "first" if sort_desc else "last"
        effective_nulls = default_nulls if nulls is None else nulls
        return [*missing, *present] if effective_nulls == "first" else [*present, *missing]

    @classmethod
    def filter_by_comparison(cls, result: List[ModelT], filter_: ComparisonFilter) -> List[ModelT]:
        """Evaluate :class:`~advanced_alchemy.filters.ComparisonFilter` in memory."""
        field_str = cls.extract_field_name(filter_.field_name)
        return [
            item
            for item in result
            if cls._matches_comparison(cls.resolve_attr_value(item, field_str), filter_.operator, filter_.value)
        ]

    @staticmethod
    def _matches_comparison(attr: Any, operator_name: str, expected: Any) -> bool:
        """Compare a single scalar field value against a comparison operator."""
        matched = False
        if operator_name in {"eq", "ne", "in", "notin"}:
            if operator_name == "eq":
                matched = bool(attr == expected)
            elif operator_name == "ne":
                matched = attr is not None and bool(attr != expected)
            elif operator_name == "in":
                matched = attr in expected
            else:
                matched = attr not in expected
        elif operator_name == "dateeq":
            if attr is not None:
                attr_date = attr.date() if isinstance(attr, datetime.datetime) else attr
                expected_date = expected.date() if isinstance(expected, datetime.datetime) else expected
                matched = bool(attr_date == expected_date)
        elif operator_name not in _COMPARISON_NON_NULL_OPS:
            msg = f"Invalid operator '{operator_name}'"
            raise ValueError(msg)
        elif attr is not None:
            matched = _COMPARISON_NON_NULL_OPS[operator_name](attr, expected)
        return matched

    @classmethod
    def filter_by_relationship(cls, result: List[ModelT], filter_: RelationshipFilter) -> List[ModelT]:
        """Evaluate :class:`~advanced_alchemy.filters.RelationshipFilter` across loaded ORM attributes."""
        raw_hops = filter_._normalize_hops()  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
        hops: list[str] = []
        for hop in raw_hops:
            if isinstance(hop, str):
                validate_identifier(hop, "relationship")
                hops.append(hop)
            else:
                hops.append(hop.key)
        hop_tuple = tuple(hops)
        matched: List[ModelT] = []
        for item in result:
            cls._validate_relationship_hops(type(item), raw_hops, hop_tuple)
            has_match = cls._matches_relationship_hops(item, hop_tuple, filter_.filters)
            if (not has_match) if filter_.negate else has_match:
                matched.append(item)
        return matched

    @staticmethod
    def _validate_relationship_hops(
        model_cls: type[Any],
        raw_hops: tuple[Any, ...],
        hop_names: tuple[str, ...],
    ) -> None:
        """Validate relationship ownership and existence when ``model_cls`` is SQLAlchemy-mapped."""
        try:
            current_cls: Any = class_mapper(model_cls).class_
        except UnmappedClassError:
            return
        for raw_hop, hop_name in zip(raw_hops, hop_names):
            mapper: Any = class_mapper(current_cls)
            if isinstance(raw_hop, InstrumentedAttribute):
                owner_cls = raw_hop.parent.class_
                owner_matches = issubclass(mapper.class_, owner_cls) or issubclass(owner_cls, mapper.class_)
                if not owner_matches:
                    msg = f"Relationship '{hop_name}' does not belong to model {mapper.class_.__name__}"
                    raise ValueError(msg)
            rel_prop = mapper.relationships.get(hop_name)
            if rel_prop is None:
                msg = f"Relationship '{hop_name}' not found on model {mapper.class_.__name__}"
                raise ValueError(msg)
            current_cls = rel_prop.mapper.class_

    @classmethod
    def _matches_relationship_hops(
        cls,
        instance: Any,
        hops: tuple[str, ...],
        leaf_filters: Any,
    ) -> bool:
        """Recursively traverse loaded relationship hops and evaluate ``leaf_filters``."""
        if not hops:
            return cls.matches_all(instance, leaf_filters)
        head, *tail = hops
        related: Any = getattr(instance, head, None)
        if related is None:
            return False
        if isinstance(related, Collection) and not isinstance(related, (str, bytes, Mapping)):
            candidates: list[Any] = [candidate for candidate in cast("Iterable[Any]", related) if candidate is not None]
        else:
            candidates = [related]
        return any(cls._matches_relationship_hops(candidate, tuple(tail), leaf_filters) for candidate in candidates)

    @classmethod
    def matches_all(cls, instance: Any, filters: Any) -> bool:
        """Return whether a single object satisfies all predicates in ``filters``."""
        return bool(cls.apply_filters([instance], *filters, apply_pagination=False))

    @classmethod
    def _evaluate_column_element(cls, item: Any, element: Any) -> bool:
        """Evaluate basic SQLAlchemy column expressions against a single loaded instance."""
        raw_element: Any = element
        if isinstance(element, BinaryExpression):
            left_key = getattr(element.left, "key", None)
            if left_key is None:
                msg = f"Unsupported expression {element!r} in mock repositories"
                raise RepositoryError(msg)
            left_val = getattr(item, left_key)
            if isinstance(element.right, True_):
                right_val: Any = True
            elif isinstance(element.right, False_):
                right_val = False
            elif isinstance(element.right, Null):
                right_val = None
            elif isinstance(element.right, BindParameter):
                right_val = element.right.value
            else:
                msg = f"Unsupported expression {element!r} in mock repositories"
                raise RepositoryError(msg)
            operator_fn = element.operator
            if operator_fn in _BINARY_ELEMENT_OPS:
                return bool(_BINARY_ELEMENT_OPS[operator_fn](left_val, right_val))
            if operator_fn in _BINARY_ORDERED_OPS:
                return (
                    left_val is not None
                    and right_val is not None
                    and bool(_BINARY_ORDERED_OPS[operator_fn](left_val, right_val))
                )
        if isinstance(element, BooleanClauseList):
            clauses = list(element.clauses)
            if element.operator is sa_op.and_:
                return all(cls._evaluate_column_element(item, clause) for clause in clauses)
            if element.operator is sa_op.or_:
                return any(cls._evaluate_column_element(item, clause) for clause in clauses)
        if isinstance(element, UnaryExpression) and element.operator is sa_op.inv:
            return not cls._evaluate_column_element(item, element.element)
        msg = f"{raw_element.__class__} expressions are not supported in mock repositories (in-memory filtering)"
        raise RepositoryError(msg)

    @classmethod
    def _filter_group(cls, result: List[ModelT], group: FilterGroup) -> List[ModelT]:
        """Evaluate :class:`~advanced_alchemy.filters.FilterGroup` conjunction or disjunction."""
        if not group.filters:
            return result
        if group.logical_operator is and_:
            return cls.apply_filters(result, *group.filters, apply_pagination=False)
        return [
            item
            for item in result
            if any(bool(cls.apply_filters([item], sub_filter, apply_pagination=False)) for sub_filter in group.filters)
        ]

    @staticmethod
    def _extract_multi_branch_filters(multi: MultiFilter, conditions: Any) -> list[StatementFilter]:
        """Convert one logical branch's raw conditions into concrete ``StatementFilter`` objects."""
        if not isinstance(conditions, list):
            return []
        valid_filters: list[StatementFilter] = []
        for condition in cast("Sequence[Any]", conditions):
            if not isinstance(condition, dict):
                continue
            built = multi._create_filter(cast("dict[str, Any]", condition))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
            if built is not None:
                valid_filters.append(built)
        return valid_filters

    @classmethod
    def _filter_multi(cls, result: List[ModelT], multi: MultiFilter) -> List[ModelT]:
        """Evaluate :class:`~advanced_alchemy.filters.MultiFilter` trees in memory."""
        filtered = result
        for filter_type, conditions in multi.filters.items():
            operator = multi._logical_map.get(filter_type)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
            if operator is None:
                continue
            valid_filters = cls._extract_multi_branch_filters(multi, conditions)
            if valid_filters:
                filtered = cls._filter_group(
                    filtered,
                    FilterGroup(logical_operator=operator, filters=valid_filters),  # type: ignore[arg-type]
                )
        return filtered

    @classmethod
    def _apply_collection_or_search_filter(cls, filtered: List[ModelT], filter_: Any) -> Optional[List[ModelT]]:
        """Evaluate collection and text-search filters, returning ``None`` for other filter types."""
        raw_filter: Any = filter_
        matched: Optional[List[ModelT]] = None
        if isinstance(filter_, NotInCollectionFilter):
            not_in_filter = cast("NotInCollectionFilter[Any]", raw_filter)
            matched = (
                filtered
                if not_in_filter.values is None  # pyright: ignore[reportUnnecessaryComparison]
                else cls.filter_not_in_collection(filtered, not_in_filter.field_name, not_in_filter.values)
            )
        elif isinstance(filter_, CollectionFilter):
            in_filter = cast("CollectionFilter[Any]", raw_filter)
            matched = (
                filtered
                if in_filter.values is None  # pyright: ignore[reportUnnecessaryComparison]
                else cls.filter_in_collection(filtered, in_filter.field_name, in_filter.values)
            )
        elif isinstance(filter_, NotInSearchFilter):
            matched = cls.filter_by_not_like(
                filtered,
                {cls.extract_field_name(f) for f in filter_.normalized_field_names},
                value=filter_.value,
                ignore_case=bool(filter_.ignore_case),
                escape_wildcards=filter_.escape_wildcards,
            )
        elif isinstance(filter_, SearchFilter):
            matched = cls.filter_by_like(
                filtered,
                {cls.extract_field_name(f) for f in filter_.normalized_field_names},
                value=filter_.value,
                ignore_case=bool(filter_.ignore_case),
                escape_wildcards=filter_.escape_wildcards,
            )
        return matched

    @classmethod
    def _apply_single_filter(cls, filtered: List[ModelT], filter_: Any) -> List[ModelT]:
        """Apply one non-ordering, non-pagination filter to ``filtered``."""
        result: Optional[List[ModelT]] = None
        if isinstance(filter_, BeforeAfter):
            result = cls.filter_on_datetime(
                filtered, field_name=filter_.field_name, before=filter_.before, after=filter_.after
            )
        elif isinstance(filter_, OnBeforeAfter):
            result = cls.filter_on_datetime(
                filtered,
                field_name=filter_.field_name,
                on_or_before=filter_.on_or_before,
                on_or_after=filter_.on_or_after,
            )
        elif isinstance(filter_, BooleanFilter):
            if filter_.value is None:
                result = filtered
            else:
                field_str = cls.extract_field_name(filter_.field_name)
                result = [item for item in filtered if cls.resolve_attr_value(item, field_str) == filter_.value]
        elif isinstance(filter_, NullFilter):
            field_str = cls.extract_field_name(filter_.field_name)
            result = [item for item in filtered if cls.resolve_attr_value(item, field_str) is None]
        elif isinstance(filter_, NotNullFilter):
            field_str = cls.extract_field_name(filter_.field_name)
            result = [item for item in filtered if cls.resolve_attr_value(item, field_str) is not None]
        elif isinstance(filter_, ComparisonFilter):
            result = cls.filter_by_comparison(filtered, filter_)
        elif (collection_or_search := cls._apply_collection_or_search_filter(filtered, filter_)) is not None:
            result = collection_or_search
        elif isinstance(filter_, FilterGroup):
            result = cls._filter_group(filtered, filter_)
        elif isinstance(filter_, RelationshipFilter):
            result = cls.filter_by_relationship(filtered, filter_)
        elif isinstance(filter_, MultiFilter):
            result = cls._filter_multi(filtered, filter_)
        elif isinstance(filter_, ColumnElement):
            result = [item for item in filtered if cls._evaluate_column_element(item, filter_)]
        else:
            msg = f"Unexpected filter: {filter_}"
            raise RepositoryError(msg)
        return result

    @classmethod
    def apply_filters(
        cls,
        result: List[ModelT],
        *filters: Any,
        apply_pagination: bool = True,
    ) -> List[ModelT]:
        """Apply filters and ordering to ``result`` with SQL-compatible semantics."""
        pending_orders: list[OrderBy] = []
        pending_pagination: list[LimitOffset] = []
        filtered = result
        for filter_ in filters:
            if isinstance(filter_, LimitOffset):
                if apply_pagination:
                    pending_pagination.append(filter_)
            elif isinstance(filter_, OrderBy):
                pending_orders.append(filter_)
            else:
                filtered = cls._apply_single_filter(filtered, filter_)

        for order_filter in reversed(pending_orders):
            filtered = cls.order_by(
                filtered,
                order_filter.field_name,
                sort_desc=order_filter.sort_order == "desc",
                nulls=order_filter.nulls,
            )
        for pagination in pending_pagination:
            filtered = cls.apply_limit_offset(filtered, pagination.limit, pagination.offset)
        return filtered
