"""Concrete field filters for the FilterSet facade.

Each class is a Tier 2 declaration: it knows which lookups it supports,
how to coerce raw query-string values to typed Python values, and how to
compile a ``(path, lookup, value)`` triple into a Tier 1 leaf
:class:`StatementFilter`. Relationship-traversal wrapping happens
elsewhere (Phase 5 compilation).
"""

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
    Literal,
    cast,
)

from sqlalchemy import ColumnElement, Select, extract

from advanced_alchemy.filters._base import ModelT, StatementFilter, StatementTypeT
from advanced_alchemy.filters._columns import (
    VALID_OPERATORS,
    CollectionFilter,
    ComparisonFilter,
    NotInCollectionFilter,
    NotNullFilter,
    NullFilter,
    operators_map,
)
from advanced_alchemy.filters._filterset import UNSET, BaseFieldFilter
from advanced_alchemy.filters._search import SearchFilter

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import Optional, Union

    from sqlalchemy.orm import InstrumentedAttribute


__all__ = (
    "BooleanFilter",
    "DateFilter",
    "DatePartFilter",
    "DateTimeFilter",
    "EnumFilter",
    "NumberFilter",
    "OrderingApply",
    "OrderingFilter",
    "StringFilter",
    "UUIDFilter",
)


_TRUE_TOKENS: frozenset[str] = frozenset({"true", "1", "yes", "on", "t"})
_FALSE_TOKENS: frozenset[str] = frozenset({"false", "0", "no", "off", "f"})
_BETWEEN_PAIR_LENGTH = 2


def _parse_bool(raw: Any) -> bool:
    """Coerce a raw query-string value to ``bool``.

    Accepts the canonical truthy/falsy tokens used by HTML forms and
    common query-string conventions. Raises ``ValueError`` on anything
    else so callers can aggregate the error.
    """
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        token = raw.strip().lower()
        if token in _TRUE_TOKENS:
            return True
        if token in _FALSE_TOKENS:
            return False
    msg = f"Cannot interpret {raw!r} as a boolean."
    raise ValueError(msg)


def _split_csv(raw: "Union[str, Sequence[str]]") -> list[str]:
    """Normalize a raw query value to a list of trimmed string tokens.

    Accepts either a single comma-separated string (``a,b,c``) or a list
    of values from repeated keys (``?x=a&x=b``); returns the union with
    blank tokens dropped so trailing commas don't produce empty entries.
    """
    if isinstance(raw, str):
        items = [piece.strip() for piece in raw.split(",")]
    else:
        items = []
        for entry in raw:
            items.extend(piece.strip() for piece in entry.split(","))
    return [item for item in items if item]


def _null_leaf(field_name: str, want_null: bool) -> "StatementFilter":
    """Choose ``NullFilter`` or ``NotNullFilter`` from a coerced bool."""
    if want_null:
        return NullFilter(field_name)
    return NotNullFilter(field_name)


