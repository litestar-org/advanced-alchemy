"""Pagination filters: limit/offset and keyset (cursor)."""

import functools
from abc import ABC
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable, Literal, Optional, Union, cast

from sqlalchemy import ColumnElement, Integer, Select, and_, false, inspect, or_
from sqlalchemy.engine.default import DefaultDialect
from sqlalchemy.orm import InstrumentedAttribute
from typing_extensions import TypeAlias

from advanced_alchemy.exceptions import ImproperConfigurationError, InvalidCursorError, MissingDependencyError
from advanced_alchemy.filters._base import (
    FilterFieldName,
    ModelT,
    StatementFilter,
    StatementTypeT,
    ordering_term,
)
from advanced_alchemy.filters._cursor import (
    CursorEnumName,
    decode_cursor,
    encode_cursor,
    normalize_cursor_ttl,
    order_fingerprint,
)
from advanced_alchemy.typing import CRYPTOGRAPHY_INSTALLED

if TYPE_CHECKING:
    from advanced_alchemy.service.pagination import CursorPagination

__all__ = (
    "CursorFilter",
    "CursorKey",
    "CursorKeys",
    "LimitOffsetFilter",
    "PaginationFilter",
    "normalize_cursor_keys",
)

_SortOrder: TypeAlias = Literal["asc", "desc"]
_NullsOrder: TypeAlias = Optional[Literal["first", "last"]]
_KeysetTerm: TypeAlias = Union[bool, "ColumnElement[bool]"]

_CURSOR_KEY_PAIR_LENGTH = 2
_INT64_LIMIT = 2**63
_STORAGE_DIALECT = DefaultDialect()


class PaginationFilter(StatementFilter, ABC):
    """Abstract base class for pagination filters.

    Subclasses should implement pagination logic, such as limit/offset or
    cursor-based pagination.
    """


@dataclass
class LimitOffsetFilter(PaginationFilter):
    """Limit and offset pagination filter.

    Implements traditional pagination using SQL LIMIT and OFFSET clauses.
    Only applies to SELECT statements; other statement types are returned unmodified.

    Note:
        This filter only modifies SELECT statements. For other statement types
        (UPDATE, DELETE), the statement is returned unchanged.

    See Also:
        - :meth:`sqlalchemy.sql.expression.Select.limit`: SQLAlchemy LIMIT clause
        - :meth:`sqlalchemy.sql.expression.Select.offset`: SQLAlchemy OFFSET clause
    """

    limit: int
    """Maximum number of rows to return."""
    offset: int
    """Number of rows to skip before returning results."""

    def append_to_statement(self, statement: StatementTypeT, model: type[ModelT]) -> StatementTypeT:
        """Apply LIMIT/OFFSET pagination to the statement.

        Args:
            statement: The SQLAlchemy statement to modify
            model: The SQLAlchemy model class

        Returns:
            StatementTypeT: Modified statement with limit and offset applied

        Note:
            Only modifies SELECT statements. Other statement types are returned as-is.

        See Also:
            :class:`sqlalchemy.sql.expression.Select`: SQLAlchemy SELECT statement
        """
        if isinstance(statement, Select):
            statement = cast("StatementTypeT", statement.limit(self.limit).offset(self.offset))
        return statement


@dataclass(frozen=True, eq=False)
class CursorKey:
    """One ordering key for :class:`CursorFilter`.

    Args:
        field_name: Mapped column attribute name or instrumented attribute.
        sort_order: Ascending or descending traversal.
        nulls: Where NULLs sort. Nullable columns left as ``None`` sort NULLs last.

    Raises:
        ValueError: The name, direction, or NULL placement is invalid.
    """

    field_name: FilterFieldName
    """Mapped column attribute name or instrumented attribute."""
    sort_order: _SortOrder = "asc"
    """Ascending or descending traversal."""
    nulls: _NullsOrder = None
    """Where NULLs sort. Nullable columns left as ``None`` sort NULLs last; non-nullable columns ignore it."""

    def __post_init__(self) -> None:
        if isinstance(self.field_name, str) and (not self.field_name or "." in self.field_name):
            msg = f"Cursor keys must name a column attribute of the model, got {self.field_name!r}"
            raise ValueError(msg)
        if self.sort_order not in {"asc", "desc"}:
            msg = "sort_order must be 'asc' or 'desc'"
            raise ValueError(msg)
        if self.nulls not in {None, "first", "last"}:
            msg = "nulls must be 'first', 'last', or None"
            raise ValueError(msg)

    @property
    def identity(self) -> "tuple[str, _SortOrder, _NullsOrder]":
        """Name, direction, and NULL placement; keys with the same identity order rows identically."""
        return (self.name, self.sort_order, self.nulls)

    @property
    def name(self) -> str:
        """Attribute name used in tokens and fingerprints."""
        if isinstance(self.field_name, str):
            return self.field_name
        key = getattr(self.field_name, "key", None)
        if not isinstance(key, str) or not key:
            msg = "Cursor key expressions must be named mapped column attributes"
            raise ValueError(msg)
        return key

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, CursorKey):
            return NotImplemented
        return self.identity == other.identity

    def __hash__(self) -> int:
        return hash(self.identity)


