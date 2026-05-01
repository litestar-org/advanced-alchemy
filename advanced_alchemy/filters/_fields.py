"""Concrete field filters for the FilterSet facade.

Each class is a Tier 2 declaration: it knows which lookups it supports,
how to coerce raw query-string values to typed Python values, and how to
compile a ``(path, lookup, value)`` triple into a Tier 1 leaf
:class:`StatementFilter`. Relationship-traversal wrapping happens
elsewhere (Phase 5 compilation).
"""

from decimal import Decimal, InvalidOperation
from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
)

from advanced_alchemy.filters._columns import (
    CollectionFilter,
    ComparisonFilter,
    NotInCollectionFilter,
    NotNullFilter,
    NullFilter,
)
from advanced_alchemy.filters._filterset import UNSET, BaseFieldFilter
from advanced_alchemy.filters._search import SearchFilter

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import Optional, Union

    from advanced_alchemy.filters._base import StatementFilter


__all__ = (
    "BooleanFilter",
    "NumberFilter",
    "StringFilter",
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