class StringFilter(BaseFieldFilter):
    """Field filter for text columns.

    Lookup catalog (per PRD §7.5):

    * ``exact`` / ``iexact`` — equality / case-insensitive equality.
    * ``contains`` / ``icontains`` — substring / case-insensitive
      substring (``%value%``).
    * ``startswith`` / ``istartswith`` — prefix match.
    * ``endswith`` / ``iendswith`` — suffix match.
    * ``in`` / ``not_in`` — set membership.
    * ``isnull`` — null check.

    ``iexact`` compiles to SQL ``ILIKE``; values containing ``%`` or
    ``_`` are interpreted as wildcards. Case-insensitive prefix/suffix
    operations rely on the same primitive.
    """

    supported_lookups: ClassVar[frozenset[str]] = frozenset(
        {
            "exact",
            "iexact",
            "contains",
            "icontains",
            "startswith",
            "istartswith",
            "endswith",
            "iendswith",
            "in",
            "not_in",
            "isnull",
        },
    )

    _COMPARISON_OPERATORS: ClassVar[dict[str, str]] = {
        "exact": "eq",
        "iexact": "ilike",
        "startswith": "startswith",
        "istartswith": "istartswith",
        "endswith": "endswith",
        "iendswith": "iendswith",
    }

    def coerce(self, raw: "Union[str, Sequence[str]]", lookup: str) -> Any:
        if lookup == "isnull":
            return _parse_bool(raw)
        if lookup in {"in", "not_in"}:
            tokens = _split_csv(raw)
            if not tokens:
                msg = f"Lookup '{lookup}' requires at least one value."
                raise ValueError(msg)
            return tokens
        if isinstance(raw, str):
            return raw
        msg = f"Lookup '{lookup}' expects a single string, got {type(raw).__name__}."
        raise ValueError(msg)

    def compile(
        self,
        path: tuple[str, ...],
        lookup: str,
        value: Any,
    ) -> "StatementFilter":
        field_name = path[-1]
        operator = self._COMPARISON_OPERATORS.get(lookup)
        if operator is not None:
            return ComparisonFilter(field_name=field_name, operator=operator, value=value)
        if lookup == "contains":
            return SearchFilter(field_name=field_name, value=value, ignore_case=False)
        if lookup == "icontains":
            return SearchFilter(field_name=field_name, value=value, ignore_case=True)
        if lookup == "in":
            return CollectionFilter(field_name=field_name, values=value)
        if lookup == "not_in":
            return NotInCollectionFilter(field_name=field_name, values=value)
        if lookup == "isnull":
            return _null_leaf(field_name, bool(value))
        msg = f"StringFilter has no compile rule for lookup {lookup!r}."
        raise ValueError(msg)


_NUMERIC_TYPES: tuple[type, ...] = (int, float, Decimal)


class NumberFilter(BaseFieldFilter):
    """Field filter for numeric columns (``int``, ``float``, ``Decimal``).

    The ``type_`` constructor argument selects which Python type raw
    values are coerced to. ``Decimal`` is preferred for monetary or
    precision-sensitive columns; ``int`` is the sensible default for
    foreign keys and counters; ``float`` for measurements.
    """

    supported_lookups: ClassVar[frozenset[str]] = frozenset(
        {"exact", "gt", "gte", "lt", "lte", "between", "in", "not_in", "isnull"},
    )

    _LOOKUP_TO_OPERATOR: ClassVar[dict[str, str]] = {
        "exact": "eq",
        "gt": "gt",
        "gte": "ge",
        "lt": "lt",
        "lte": "le",
        "between": "between",
    }

    def __init__(
        self,
        *,
        type_: type = int,
        lookups: "Optional[Sequence[str]]" = None,
        default: Any = UNSET,
    ) -> None:
        if type_ not in _NUMERIC_TYPES:
            msg = f"NumberFilter type_ must be one of int, float, Decimal — got {type_!r}."
            raise TypeError(msg)
        self.type_: type = type_
        super().__init__(lookups=lookups, default=default)

    def _coerce_one(self, raw: Any) -> Any:
        if not isinstance(raw, str):
            msg = f"NumberFilter expects str input, got {type(raw).__name__}."
            raise TypeError(msg)
        token = raw.strip()
        try:
            if self.type_ is Decimal:
                return Decimal(token)
            return self.type_(token)
        except (ValueError, InvalidOperation) as exc:
            msg = f"Cannot coerce {raw!r} to {self.type_.__name__}: {exc}"
            raise ValueError(msg) from exc

    def coerce(self, raw: "Union[str, Sequence[str]]", lookup: str) -> Any:
        if lookup == "isnull":
            return _parse_bool(raw)
        if lookup == "between":
            tokens = _split_csv(raw)
            if len(tokens) != _BETWEEN_PAIR_LENGTH:
                msg = f"between requires exactly two values, got {len(tokens)}."
                raise ValueError(msg)
            try:
                return (self._coerce_one(tokens[0]), self._coerce_one(tokens[1]))
            except TypeError as exc:
                raise ValueError(str(exc)) from exc
        if lookup in {"in", "not_in"}:
            tokens = _split_csv(raw)
            if not tokens:
                msg = f"Lookup '{lookup}' requires at least one value."
                raise ValueError(msg)
            try:
                return [self._coerce_one(token) for token in tokens]
            except TypeError as exc:
                raise ValueError(str(exc)) from exc
        if isinstance(raw, str):
            try:
                return self._coerce_one(raw)
            except TypeError as exc:
                raise ValueError(str(exc)) from exc
        msg = f"Lookup '{lookup}' expects a single value, got {type(raw).__name__}."
        raise ValueError(msg)

    def compile(
        self,
        path: tuple[str, ...],
        lookup: str,
        value: Any,
    ) -> "StatementFilter":
        field_name = path[-1]
        operator = self._LOOKUP_TO_OPERATOR.get(lookup)
        if operator is not None:
            return ComparisonFilter(field_name=field_name, operator=operator, value=value)
        if lookup == "in":
            return CollectionFilter(field_name=field_name, values=value)
        if lookup == "not_in":
            return NotInCollectionFilter(field_name=field_name, values=value)
        if lookup == "isnull":
            return _null_leaf(field_name, bool(value))
        msg = f"NumberFilter has no compile rule for lookup {lookup!r}."
        raise ValueError(msg)