CursorKeys: TypeAlias = Union[
    str,
    "InstrumentedAttribute[Any]",
    CursorKey,
    Sequence[Union[str, "InstrumentedAttribute[Any]", CursorKey, "tuple[FilterFieldName, _SortOrder]"]],
]
"""Ordering keys accepted by :class:`CursorFilter`: a name, attribute, :class:`CursorKey`, or a sequence of them.

Sequence items may also be ``(name, "asc" | "desc")`` pairs. Bare names sort ascending.
"""


def normalize_cursor_keys(keys: CursorKeys) -> "tuple[CursorKey, ...]":
    """Normalize cursor ordering keys.

    Args:
        keys: A name, attribute, :class:`CursorKey`, or a sequence of names, attributes,
            ``(name, direction)`` pairs, and :class:`CursorKey` objects.

    Returns:
        Cursor keys in declared order.

    Raises:
        TypeError: A key has an unsupported type.
        ValueError: A key is invalid or declared twice.
    """
    items: Sequence[Any] = [keys] if isinstance(keys, (str, CursorKey, InstrumentedAttribute)) else keys
    normalized: list[CursorKey] = []
    for item in items:
        if isinstance(item, CursorKey):
            normalized.append(item)
        elif isinstance(item, tuple):
            pair = cast("tuple[Any, ...]", item)  # type: ignore[redundant-cast]
            if len(pair) != _CURSOR_KEY_PAIR_LENGTH:
                msg = f"Cursor key pairs must be a (name, direction) pair; got a tuple with {len(pair)} items"
                raise ValueError(msg)
            normalized.append(CursorKey(pair[0], pair[1]))
        elif isinstance(item, (str, InstrumentedAttribute)):
            normalized.append(CursorKey(cast("FilterFieldName", item)))
        else:
            msg = (
                "Each cursor key must be a name, an attribute, a (name, direction) pair, or a CursorKey."
                f" Unsupported value: {item!r}"
            )
            raise TypeError(msg)
    names = [key.name for key in normalized]
    if len(set(names)) != len(names):
        duplicates = ", ".join(dict.fromkeys(name for name in names if names.count(name) > 1))
        msg = f"Cursor keys must be unique; duplicate keys: {duplicates}"
        raise ValueError(msg)
    return tuple(normalized)


