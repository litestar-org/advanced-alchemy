"""Native and ORM fallback upsert planning utilities for SQLAlchemy repositories."""

import contextlib
import datetime
import decimal
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Final, Generic, Optional, Union, cast

from sqlalchemy import Dialect, Table, and_, any_, inspect, or_, tuple_
from sqlalchemy.sql import ColumnElement

from advanced_alchemy.base import ModelProtocol, model_to_dict
from advanced_alchemy.exceptions import RepositoryError
from advanced_alchemy.operations import UpsertStrategy, resolve_column_default
from advanced_alchemy.repository._typing import arrays_equal, is_numpy_array
from advanced_alchemy.repository.typing import MISSING, ModelT
from advanced_alchemy.types.file_object import StoredObject

if TYPE_CHECKING:
    from sqlalchemy.orm import InstrumentedAttribute

__all__ = (
    "DEFAULT_INSERTMANYVALUES_MAX_PARAMETERS",
    "DEFAULT_SAFE_TYPES",
    "_UpsertPlanningMixin",
    "compare_values",
    "has_upsert_update_intent",
    "was_attribute_set",
)

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


def _get_instrumented_attr(
    model: type[ModelProtocol],
    key: "Union[str, InstrumentedAttribute[Any]]",
) -> "InstrumentedAttribute[Any]":
    """Retrieve an instrumented attribute from a SQLAlchemy model."""
    if isinstance(key, str):
        return cast("InstrumentedAttribute[Any]", getattr(model, key))
    return key


def was_attribute_set(instance: Any, mapper: Any, attr_name: str) -> bool:
    """Check if an attribute was explicitly set on a model instance.

    This function distinguishes between attributes that were explicitly set
    (even to ``None``) versus attributes that are simply uninitialized and defaulting
    to ``None``. This is crucial for partial updates where only modified fields
    should be copied.

    Args:
        instance: The model instance to check.
        mapper: The SQLAlchemy mapper/inspector for the instance.
        attr_name: The name of the attribute to check.

    Returns:
        bool: ``True`` if the attribute was explicitly set, ``False`` if uninitialized.
    """
    try:
        attr_state = mapper.attrs.get(attr_name)
        if attr_state is None:
            return False

        history = attr_state.history
        if history.has_changes():
            return True

        return hasattr(instance, "__dict__") and attr_name in instance.__dict__
    except (AttributeError, KeyError):  # pragma: no cover
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
        bool: ``True`` if the attribute has update intent, ``False`` otherwise.
    """
    if instance_state.transient:
        return was_attribute_set(instance, instance_state, attribute_name)
    attribute_state = instance_state.attrs.get(attribute_name)
    return bool(attribute_state is not None and attribute_state.history.has_changes())


def compare_values(existing_value: Any, new_value: Any) -> bool:
    """Safely compare two values, handling numpy arrays and other special types.

    Args:
        existing_value: The current value to compare.
        new_value: The new value to compare against.

    Returns:
        bool: ``True`` if values are equal, ``False`` otherwise.
    """
    if existing_value is None and new_value is None:
        return True
    if existing_value is None or new_value is None:
        return False

    if is_numpy_array(existing_value) or is_numpy_array(new_value):
        if not (is_numpy_array(existing_value) and is_numpy_array(new_value)):
            return False
        return arrays_equal(existing_value, new_value)

    try:
        return bool(existing_value == new_value)
    except (ValueError, TypeError):
        return False


class _UpsertPlanningMixin(Generic[ModelT]):
    """Mixin providing native and ORM fallback upsert planning for SQLAlchemy repositories."""

    model_type: type[ModelT]
    _prefer_any: bool = False
    _dialect: Dialect

    def _type_must_use_in_instead_of_any(self, matched_values: Sequence[Any], field_type: Any = None) -> bool:
        """Determine if ``field.in_()`` should be used instead of ``any_()`` for compatibility.

        Args:
            matched_values: Values to be used in the filter.
            field_type: Optional SQLAlchemy TypeEngine from the column.

        Returns:
            bool: ``True`` if ``field.in_()`` should be used instead of ``any_()``.
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
        match_columns = [_get_instrumented_attr(self.model_type, field_name) for field_name in match_fields]
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
        """Detect duplicate source keys, which dialects treat differently."""
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
        """Detect batches whose semantics depend on the ORM unit of work."""
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
        """Resolve columns that have uniform update intent across the batch."""
        if not data:
            return []
        table = cast("Table", self.model_type.__table__)
        if any(bool(col.onupdate is not None and col.onupdate.is_clause_element) for col in table.columns):
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
        """Detect row shapes whose portable semantics require the ORM fallback."""
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
            if bool(column.default is not None and column.default.is_clause_element)
        }
        return any(not sql_default_columns.issubset(row.keys()) for row in input_rows)

    def _extract_upsert_row(self, instance: ModelT) -> dict[str, Any]:
        """Convert a model instance to a row dict suitable for native upsert execution."""
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
            if value_default is not None and value_default.is_clause_element:
                prepared_row.pop(column.key, None)
                continue
            default_value = getattr(value_default, "arg", None) if value_default is not None else None
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
        """Restore input ordering because RETURNING/OUTPUT order is undefined."""
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