class BooleanFilter(BaseFieldFilter):
    """Field filter for boolean columns.

    Accepts the standard truthy/falsy tokens (``true``/``false``,
    ``1``/``0``, ``yes``/``no``, ``on``/``off``) on coercion; matches
    with SQL equality on compilation.
    """

    supported_lookups: ClassVar[frozenset[str]] = frozenset({"exact", "isnull"})

    def coerce(self, raw: "Union[str, Sequence[str]]", lookup: str) -> Any:
        if isinstance(raw, list):
            if not raw:
                msg = f"Lookup '{lookup}' requires a value."
                raise ValueError(msg)
            raw = raw[0]
        return _parse_bool(raw)

    def compile(
        self,
        path: tuple[str, ...],
        lookup: str,
        value: Any,
    ) -> "StatementFilter":
        field_name = path[-1]
        if lookup == "exact":
            return ComparisonFilter(field_name=field_name, operator="eq", value=value)
        if lookup == "isnull":
            return _null_leaf(field_name, bool(value))
        msg = f"BooleanFilter has no compile rule for lookup {lookup!r}."
        raise ValueError(msg)


@dataclass
class DatePartFilter(StatementFilter):
    """Apply ``EXTRACT(part FROM column) <op> value`` as a WHERE clause.

    Backs the ``year``/``month``/``day``/``hour``/``minute``/``second``
    lookups on ``DateFilter`` and ``DateTimeFilter``. Stays a Tier 1
    primitive — relationship-traversal wrapping happens elsewhere.
    """

    field_name: "Union[str, ColumnElement[Any], InstrumentedAttribute[Any]]"
    """Field name, model attribute, or column expression."""
    part: str
    """Datetime component to extract (``year``, ``month``, ``day``, ``hour``, ``minute``, ``second``)."""
    operator: str
    """Comparison operator key from ``operators_map`` (``eq``, ``gt``, ``ge``, …)."""
    value: Any
    """Right-hand side passed to the comparison operator."""

    def append_to_statement(self, statement: StatementTypeT, model: type[ModelT]) -> StatementTypeT:
        field = self._get_instrumented_attr(model, self.field_name)
        op_func = operators_map.get(self.operator)
        if op_func is None:
            msg = f"Invalid operator '{self.operator}'. Must be one of: {sorted(VALID_OPERATORS)}"
            raise ValueError(msg)
        condition = op_func(extract(self.part, field), self.value)
        return cast("StatementTypeT", statement.where(condition))