@dataclass(init=False, repr=False, eq=False)
class CursorFilter(PaginationFilter):
    """Keyset (cursor) pagination.

    Pages by comparing the ordering keys of the last row a client saw instead of skipping
    rows with ``OFFSET``, so deep pages cost the same as the first and concurrent inserts
    do not shift later pages. The model's primary key is appended as the final key, in the
    direction of the last declared key, so every row has a unique position.

    The filter owns ordering and limits: it replaces any ``ORDER BY``, ``LIMIT``, and
    ``OFFSET`` on the statement and fetches ``limit + 1`` rows to learn whether another
    page exists. Build the response with ``to_schema(..., pagination_type="cursor")`` or
    :meth:`build_page`, which drop the extra row.

    Args:
        keys: Ordering keys; see :data:`CursorKeys`. An empty sequence pages by primary key.
        limit: Page size.
        cursor: Token from a previous page, or ``None`` for the first page.
        secret: Key used to sign tokens, or to encrypt them when ``encrypted`` is set.
        ttl: Token lifetime in seconds or as a ``timedelta``.
        encrypted: Encrypt tokens so clients cannot read the key values.

    Raises:
        ValueError: The keys, limit, secret, or ttl are invalid.
        MissingDependencyError: ``encrypted=True`` was requested without ``cryptography`` installed.
        InvalidCursorError: ``cursor`` is malformed, tampered with, expired, or issued for a different ordering.
    """

    keys: "tuple[CursorKey, ...]"
    """Declared ordering keys, without the appended primary key."""
    limit: int
    """Page size."""
    cursor: Optional[str]
    """Token this page continues from."""
    ttl: Union[float, timedelta, None]
    """Lifetime of issued tokens."""
    encrypted: bool
    """Whether issued tokens are encrypted."""

    def __init__(
        self,
        keys: CursorKeys,
        limit: int,
        cursor: Optional[str] = None,
        secret: Union[str, bytes, None] = None,
        *,
        ttl: Union[float, timedelta, None] = None,
        encrypted: bool = False,
    ) -> None:
        self.keys = normalize_cursor_keys(keys)
        raw_limit: Any = limit
        if isinstance(raw_limit, bool) or not isinstance(raw_limit, int) or raw_limit < 1:
            msg = "limit must be a positive integer"
            raise ValueError(msg)
        self._secret: Optional[bytes] = secret.encode("utf-8") if isinstance(secret, str) else secret
        if self._secret == b"":
            msg = "a provided secret must not be empty"
            raise ValueError(msg)
        if encrypted and not self._secret:
            msg = "secret must not be empty when encrypted=True"
            raise ValueError(msg)
        if encrypted and not CRYPTOGRAPHY_INSTALLED:
            raise MissingDependencyError(package="cryptography")
        normalize_cursor_ttl(ttl)
        self.limit = limit
        self.cursor = cursor
        self.ttl = ttl
        self.encrypted = bool(encrypted)
        self._fingerprint = _cursor_fingerprint(tuple(key.identity for key in self.keys))
        self._values: Optional[tuple[Any, ...]] = None
        self._backward = False
        self._bound_model: Optional[Any] = None
        if cursor is not None:
            decoded = decode_cursor(
                cursor, self._fingerprint, secret=self._secret, ttl=self.ttl, encrypted=self.encrypted
            )
            self._values = decoded.values
            self._backward = decoded.backward

    @property
    def backward(self) -> bool:
        """Whether this page is fetched backward from ``cursor``."""
        return self._backward

    def append_to_statement(self, statement: StatementTypeT, model: type[ModelT]) -> StatementTypeT:
        """Apply keyset ordering, the keyset predicate, and the ``limit + 1`` fetch.

        Args:
            statement: The SQLAlchemy statement to modify.
            model: The SQLAlchemy model class.

        Returns:
            StatementTypeT: The paginated statement. Non-SELECT statements are returned unchanged.

        Raises:
            InvalidCursorError: The cursor values do not fit the model's ordering columns.
        """
        if not isinstance(statement, Select):
            return statement
        resolved = self._resolve(model)
        self._bound_model = model
        terms: list[ColumnElement[Any]] = []
        effective: list[tuple[_ResolvedKey, bool, _NullsOrder]] = []
        for key in resolved:
            ascending = (key.sort_order == "asc") != self._backward
            nulls = key.nulls
            if self._backward and nulls is not None:
                nulls = "last" if nulls == "first" else "first"
            terms.append(ordering_term(key.column, descending=not ascending, nulls=nulls))
            effective.append((key, ascending, nulls))
        select_stmt: Select[Any] = statement.order_by(None).order_by(*terms).limit(self.limit + 1).offset(None)
        if self._values is not None:
            predicate = self._keyset_predicate(effective, self._coerce_values(resolved))
            if predicate is False:
                select_stmt = select_stmt.where(false())
            elif predicate is not True:
                select_stmt = select_stmt.where(predicate)
        return cast("StatementTypeT", select_stmt)

    def paginate_items(self, items: "Sequence[Any]", model: Any) -> "list[Any]":
        """Apply this page's ordering, keyset bound, and ``limit + 1`` fetch to in-memory rows.

        Enum keys are ordered by the value their column stores: the member name for
        :class:`sqlalchemy.types.Enum`, or whatever a ``TypeDecorator`` binds. Databases
        with a native enum type order by declaration instead.

        Args:
            items: Model instances to paginate.
            model: Mapped model the items belong to.

        Returns:
            Up to ``limit + 1`` items in query order, ready for :meth:`build_page`.

        Raises:
            InvalidCursorError: The cursor values do not fit the model's ordering columns.
        """
        resolved = self._resolve(model)
        self._bound_model = model
        effective: list[tuple[str, bool, _NullsOrder]] = []
        for key in resolved:
            ascending = (key.sort_order == "asc") != self._backward
            nulls = key.nulls
            if self._backward and nulls is not None:
                nulls = "last" if nulls == "first" else "first"
            effective.append((key.attr_key, ascending, nulls if nulls is not None else "first"))
        processors: list[Optional[Callable[[Any], Any]]] = [
            key.column.type.bind_processor(_STORAGE_DIALECT) if key.enum_class is not None else None for key in resolved
        ]

        def compare(left: "Sequence[Any]", right: "Sequence[Any]") -> int:
            for (_, ascending, nulls), lv, rv in zip(effective, left, right):
                if lv is None or rv is None:
                    if lv is None and rv is None:
                        continue
                    return -1 if (lv is None) == (nulls == "first") else 1
                result = int(lv > rv) - int(lv < rv)
                if result:
                    return result if ascending else -result
            return 0

        def stored(values: "Sequence[Any]") -> "list[Any]":
            return [
                processor(value) if processor is not None and isinstance(value, Enum) else value
                for processor, value in zip(processors, values)
            ]

        def row_values(item: Any) -> "list[Any]":
            return stored([_row_value(item, attr_key) for attr_key, _, _ in effective])

        ordered = sorted(items, key=functools.cmp_to_key(lambda a, b: compare(row_values(a), row_values(b))))
        if self._values is not None:
            bound = stored(self._coerce_values(resolved))
            ordered = [item for item in ordered if compare(row_values(item), bound) > 0]
        return ordered[: self.limit + 1]

    def build_page(self, rows: "Sequence[Any]", *, model: Optional[Any] = None) -> "CursorPagination[Any]":
        """Drop the extra row, restore declared order, and mint adjacent-page tokens.

        Args:
            rows: Rows returned by the statement this filter was applied to.
            model: Mapped model the rows belong to. Defaults to the model the filter was last applied with.

        Returns:
            The page with ``next_cursor`` and ``previous_cursor`` set when such pages exist.

        Raises:
            ImproperConfigurationError: No model is known or a row lacks an ordering key.
        """
        from advanced_alchemy.service.pagination import CursorPagination

        bound = model if model is not None else self._bound_model
        if bound is None:
            if not rows:
                return CursorPagination(
                    items=[],
                    limit=self.limit,
                    next_cursor=None,
                    previous_cursor=None,
                    has_next=False,
                    has_previous=False,
                )
            bound = _row_model(rows[0])
        if bound is None:
            msg = "CursorFilter.build_page() needs the model; apply the filter to a statement or pass model="
            raise ImproperConfigurationError(msg)
        resolved = self._resolve(bound)
        has_more = len(rows) > self.limit
        items = list(rows[: self.limit])
        if self._backward:
            items.reverse()
        has_next = bool(items) and (self._backward or has_more)
        has_previous = bool(items) and (has_more if self._backward else self.cursor is not None)

        def token(row: Any, *, backward: bool) -> str:
            return encode_cursor(
                _token_values(row, resolved),
                self._fingerprint,
                backward=backward,
                secret=self._secret,
                ttl=self.ttl,
                encrypted=self.encrypted,
            )

        return CursorPagination(
            items=items,
            limit=self.limit,
            next_cursor=token(items[-1], backward=False) if has_next else None,
            previous_cursor=token(items[0], backward=True) if has_previous else None,
            has_next=has_next,
            has_previous=has_previous,
        )

    def _resolve(self, model: Any) -> "tuple[_ResolvedKey, ...]":
        return _resolve_cursor_keys(model, tuple(key.identity for key in self.keys))

    def _coerce_values(self, resolved: "tuple[_ResolvedKey, ...]") -> "tuple[Any, ...]":
        values: tuple[Any, ...] = self._values or ()
        if len(values) != len(resolved):
            msg = "Invalid pagination cursor: ordering mismatch"
            raise InvalidCursorError(msg)
        coerced: list[Any] = []
        for key, value in zip(resolved, values):
            if value is None:
                if not key.nullable:
                    msg = "Invalid pagination cursor: ordering mismatch"
                    raise InvalidCursorError(msg)
            elif isinstance(value, CursorEnumName):
                if key.enum_class is None or value not in key.enum_class.__members__:
                    msg = "Invalid pagination cursor: value does not match the ordering column"
                    raise InvalidCursorError(msg)
                value = key.enum_class[value]
            elif (
                key.integer
                and isinstance(value, int)
                and not isinstance(value, bool)
                and not -_INT64_LIMIT <= value < _INT64_LIMIT
            ):
                msg = "Invalid pagination cursor: value is out of range for the ordering column"
                raise InvalidCursorError(msg)
            elif not _value_matches_type(value, key.python_type):
                msg = "Invalid pagination cursor: value does not match the ordering column"
                raise InvalidCursorError(msg)
            coerced.append(value)
        return tuple(coerced)

    @staticmethod
    def _keyset_predicate(
        effective: "list[tuple[_ResolvedKey, bool, _NullsOrder]]", values: "tuple[Any, ...]"
    ) -> _KeysetTerm:
        """Build ``aoe(k1) AND (after(k1) OR (aoe(k2) AND (after(k2) OR ...)))`` for the effective order."""
        parts: list[tuple[_KeysetTerm, _KeysetTerm]] = []
        for (key, ascending, nulls), value in zip(effective, values):
            column = key.column
            after: _KeysetTerm
            at_or_after: _KeysetTerm
            if value is None:
                after = column.is_not(None) if nulls == "first" else False
                at_or_after = True if nulls == "first" else column.is_(None)
            elif isinstance(value, bool):
                is_first_value = value is (not ascending)
                after = column == (not value) if is_first_value else False
                at_or_after = (
                    (True if nulls == "last" or not key.nullable else column.is_not(None))
                    if is_first_value
                    else column == value
                )
                if nulls == "last":
                    after = _fold_or(after, column.is_(None))
                    at_or_after = _fold_or(at_or_after, column.is_(None))
            else:
                after = column > value if ascending else column < value
                at_or_after = column >= value if ascending else column <= value
                if nulls == "last":
                    after = _fold_or(after, column.is_(None))
                    at_or_after = _fold_or(at_or_after, column.is_(None))
            parts.append((after, at_or_after))
        predicate = parts[-1][0]
        for after, at_or_after in reversed(parts[:-1]):
            predicate = _fold_and(at_or_after, _fold_or(after, predicate))
        return predicate

    def __repr__(self) -> str:
        return f"CursorFilter(keys={self.keys!r}, limit={self.limit!r}, cursor={self.cursor!r})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, CursorFilter):
            return NotImplemented
        return (self.keys, self.limit, self.cursor, self._secret, self.ttl, self.encrypted) == (
            other.keys,
            other.limit,
            other.cursor,
            other._secret,
            other.ttl,
            other.encrypted,
        )

    def __hash__(self) -> int:
        return hash((self.keys, self.limit, self.cursor))

    def __reduce__(self) -> "tuple[Any, ...]":
        return (
            _rebuild_cursor_filter,
            (self.keys, self.limit, self.cursor, self._secret, self.ttl, self.encrypted),
        )


