# ruff: noqa: PLR0911
import builtins
import contextlib
import datetime
import re
from collections import abc, defaultdict
from collections.abc import Callable, Iterable
from inspect import isclass, signature
from typing import TYPE_CHECKING, Any, Generic, List, Literal, Optional, Union, cast, overload

from sqlalchemy import BinaryExpression, BooleanClauseList, Column, ColumnElement, inspect, or_
from sqlalchemy.exc import NoInspectionAvailable
from sqlalchemy.orm import InstrumentedAttribute, RelationshipProperty, Session, object_mapper
from sqlalchemy.sql import operators as sql_op
from sqlalchemy.sql.elements import BindParameter, ClauseList, False_, Grouping, True_, UnaryExpression
from typing_extensions import TypeVar

from advanced_alchemy.exceptions import AdvancedAlchemyError, RepositoryError
from advanced_alchemy.filters import (
    VALID_OPERATORS,
    BeforeAfter,
    BooleanFilter,
    CollectionFilter,
    ComparisonFilter,
    ExistsFilter,
    FilterGroup,
    LimitOffset,
    MultiFilter,
    NotExistsFilter,
    NotInCollectionFilter,
    NotInSearchFilter,
    NotNullFilter,
    NullFilter,
    OnBeforeAfter,
    OrderBy,
    SearchFilter,
    StatementFilter,
)
from advanced_alchemy.repository._util import (
    column_has_defaults,
    compare_values,
    get_primary_key_info,
    was_attribute_set,
)
from advanced_alchemy.repository.typing import (
    _MISSING,  # pyright: ignore[reportPrivateUsage]
    MISSING,
    ModelT,
    OrderingPair,
)
from advanced_alchemy.utils.deprecation import warn_deprecation

if TYPE_CHECKING:
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

    def get_or_none(self, key: Any, default: Any = _NotSet) -> "Union[T, None]":
        return self.get(key) if default is _NotSet else self.get(key, default)

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
        for relationship in object_mapper(data).relationships:
            local = next(iter(relationship.local_columns))
            remote = next(iter(relationship.remote_side))
            if not local.key or not remote.key:
                msg = f"Cannot update relationship {relationship} for model {ref_mapper.class_}"
                raise AdvancedAlchemyError(msg)
            value = getattr(data, relationship.key)
            if not value and relationship.mapper.class_ is ref_mapper.class_:
                if relationship.uselist:
                    for elem in value:
                        if local_value := getattr(data, local.key):
                            setattr(elem, remote.key, local_value)
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
                if relationship.uselist:
                    for elem in value:
                        if local_value := getattr(data, local.key):
                            setattr(elem, remote.key, local_value)
                        self._update_relationship(elem, data)
                    # Remove duplicates added by orm when updating list items
                    if isinstance(value, list):
                        setattr(data, relationship.key, type(value)(set(value)))  # pyright: ignore[reportUnknownArgumentType]
                else:
                    if remote_value := getattr(value, remote.key):
                        setattr(data, local.key, remote_value)
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
            if value is None and not isinstance(default, _MISSING) and default is not None:
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
        try:
            mapper = inspect(data)
        except NoInspectionAvailable as exc:
            msg = f"Cannot inspect {data.__class__} model"
            raise AdvancedAlchemyError(msg) from exc
        if mapper is None:
            msg = f"Cannot inspect {data.__class__} model"
            raise AdvancedAlchemyError(msg)
        for column in mapper.mapper.columns:
            field_name = column.key
            new_field_value = getattr(data, field_name, MISSING)
            if new_field_value is MISSING:
                continue
            if new_field_value is None and column_has_defaults(column):
                continue
            if was_attribute_set(data, mapper, field_name):
                res.append(field_name)
        for relationship in mapper.mapper.relationships:
            if relationship.viewonly or relationship.lazy in {
                "write_only",
                "dynamic",
                "raise",
                "raise_on_sql",
            }:
                continue
            if was_attribute_set(data, mapper, relationship.key):
                res.append(relationship.key)
        return res

    def key(self, obj: ModelT) -> str:
        """Generate a store key from a model instance.

        Supports both single and composite primary keys.

        Args:
            obj: Model instance to generate key from.

        Returns:
            String key for storage. For composite keys, returns tuple representation.
        """
        _pk_columns, pk_attr_names = get_primary_key_info(type(obj))
        if len(pk_attr_names) > 1:
            pk_values = tuple(getattr(obj, attr_name) for attr_name in pk_attr_names)
            return str(pk_values)
        attr_name = pk_attr_names[0] if pk_attr_names else self.id_attribute
        return str(getattr(obj, attr_name, getattr(obj, self.id_attribute, None)))

    def add(self, obj: ModelT) -> ModelT:
        self._set_defaults(obj)
        self._update_fks(obj)
        return super().add(obj)

    def update(self, obj: ModelT) -> ModelT:
        existing = self.get(self.key(obj))
        for attr in self.changed_attrs(obj):
            new_value = getattr(obj, attr, MISSING)
            existing_value = getattr(existing, attr, MISSING)
            if new_value is not MISSING and not compare_values(existing_value, new_value):
                setattr(existing, attr, new_value)
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
            if column.key not in new_attrs or not column.foreign_keys:
                continue
            remote_mapper = mappers[next(iter(column.foreign_keys))._table_key()]  # noqa: SLF001 # pyright: ignore[reportPrivateUsage]
            try:
                obj = self.store(remote_mapper.class_).get(new_attrs.get(column.key))
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