_DATE_NUMERIC_LOOKUP_TO_OPERATOR: dict[str, str] = {
    "exact": "eq",
    "gt": "gt",
    "gte": "ge",
    "lt": "lt",
    "lte": "le",
    "between": "between",
}


class DateFilter(BaseFieldFilter):
    """Field filter for ISO-8601 ``date`` columns.

    Supports comparison lookups (exact/gt/gte/lt/lte/between), date-part
    lookups (year/month/day) backed by ``EXTRACT``, set membership
    (in/not_in), and null checks. Values are parsed via
    :meth:`datetime.date.fromisoformat`.
    """

    supported_lookups: ClassVar[frozenset[str]] = frozenset(
        {
            "exact",
            "gt",
            "gte",
            "lt",
            "lte",
            "between",
            "year",
            "month",
            "day",
            "in",
            "not_in",
            "isnull",
        },
    )

    _DATE_PART_LOOKUPS: ClassVar[frozenset[str]] = frozenset({"year", "month", "day"})

    def _coerce_date(self, raw: str) -> Any:
        token = raw.strip()
        try:
            return date.fromisoformat(token)
        except ValueError as exc:
            msg = f"Cannot parse {raw!r} as ISO-8601 date: {exc}"
            raise ValueError(msg) from exc

    @staticmethod
    def _coerce_int(raw: "Union[str, Sequence[str]]") -> int:
        if isinstance(raw, str):
            token = raw
        elif raw:
            token = raw[0]
        else:
            msg = "Date-part lookup requires a value."
            raise ValueError(msg)
        try:
            return int(token.strip())
        except ValueError as exc:
            msg = f"Cannot coerce {token!r} to int: {exc}"
            raise ValueError(msg) from exc

    def coerce(self, raw: "Union[str, Sequence[str]]", lookup: str) -> Any:
        if lookup == "isnull":
            return _parse_bool(raw)
        if lookup in self._DATE_PART_LOOKUPS:
            return self._coerce_int(raw)
        if lookup == "between":
            tokens = _split_csv(raw)
            if len(tokens) != _BETWEEN_PAIR_LENGTH:
                msg = f"between requires exactly two values, got {len(tokens)}."
                raise ValueError(msg)
            return (self._coerce_date(tokens[0]), self._coerce_date(tokens[1]))
        if lookup in {"in", "not_in"}:
            tokens = _split_csv(raw)
            if not tokens:
                msg = f"Lookup '{lookup}' requires at least one value."
                raise ValueError(msg)
            return [self._coerce_date(token) for token in tokens]
        if isinstance(raw, str):
            return self._coerce_date(raw)
        msg = f"Lookup '{lookup}' expects a single value."
        raise ValueError(msg)

    def compile(
        self,
        path: tuple[str, ...],
        lookup: str,
        value: Any,
    ) -> "StatementFilter":
        field_name = path[-1]
        if lookup in self._DATE_PART_LOOKUPS:
            return DatePartFilter(field_name=field_name, part=lookup, operator="eq", value=value)
        operator = _DATE_NUMERIC_LOOKUP_TO_OPERATOR.get(lookup)
        if operator is not None:
            return ComparisonFilter(field_name=field_name, operator=operator, value=value)
        if lookup == "in":
            return CollectionFilter(field_name=field_name, values=value)
        if lookup == "not_in":
            return NotInCollectionFilter(field_name=field_name, values=value)
        if lookup == "isnull":
            return _null_leaf(field_name, bool(value))
        msg = f"DateFilter has no compile rule for lookup {lookup!r}."
        raise ValueError(msg)