@dataclass(frozen=True)
class _ResolvedKey:
    column: Any
    attr_key: str
    sort_order: _SortOrder
    nulls: _NullsOrder
    nullable: bool
    enum_class: "Optional[type[Enum]]"
    python_type: Optional[type[Any]]
    integer: bool


@functools.lru_cache(maxsize=512)
def _cursor_fingerprint(identities: "tuple[tuple[str, _SortOrder, _NullsOrder], ...]") -> str:
    return order_fingerprint(identities)


@functools.lru_cache(maxsize=512)
def _resolve_cursor_keys(
    model: Any, identities: "tuple[tuple[str, _SortOrder, _NullsOrder], ...]"
) -> "tuple[_ResolvedKey, ...]":
    """Resolve declared keys plus the primary-key tiebreaker once per model and ordering."""
    mapper = inspect(model).mapper
    resolved: list[_ResolvedKey] = []
    for name, sort_order, nulls in identities:
        prop = mapper.column_attrs.get(name)
        if prop is None:
            msg = f"Cursor key {name!r} is not a column attribute of {mapper.class_.__name__}"
            raise ImproperConfigurationError(msg)
        resolved.append(_resolved_key(model, prop, sort_order, nulls))
    declared = {key.attr_key for key in resolved}
    tiebreak_order: _SortOrder = identities[-1][1] if identities else "asc"
    for pk_column in mapper.primary_key:
        prop = mapper.get_property_by_column(pk_column)
        if prop.key not in declared:
            resolved.append(_resolved_key(model, prop, tiebreak_order, None))
    return tuple(resolved)