class InMemoryFilterEvaluator:
    """Synchronous filter, ordering, pagination, and SQLAlchemy AST evaluator for in-memory repositories."""

    @staticmethod
    def extract_field_name(field: "Union[str, ColumnElement[Any], InstrumentedAttribute[Any]]") -> str:
        """Extract string field name from string, InstrumentedAttribute, or Column."""
        if isinstance(field, str):
            return field
        if isinstance(field, InstrumentedAttribute):
            return field.key
        if isinstance(field, Column):
            return field.key
        msg = f"{type(field)} columns are not supported in mock repositories (in-memory filtering)"
        raise RepositoryError(msg)

    @staticmethod
    def apply_limit_offset_pagination(result: List[ModelT], limit: int, offset: int) -> List[ModelT]:
        """Slice items using SQL LIMIT/OFFSET semantics (`result[offset : offset + limit]`)."""
        return result[offset : offset + limit]

    @classmethod
    def filter_in_collection(
        cls,
        result: List[ModelT],
        field_name: "Union[str, ColumnElement[Any], InstrumentedAttribute[Any]]",
        values: abc.Collection[Any],
    ) -> List[ModelT]:
        """Filter items whose field value is in `values` (returning `[]` when `values` is empty)."""
        if not values:
            return []
        field_str = cls.extract_field_name(field_name)
        return [item for item in result if getattr(item, field_str) in values]

    @classmethod
    def filter_not_in_collection(
        cls,
        result: List[ModelT],
        field_name: "Union[str, ColumnElement[Any], InstrumentedAttribute[Any]]",
        values: abc.Collection[Any],
    ) -> List[ModelT]:
        """Filter items whose field value is not in `values`."""
        if not values:
            return result
        field_str = cls.extract_field_name(field_name)
        return [item for item in result if getattr(item, field_str) not in values]

    @classmethod
    def filter_on_datetime_field(
        cls,
        result: List[ModelT],
        field_name: "Union[str, ColumnElement[Any], InstrumentedAttribute[Any]]",
        before: Optional[datetime.datetime] = None,
        after: Optional[datetime.datetime] = None,
        on_or_before: Optional[datetime.datetime] = None,
        on_or_after: Optional[datetime.datetime] = None,
    ) -> List[ModelT]:
        """Filter items by conjunctive (`AND`) datetime range bounds."""
        field_str = cls.extract_field_name(field_name)
        result_: List[ModelT] = []
        for item in result:
            attr: Optional[datetime.datetime] = getattr(item, field_str, None)
            if attr is None:
                continue
            if before is not None and not (attr < before):
                continue
            if after is not None and not (attr > after):
                continue
            if on_or_before is not None and not (attr <= on_or_before):
                continue
            if on_or_after is not None and not (attr >= on_or_after):
                continue
            result_.append(item)
        return result_

    @staticmethod
    def filter_by_like(
        result: List[ModelT],
        field_name: Union[str, set[str]],
        value: str,
        ignore_case: bool,
        escape_wildcards: bool = False,
    ) -> List[ModelT]:
        """Filter items matching a substring pattern across one or more fields (`OR` semantics)."""
        if escape_wildcards:
            value = re.escape(value)
        pattern = re.compile(rf".*{value}.*", re.IGNORECASE) if ignore_case else re.compile(rf".*{value}.*")
        fields = {field_name} if isinstance(field_name, str) else field_name
        matched_ids: set[int] = set()
        filtered: List[ModelT] = []
        for item in result:
            if id(item) in matched_ids:
                continue
            for field in fields:
                attr_val = getattr(item, field, None)
                if isinstance(attr_val, str) and pattern.match(attr_val):
                    matched_ids.add(id(item))
                    filtered.append(item)
                    break
        return filtered

    @staticmethod
    def filter_by_not_like(
        result: List[ModelT],
        field_name: Union[str, set[str]],
        value: str,
        ignore_case: bool,
        escape_wildcards: bool = False,
    ) -> List[ModelT]:
        """Exclude items matching a substring pattern across any of the specified fields (`AND NOT` semantics)."""
        if escape_wildcards:
            value = re.escape(value)
        pattern = re.compile(rf".*{value}.*", re.IGNORECASE) if ignore_case else re.compile(rf".*{value}.*")
        fields = {field_name} if isinstance(field_name, str) else field_name
        excluded_ids: set[int] = set()
        for item in result:
            for field in fields:
                attr_val = getattr(item, field, None)
                if isinstance(attr_val, str) and pattern.match(attr_val):
                    excluded_ids.add(id(item))
                    break
        return [item for item in result if id(item) not in excluded_ids]

    @classmethod
    def filter_comparison(cls, result: List[ModelT], filter_: ComparisonFilter) -> List[ModelT]:
        """Evaluate a `ComparisonFilter` against `result`."""
        if filter_.operator not in VALID_OPERATORS:
            msg = f"Invalid operator '{filter_.operator}'. Must be one of: {', '.join(sorted(VALID_OPERATORS))}"
            raise ValueError(msg)
        field_str = cls.extract_field_name(filter_.field_name)
        op_name = filter_.operator
        target = filter_.value
        matched: List[ModelT] = []
        for item in result:
            val = getattr(item, field_str, None)
            if cls._eval_comparison_op(val, op_name, target):
                matched.append(item)
        return matched

    @staticmethod
    def _like_to_regex(pattern_str: str, ignore_case: bool = False) -> re.Pattern[str]:
        parts: List[str] = ["^"]
        for ch in pattern_str:
            if ch == "%":
                parts.append(".*")
            elif ch == "_":
                parts.append(".")
            else:
                parts.append(re.escape(ch))
        parts.append("$")
        flags = re.IGNORECASE | re.DOTALL if ignore_case else re.DOTALL
        return re.compile("".join(parts), flags)

    @classmethod
    def _eval_comparison_op(cls, val: Any, op_name: str, target: Any) -> bool:
        if op_name == "eq":
            return bool(val == target)
        if op_name == "ne":
            return bool(val != target)
        if val is None:
            return False
        if op_name == "gt":
            return bool(val > target)
        if op_name == "ge":
            return bool(val >= target)
        if op_name == "lt":
            return bool(val < target)
        if op_name == "le":
            return bool(val <= target)
        if op_name == "in":
            return bool(val in target)
        if op_name == "notin":
            return bool(val not in target)
        if op_name == "between":
            return bool(target[0] <= val <= target[1])
        if op_name == "like":
            return isinstance(val, str) and bool(cls._like_to_regex(str(target), ignore_case=False).match(val))
        if op_name == "ilike":
            return isinstance(val, str) and bool(cls._like_to_regex(str(target), ignore_case=True).match(val))
        if op_name == "startswith":
            return isinstance(val, str) and val.startswith(str(target))
        if op_name == "istartswith":
            return isinstance(val, str) and val.lower().startswith(str(target).lower())
        if op_name == "endswith":
            return isinstance(val, str) and val.endswith(str(target))
        if op_name == "iendswith":
            return isinstance(val, str) and val.lower().endswith(str(target).lower())
        if op_name == "dateeq":
            val_date = val.date() if isinstance(val, datetime.datetime) else val
            target_date = target.date() if isinstance(target, datetime.datetime) else target
            return bool(val_date == target_date)
        return False

    @classmethod
    def filter_boolean(cls, result: List[ModelT], filter_: BooleanFilter) -> List[ModelT]:
        """Evaluate a `BooleanFilter` against `result`."""
        if filter_.value is None:
            return result
        field_str = cls.extract_field_name(filter_.field_name)
        return [item for item in result if getattr(item, field_str, None) == filter_.value]

    @classmethod
    def filter_null(cls, result: List[ModelT], filter_: NullFilter) -> List[ModelT]:
        """Evaluate a `NullFilter` (`IS NULL`) against `result`."""
        field_str = cls.extract_field_name(filter_.field_name)
        return [item for item in result if getattr(item, field_str, None) is None]

    @classmethod
    def filter_not_null(cls, result: List[ModelT], filter_: NotNullFilter) -> List[ModelT]:
        """Evaluate a `NotNullFilter` (`IS NOT NULL`) against `result`."""
        field_str = cls.extract_field_name(filter_.field_name)
        return [item for item in result if getattr(item, field_str, None) is not None]

    @classmethod
    def filter_group(cls, result: List[ModelT], filter_: FilterGroup) -> List[ModelT]:
        """Evaluate a `FilterGroup` (`and_` / `or_`) recursively against `result`."""
        if not filter_.filters:
            return result
        is_or = filter_.logical_operator is or_ or getattr(filter_.logical_operator, "__name__", "") == "or_"
        if is_or:
            matched_ids: set[int] = set()
            for sub_filter in filter_.filters:
                sub_matches = cls.apply_filters(result, sub_filter, apply_pagination=False)
                for item in sub_matches:
                    matched_ids.add(id(item))
            return [item for item in result if id(item) in matched_ids]
        current = result
        for sub_filter in filter_.filters:
            current = cls.apply_filters(current, sub_filter, apply_pagination=False)
        return current

    @classmethod
    def filter_multi(cls, result: List[ModelT], filter_: MultiFilter) -> List[ModelT]:
        """Evaluate a `MultiFilter` dictionary tree against `result`."""
        current = result
        for filter_type, conditions in filter_.filters.items():
            operator = cast(
                "Optional[Callable[..., ColumnElement[bool]]]",
                filter_._logical_map.get(filter_type),  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
            )
            if operator and isinstance(conditions, list):
                valid_filters: List[StatementFilter] = []
                for cond in conditions:  # pyright: ignore[reportUnknownVariableType]
                    if isinstance(cond, dict):
                        cond_dict = cast("dict[str, Any]", cond)
                        filter_instance = filter_._create_filter(cond_dict)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
                        if filter_instance is not None:
                            valid_filters.append(filter_instance)
                if valid_filters:
                    group = FilterGroup(logical_operator=operator, filters=valid_filters)
                    current = cls.filter_group(current, group)
        return current

    @classmethod
    def filter_exists(cls, result: List[ModelT], filter_: Union[ExistsFilter, NotExistsFilter]) -> List[ModelT]:
        """Evaluate an `ExistsFilter` or `NotExistsFilter` against `result`."""
        negate = isinstance(filter_, NotExistsFilter)
        if not filter_.values:
            return result if negate else []
        is_and = filter_.operator == "and"
        matched: List[ModelT] = []
        for item in result:
            outcomes = [bool(cls.evaluate_sql_expression(item, expr)) for expr in filter_.values]
            exists_match = all(outcomes) if is_and else any(outcomes)
            if (not exists_match) if negate else exists_match:
                matched.append(item)
        return matched

    @classmethod
    def evaluate_sql_expression(cls, item: Any, expr: Any) -> Any:
        """Evaluate a SQLAlchemy `ColumnElement` AST expression against an in-memory model instance."""
        if isinstance(expr, Grouping):
            return cls.evaluate_sql_expression(item, expr.element)  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType]
        if isinstance(expr, True_):
            return True
        if isinstance(expr, False_):
            return False
        if isinstance(expr, BindParameter):
            return expr.value  # pyright: ignore[reportUnknownMemberType,reportUnknownVariableType]
        if isinstance(expr, BooleanClauseList):
            if expr.operator is sql_op.or_:
                return any(bool(cls.evaluate_sql_expression(item, clause)) for clause in expr.clauses)
            return all(bool(cls.evaluate_sql_expression(item, clause)) for clause in expr.clauses)
        if isinstance(expr, ClauseList):
            return tuple(cls.evaluate_sql_expression(item, clause) for clause in expr.clauses)
        if isinstance(expr, UnaryExpression):
            inner = cls.evaluate_sql_expression(item, expr.element)
            if expr.operator is sql_op.inv:
                return not bool(inner)
            return inner
        if isinstance(expr, InstrumentedAttribute):
            return getattr(item, expr.key, None)
        if isinstance(expr, Column):
            return getattr(item, expr.key, None)
        if isinstance(expr, BinaryExpression):
            left = cls.evaluate_sql_expression(item, expr.left)
            right = cls.evaluate_sql_expression(item, expr.right)
            return cls._eval_binary_operator(left, right, expr.operator)
        if isinstance(expr, ColumnElement):
            key = getattr(expr, "key", None) or getattr(expr, "name", None)  # pyright: ignore[reportUnknownArgumentType]
            if isinstance(key, str) and hasattr(item, key):
                return getattr(item, key)
        return cast("Any", expr)

    @classmethod
    def _eval_binary_operator(cls, left: Any, right: Any, operator: Any) -> bool:
        if operator in (sql_op.is_, sql_op.eq):
            if right is None and operator is sql_op.is_:
                return left is None
            return bool(compare_values(left, right) if not isinstance(left, (int, str, float, bool)) else left == right)
        if operator in (sql_op.is_not, sql_op.ne):
            if right is None and operator is sql_op.is_not:
                return left is not None
            return bool(
                not compare_values(left, right) if not isinstance(left, (int, str, float, bool)) else left != right
            )
        if operator is sql_op.in_op:
            if right is None:
                return False
            return bool(left in right)
        if operator is sql_op.notin_op:
            if right is None:
                return True
            return bool(left not in right)
        if left is None:
            return False
        if operator is sql_op.gt:
            return bool(left > right)
        if operator is sql_op.ge:
            return bool(left >= right)
        if operator is sql_op.lt:
            return bool(left < right)
        if operator is sql_op.le:
            return bool(left <= right)
        if operator is sql_op.between_op and isinstance(right, tuple):
            right_tuple: tuple[Any, ...] = right  # pyright: ignore[reportUnknownVariableType]
            if len(right_tuple) > 1:
                return bool(right_tuple[0] <= left <= right_tuple[1])
        right_str = str(cast("Any", right))
        if operator is sql_op.like_op:
            return isinstance(left, str) and bool(cls._like_to_regex(right_str, ignore_case=False).match(left))
        if operator is sql_op.ilike_op:
            return isinstance(left, str) and bool(cls._like_to_regex(right_str, ignore_case=True).match(left))
        if operator is sql_op.not_like_op:
            return isinstance(left, str) and not bool(cls._like_to_regex(right_str, ignore_case=False).match(left))
        if operator is sql_op.not_ilike_op:
            return isinstance(left, str) and not bool(cls._like_to_regex(right_str, ignore_case=True).match(left))
        if operator is sql_op.startswith_op:
            return isinstance(left, str) and left.startswith(right_str)
        if operator is sql_op.endswith_op:
            return isinstance(left, str) and left.endswith(right_str)
        if operator is sql_op.contains_op:
            return isinstance(left, str) and (right_str in left)
        try:
            return bool(operator(left, right))
        except Exception:  # noqa: BLE001
            return False

    @classmethod
    def order_by(
        cls,
        result: List[ModelT],
        field_name: "Union[str, ColumnElement[Any], InstrumentedAttribute[Any]]",
        sort_desc: bool = False,
        nulls: Optional[Literal["first", "last"]] = None,
    ) -> List[ModelT]:
        """Sort `result` by `field_name` with optional `nulls` placement (`first` or `last`)."""
        attribute = cls.extract_field_name(field_name)
        missing = [item for item in result if getattr(item, attribute, None) is None]
        present = sorted(
            (item for item in result if getattr(item, attribute, None) is not None),
            key=lambda item: getattr(item, attribute),
            reverse=sort_desc,
        )
        if nulls == "first":
            return [*missing, *present]
        if nulls == "last":
            return [*present, *missing]
        return [*present, *missing] if sort_desc else [*missing, *present]

    @classmethod
    def apply_order_by_list(
        cls,
        result: List[ModelT],
        order_by: Optional[Union[List[OrderingPair], OrderingPair]],
    ) -> List[ModelT]:
        """Apply repository `order_by` pairs or unary expressions to `result`."""
        if order_by is None:
            return result
        order_list = order_by if isinstance(order_by, list) else [order_by]
        for order_item in reversed(order_list):
            if isinstance(order_item, UnaryExpression):
                field_name = cls.extract_field_name(cast("Any", order_item.element))
                is_desc = order_item.modifier is sql_op.desc_op
                result = cls.order_by(result, field_name, sort_desc=is_desc)
            else:
                result = cls.order_by(result, order_item[0], sort_desc=bool(order_item[1]))
        return result

    @classmethod
    def apply_filters(
        cls,
        result: List[ModelT],
        *filters: Union[StatementFilter, ColumnElement[bool]],
        apply_pagination: bool = True,
    ) -> List[ModelT]:
        """Apply `StatementFilter` instances and SQLAlchemy boolean expressions to `result`."""
        pagination_filters: List[LimitOffset] = []
        for filter_ in filters:
            if isinstance(filter_, LimitOffset):
                if apply_pagination:
                    pagination_filters.append(filter_)
            elif isinstance(filter_, BeforeAfter):
                result = cls.filter_on_datetime_field(
                    result,
                    field_name=filter_.field_name,
                    before=filter_.before,
                    after=filter_.after,
                )
            elif isinstance(filter_, OnBeforeAfter):
                result = cls.filter_on_datetime_field(
                    result,
                    field_name=filter_.field_name,
                    on_or_before=filter_.on_or_before,
                    on_or_after=filter_.on_or_after,
                )
            elif isinstance(filter_, NotInCollectionFilter):
                values: Optional[abc.Collection[Any]] = filter_.values  # pyright: ignore[reportUnknownMemberType,reportUnknownVariableType]
                if values is not None:
                    result = cls.filter_not_in_collection(result, filter_.field_name, values)  # pyright: ignore[reportUnknownArgumentType]
            elif isinstance(filter_, CollectionFilter):
                in_values: Optional[abc.Collection[Any]] = filter_.values  # pyright: ignore[reportUnknownMemberType,reportUnknownVariableType]
                if in_values is not None:
                    result = cls.filter_in_collection(result, filter_.field_name, in_values)  # pyright: ignore[reportUnknownArgumentType]
            elif isinstance(filter_, OrderBy):
                result = cls.order_by(
                    result,
                    filter_.field_name,
                    sort_desc=filter_.sort_order == "desc",
                    nulls=filter_.nulls,
                )
            elif isinstance(filter_, NotInSearchFilter):
                result = cls.filter_by_not_like(
                    result,
                    filter_.field_name,
                    value=filter_.value,
                    ignore_case=bool(filter_.ignore_case),
                    escape_wildcards=filter_.escape_wildcards,
                )
            elif isinstance(filter_, SearchFilter):
                result = cls.filter_by_like(
                    result,
                    filter_.field_name,
                    value=filter_.value,
                    ignore_case=bool(filter_.ignore_case),
                    escape_wildcards=filter_.escape_wildcards,
                )
            elif isinstance(filter_, ComparisonFilter):
                result = cls.filter_comparison(result, filter_)
            elif isinstance(filter_, BooleanFilter):
                result = cls.filter_boolean(result, filter_)
            elif isinstance(filter_, NullFilter):
                result = cls.filter_null(result, filter_)
            elif isinstance(filter_, NotNullFilter):
                result = cls.filter_not_null(result, filter_)
            elif isinstance(filter_, FilterGroup):
                result = cls.filter_group(result, filter_)
            elif isinstance(filter_, MultiFilter):
                result = cls.filter_multi(result, filter_)
            elif isinstance(filter_, (ExistsFilter, NotExistsFilter)):
                result = cls.filter_exists(result, filter_)
            elif isinstance(filter_, ColumnElement):
                result = [item for item in result if bool(cls.evaluate_sql_expression(item, filter_))]
            else:
                msg = f"Unexpected filter: {filter_}"
                raise RepositoryError(msg)
        for pag in pagination_filters:
            result = cls.apply_limit_offset_pagination(result, pag.limit, pag.offset)
        return result

    @classmethod
    def paginate_items(
        cls,
        result: List[ModelT],
        *filters: Union[StatementFilter, ColumnElement[bool]],
    ) -> List[ModelT]:
        """Apply only `LimitOffset` pagination filters from `filters` to `result`."""
        for filter_ in filters:
            if isinstance(filter_, LimitOffset):
                result = cls.apply_limit_offset_pagination(result, filter_.limit, filter_.offset)
        return result

    @staticmethod
    def filter_by_kwargs(
        result: Iterable[ModelT],
        kwargs: dict[str, Any],
    ) -> List[ModelT]:
        """Filter `result` by exact attribute equality for all key/value pairs in `kwargs`."""
        try:
            return [item for item in result if all(getattr(item, field) == value for field, value in kwargs.items())]
        except AttributeError as error:
            raise RepositoryError from error