class DateTimeFilter(DateFilter):
    """Field filter for ISO-8601 ``datetime`` columns.

    Superset of :class:`DateFilter` adding ``hour``/``minute``/``second``
    extraction. Values are parsed via :meth:`datetime.datetime.fromisoformat`,
    which accepts both date-only and datetime tokens.
    """

    supported_lookups: ClassVar[frozenset[str]] = frozenset(
        {
            "exact",
            "gt",
            "gte",
            "lt",
            "lte",
            "between",
            "year",
            "month",
            "day",
            "hour",
            "minute",
            "second",
            "in",
            "not_in",
            "isnull",
        },
    )

    _DATE_PART_LOOKUPS: ClassVar[frozenset[str]] = frozenset(
        {"year", "month", "day", "hour", "minute", "second"},
    )

    def _coerce_date(self, raw: str) -> Any:
        token = raw.strip()
        try:
            return datetime.fromisoformat(token)
        except ValueError as exc:
            msg = f"Cannot parse {raw!r} as ISO-8601 datetime: {exc}"
            raise ValueError(msg) from exc


class UUIDFilter(BaseFieldFilter):
    """Field filter for UUID columns.

    Supports exact/in/not_in/isnull lookups; rejects malformed UUID
    strings via :class:`uuid.UUID`'s parser.
    """

    supported_lookups: ClassVar[frozenset[str]] = frozenset({"exact", "in", "not_in", "isnull"})

    @staticmethod
    def _coerce_uuid(raw: str) -> uuid.UUID:
        try:
            return uuid.UUID(raw.strip())
        except (ValueError, AttributeError, TypeError) as exc:
            msg = f"Cannot parse {raw!r} as UUID: {exc}"
            raise ValueError(msg) from exc

    def coerce(self, raw: "Union[str, Sequence[str]]", lookup: str) -> Any:
        if lookup == "isnull":
            return _parse_bool(raw)
        if lookup in {"in", "not_in"}:
            tokens = _split_csv(raw)
            if not tokens:
                msg = f"Lookup '{lookup}' requires at least one value."
                raise ValueError(msg)
            return [self._coerce_uuid(token) for token in tokens]
        if isinstance(raw, str):
            return self._coerce_uuid(raw)
        msg = f"Lookup '{lookup}' expects a single value."
        raise ValueError(msg)

    def compile(
        self,
        path: tuple[str, ...],
        lookup: str,
        value: Any,
    ) -> "StatementFilter":
        field_name = path[-1]
        if lookup == "exact":
            return ComparisonFilter(field_name=field_name, operator="eq", value=value)
        if lookup == "in":
            return CollectionFilter(field_name=field_name, values=value)
        if lookup == "not_in":
            return NotInCollectionFilter(field_name=field_name, values=value)
        if lookup == "isnull":
            return _null_leaf(field_name, bool(value))
        msg = f"UUIDFilter has no compile rule for lookup {lookup!r}."
        raise ValueError(msg)


class EnumFilter(BaseFieldFilter):
    """Field filter for columns backed by a Python ``enum.Enum``.

    Coercion accepts either the enum member's value (``"red"``) or its
    name (``"RED"``); rejects unknown tokens with ``ValueError``.
    """

    supported_lookups: ClassVar[frozenset[str]] = frozenset({"exact", "in", "not_in", "isnull"})

    def __init__(
        self,
        *,
        enum: Any,
        lookups: "Optional[Sequence[str]]" = None,
        default: Any = UNSET,
    ) -> None:
        if not isinstance(enum, type) or not issubclass(enum, Enum):
            msg = f"EnumFilter requires an Enum subclass, got {enum!r}."
            raise TypeError(msg)
        self.enum: type[Enum] = enum
        super().__init__(lookups=lookups, default=default)

    def _coerce_member(self, raw: str) -> Enum:
        token = raw.strip()
        try:
            return self.enum(token)
        except ValueError:
            pass
        try:
            return self.enum[token]
        except KeyError as exc:
            members = sorted(member.name for member in self.enum)
            msg = f"{token!r} is not a valid {self.enum.__name__} member (by value or name). Known members: {members}."
            raise ValueError(msg) from exc

    def coerce(self, raw: "Union[str, Sequence[str]]", lookup: str) -> Any:
        if lookup == "isnull":
            return _parse_bool(raw)
        if lookup in {"in", "not_in"}:
            tokens = _split_csv(raw)
            if not tokens:
                msg = f"Lookup '{lookup}' requires at least one value."
                raise ValueError(msg)
            return [self._coerce_member(token) for token in tokens]
        if isinstance(raw, str):
            return self._coerce_member(raw)
        msg = f"Lookup '{lookup}' expects a single value."
        raise ValueError(msg)

    def compile(
        self,
        path: tuple[str, ...],
        lookup: str,
        value: Any,
    ) -> "StatementFilter":
        field_name = path[-1]
        if lookup == "exact":
            return ComparisonFilter(field_name=field_name, operator="eq", value=value)
        if lookup == "in":
            return CollectionFilter(field_name=field_name, values=value)
        if lookup == "not_in":
            return NotInCollectionFilter(field_name=field_name, values=value)
        if lookup == "isnull":
            return _null_leaf(field_name, bool(value))
        msg = f"EnumFilter has no compile rule for lookup {lookup!r}."
        raise ValueError(msg)