def _resolved_key(model: Any, prop: Any, sort_order: _SortOrder, nulls: _NullsOrder) -> _ResolvedKey:
    column_obj = prop.columns[0]
    nullable = bool(getattr(column_obj, "nullable", True))
    column_type = getattr(column_obj, "type", None)
    python_type = _column_python_type(column_type)
    enum_class = getattr(column_type, "enum_class", None)
    if enum_class is None and python_type is not None and issubclass(python_type, Enum):
        enum_class = python_type
    return _ResolvedKey(
        column=getattr(model, prop.key),
        attr_key=prop.key,
        sort_order=sort_order,
        nulls=(nulls or "last") if nullable else None,
        nullable=nullable,
        enum_class=enum_class,
        python_type=python_type,
        integer=isinstance(getattr(column_type, "impl_instance", column_type), Integer),
    )


def _column_python_type(column_type: Any) -> Optional[type[Any]]:
    try:
        python_type = column_type.python_type
    except (AttributeError, NotImplementedError):
        return None
    return python_type if isinstance(python_type, type) else None


def _value_matches_type(value: Any, python_type: Optional[type[Any]]) -> bool:
    if python_type is None:
        return True
    if isinstance(value, bool):
        return python_type is bool
    if isinstance(value, python_type):
        return True
    numeric = (int, float, Decimal)
    return python_type in numeric and isinstance(value, numeric)


def _fold_and(left: _KeysetTerm, right: _KeysetTerm) -> _KeysetTerm:
    if left is False or right is False:
        return False
    if left is True:
        return right
    if right is True:
        return left
    return and_(left, right)


def _fold_or(left: _KeysetTerm, right: _KeysetTerm) -> _KeysetTerm:
    if left is True or right is True:
        return True
    if left is False:
        return right
    if right is False:
        return left
    return or_(left, right)


def _row_model(row: object) -> Optional[type[Any]]:
    return type(row) if inspect(type(row), raiseerr=False) is not None else None


def _token_values(row: object, resolved: "tuple[_ResolvedKey, ...]") -> "list[Any]":
    values = [_row_value(row, key.attr_key) for key in resolved]
    for key, value in zip(resolved, values):
        if isinstance(value, Enum) and key.enum_class is None:
            msg = (
                f"Cursor key {key.attr_key!r} holds Enum values but its column type does not name the Enum class; "
                "define python_type on the column type to return it"
            )
            raise ImproperConfigurationError(msg)
    return values


def _row_value(row: object, key: str) -> Any:
    source: object = row
    mapping: Optional[Mapping[str, Any]] = (
        cast("Mapping[str, Any]", row) if isinstance(row, Mapping) else getattr(row, "_mapping", None)
    )
    try:
        return mapping[key] if mapping is not None else getattr(source, key)
    except (KeyError, AttributeError) as exc:
        msg = f"Row has no cursor key {key!r}; select every ordering column"
        raise ImproperConfigurationError(msg) from exc


def _rebuild_cursor_filter(
    keys: "tuple[CursorKey, ...]",
    limit: int,
    cursor: Optional[str],
    secret: Optional[bytes],
    ttl: Union[float, timedelta, None],
    encrypted: bool,
) -> CursorFilter:
    return CursorFilter(keys, limit, cursor, secret, ttl=ttl, encrypted=encrypted)