@dataclass
class OrderingApply(StatementFilter):
    """Apply a chain of ``ORDER BY`` clauses to a SELECT statement.

    The ``orderings`` list is preserved in order; SQLAlchemy collapses
    repeated ``.order_by()`` calls into one ``ORDER BY`` clause with the
    columns in declaration order, which is what callers want.
    """

    orderings: list[tuple[str, Literal["asc", "desc"]]] = field(default_factory=list)
    """Sequence of ``(field_name, direction)`` pairs to apply."""

    def append_to_statement(self, statement: StatementTypeT, model: type[ModelT]) -> StatementTypeT:
        if not isinstance(statement, Select) or not self.orderings:
            return statement
        select_stmt: Select[Any] = statement
        for field_name, direction in self.orderings:
            column = self._get_instrumented_attr(model, field_name)
            select_stmt = select_stmt.order_by(
                column.desc() if direction == "desc" else column.asc(),
            )
        return cast("StatementTypeT", select_stmt)


class OrderingFilter(BaseFieldFilter):
    """Field filter for declarative ``ORDER BY`` declarations.

    Special-case Tier 2 filter — does not participate in the standard
    lookup catalog. Coerces a comma-separated value (with ``-`` prefix
    for descending) into a list of ``(field, direction)`` pairs and
    compiles them into a single :class:`OrderingApply` instance.
    """

    supported_lookups: ClassVar[frozenset[str]] = frozenset({"exact"})
    default_lookup: ClassVar[str] = "exact"
    binds_to_column: ClassVar[bool] = False

    def __init__(
        self,
        *,
        allowed: "Sequence[str]",
        default: Any = UNSET,
    ) -> None:
        if not allowed:
            msg = "OrderingFilter requires a non-empty 'allowed' list."
            raise ValueError(msg)
        self.allowed: tuple[str, ...] = tuple(allowed)
        self._allowed_set: frozenset[str] = frozenset(self.allowed)
        super().__init__(lookups=None, default=default)

    def coerce(
        self,
        raw: "Union[str, Sequence[str]]",
        lookup: str,
    ) -> list[tuple[str, Literal["asc", "desc"]]]:
        tokens = _split_csv(raw)
        if not tokens:
            msg = "OrderingFilter requires at least one field."
            raise ValueError(msg)
        result: list[tuple[str, Literal["asc", "desc"]]] = []
        for token in tokens:
            if token.startswith("-"):
                name = token[1:].strip()
                direction: Literal["asc", "desc"] = "desc"
            else:
                name = token.strip()
                direction = "asc"
            if not name:
                msg = "OrderingFilter received an empty field name."
                raise ValueError(msg)
            if name not in self._allowed_set:
                msg = f"{name!r} is not in OrderingFilter.allowed: {sorted(self.allowed)}."
                raise ValueError(msg)
            result.append((name, direction))
        return result

    def compile(
        self,
        path: tuple[str, ...],
        lookup: str,
        value: Any,
    ) -> "StatementFilter":
        return OrderingApply(orderings=list(value))
