"""Tests for FilterSet parsing — Phase 4.

Covers:

* ``from_query_params`` — coerces ``Mapping[str, str | list[str]]`` into a
  populated ``FilterSet`` instance.
* ``from_dict`` — accepts native Python typed values; falls through to
  ``coerce()`` when the value is a string or sequence of strings.
* ``Meta.strict`` — when ``True``, unknown query keys raise
  :class:`FilterValidationError`; when ``False`` (default) they are
  ignored.
* Per-field error aggregation — a single ``FilterValidationError``
  carries ``field → message`` so callers can fix every problem in one
  pass.
"""

import enum
from datetime import date, datetime
from decimal import Decimal
from typing import ClassVar
from uuid import uuid4

import pytest
from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from advanced_alchemy.exceptions import FilterValidationError
from advanced_alchemy.filters import (
    BooleanFilter,
    DateFilter,
    DateTimeFilter,
    EnumFilter,
    FilterSet,
    NumberFilter,
    OrderingFilter,
    StringFilter,
    UUIDFilter,
)


class _Base(DeclarativeBase):
    pass


class _Author(_Base):
    __tablename__ = "_fsp_author"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50))
    country: Mapped[str] = mapped_column(String(2))


class _Post(_Base):
    __tablename__ = "_fsp_post"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(120))
    score: Mapped[int] = mapped_column(Integer)
    is_published: Mapped[bool] = mapped_column()
    created_at: Mapped[datetime] = mapped_column()
    author_id: Mapped[int] = mapped_column(ForeignKey("_fsp_author.id"))
    author: Mapped[_Author] = relationship("_Author")


class PostFilter(FilterSet):
    title = StringFilter(lookups=["exact", "icontains", "in"])
    score = NumberFilter(lookups=["exact", "gt", "lt", "between", "in"])
    is_published = BooleanFilter()
    created_at = DateTimeFilter(lookups=["gte", "lte", "year"])
    author__name = StringFilter(lookups=["iexact", "in"])
    order_by = OrderingFilter(allowed=["title", "score", "created_at"])

    class Meta:
        model = _Post
        allowed_relationships: ClassVar = ["author"]


class StrictPostFilter(PostFilter):
    class Meta:
        model = _Post
        allowed_relationships: ClassVar = ["author"]
        strict: ClassVar = True


class TestKeyResolution:
    def test_default_lookup_applied_for_bare_field(self) -> None:
        fs = PostFilter.from_query_params({"title": "hello"})
        assert fs.invocations == [("title", "exact", "hello")]

    def test_explicit_lookup_parsed(self) -> None:
        fs = PostFilter.from_query_params({"title__icontains": "py"})
        assert fs.invocations == [("title", "icontains", "py")]

    def test_relationship_path_with_default_lookup(self) -> None:
        fs = PostFilter.from_query_params({"author__name": "Jane"})
        assert fs.invocations == [("author__name", "iexact", "Jane")]

    def test_relationship_path_with_explicit_lookup(self) -> None:
        fs = PostFilter.from_query_params({"author__name__iexact": "Jane"})
        assert fs.invocations == [("author__name", "iexact", "Jane")]

    def test_in_lookup_with_csv(self) -> None:
        fs = PostFilter.from_query_params({"title__in": "a,b,c"})
        assert fs.invocations == [("title", "in", ["a", "b", "c"])]

    def test_in_lookup_with_repeated_keys_as_list(self) -> None:
        fs = PostFilter.from_query_params({"title__in": ["a", "b"]})
        assert fs.invocations == [("title", "in", ["a", "b"])]

    def test_between_lookup_two_values(self) -> None:
        fs = PostFilter.from_query_params({"score__between": "10,20"})
        assert fs.invocations == [("score", "between", (10, 20))]


class TestMultipleFields:
    def test_multiple_fields_each_invoked(self) -> None:
        fs = PostFilter.from_query_params(
            {
                "title__icontains": "python",
                "score__gt": "5",
                "is_published": "true",
            },
        )
        invocations = {name: (lookup, value) for name, lookup, value in fs.invocations}
        assert invocations["title"] == ("icontains", "python")
        assert invocations["score"] == ("gt", 5)
        assert invocations["is_published"] == ("exact", True)

    def test_ordering_filter_invocation(self) -> None:
        fs = PostFilter.from_query_params({"order_by": "-created_at,title"})
        assert fs.invocations == [
            ("order_by", "exact", [("created_at", "desc"), ("title", "asc")]),
        ]


class TestCoercionErrors:
    def test_invalid_int_aggregates_error(self) -> None:
        with pytest.raises(FilterValidationError) as ei:
            PostFilter.from_query_params({"score__gt": "abc"})
        assert "score" in ei.value.errors

    def test_multiple_errors_aggregated(self) -> None:
        with pytest.raises(FilterValidationError) as ei:
            PostFilter.from_query_params(
                {
                    "score__gt": "abc",
                    "is_published": "maybe",
                },
            )
        assert {"score", "is_published"} <= set(ei.value.errors)

    def test_between_wrong_arity_reported(self) -> None:
        with pytest.raises(FilterValidationError) as ei:
            PostFilter.from_query_params({"score__between": "10"})
        assert "score" in ei.value.errors
        assert "two" in ei.value.errors["score"].lower()


class TestStrictMode:
    def test_default_ignores_unknown_keys(self) -> None:
        fs = PostFilter.from_query_params(
            {
                "title": "x",
                "ghost": "y",
            },
        )
        assert fs.invocations == [("title", "exact", "x")]

    def test_strict_rejects_unknown_keys(self) -> None:
        with pytest.raises(FilterValidationError) as ei:
            StrictPostFilter.from_query_params(
                {
                    "title": "x",
                    "ghost": "y",
                },
            )
        assert "ghost" in ei.value.errors

    def test_strict_aggregates_multiple_unknown(self) -> None:
        with pytest.raises(FilterValidationError) as ei:
            StrictPostFilter.from_query_params(
                {
                    "ghost": "y",
                    "phantom": "z",
                },
            )
        assert {"ghost", "phantom"} <= set(ei.value.errors)


class TestFromDict:
    def test_native_types_pass_through(self) -> None:
        fs = PostFilter.from_dict(
            {
                "score__gt": 10,
                "is_published": True,
            },
        )
        invocations = {name: (lookup, value) for name, lookup, value in fs.invocations}
        assert invocations["score"] == ("gt", 10)
        assert invocations["is_published"] == ("exact", True)

    def test_string_values_still_coerce(self) -> None:
        fs = PostFilter.from_dict({"score__gt": "10"})
        assert fs.invocations == [("score", "gt", 10)]

    def test_native_list_passes_through(self) -> None:
        fs = PostFilter.from_dict({"score__in": [1, 2, 3]})
        assert fs.invocations == [("score", "in", [1, 2, 3])]

    def test_native_string_list_coerces(self) -> None:
        fs = PostFilter.from_dict({"score__in": ["1", "2", "3"]})
        assert fs.invocations == [("score", "in", [1, 2, 3])]

    def test_native_date_passes_through(self) -> None:
        d = date(2024, 3, 14)
        fs = PostFilter.from_dict({"created_at__gte": d})
        assert fs.invocations == [("created_at", "gte", d)]


class TestFilterValidationErrorShape:
    def test_to_dict_returns_http_friendly(self) -> None:
        exc = FilterValidationError({"score": "bad", "name": "also bad"})
        payload = exc.to_dict()
        assert payload == {
            "type": "filter_validation",
            "errors": {"score": "bad", "name": "also bad"},
        }

    def test_errors_dict_is_isolated(self) -> None:
        original = {"name": "bad"}
        exc = FilterValidationError(original)
        original["name"] = "changed"
        assert exc.errors == {"name": "bad"}


class _NullableTitleFilter(FilterSet):
    title = StringFilter(lookups=["exact", "isnull"])

    class Meta:
        model = _Post


class TestNullLookup:
    def test_isnull_true_value(self) -> None:
        fs = _NullableTitleFilter.from_query_params({"title__isnull": "true"})
        assert fs.invocations == [("title", "isnull", True)]

    def test_isnull_false_value(self) -> None:
        fs = _NullableTitleFilter.from_query_params({"title__isnull": "0"})
        assert fs.invocations == [("title", "isnull", False)]


class _UItemBase(DeclarativeBase):
    pass


class _UItem(_UItemBase):
    __tablename__ = "_fsp_item"
    id: Mapped[str] = mapped_column(primary_key=True)
    ref: Mapped[str] = mapped_column(String(36))
    created: Mapped[date] = mapped_column()


class _ItemFilter(FilterSet):
    ref = UUIDFilter(lookups=["exact", "in"])
    created = DateFilter(lookups=["exact", "year", "between"])

    class Meta:
        model = _UItem


class TestUUIDAndDateParsing:
    def test_uuid_parsing(self) -> None:
        u = uuid4()
        fs = _ItemFilter.from_query_params({"ref": str(u)})
        assert fs.invocations[0][2] == u

    def test_date_year_extracts_int(self) -> None:
        fs = _ItemFilter.from_query_params({"created__year": "2024"})
        assert fs.invocations == [("created", "year", 2024)]


class TestEmptyParams:
    def test_no_keys_yields_empty_invocations(self) -> None:
        fs = PostFilter.from_query_params({})
        assert fs.invocations == []

    def test_strict_with_empty_params_is_ok(self) -> None:
        fs = StrictPostFilter.from_query_params({})
        assert fs.invocations == []


class TestRepeatedKeys:
    def test_in_lookup_handles_list_of_csv(self) -> None:
        fs = PostFilter.from_query_params({"score__in": ["1,2", "3"]})
        assert fs.invocations == [("score", "in", [1, 2, 3])]


class _MoneyBase(DeclarativeBase):
    pass


class _Money(_MoneyBase):
    __tablename__ = "_fsp_money"
    id: Mapped[int] = mapped_column(primary_key=True)
    amount: Mapped[Decimal] = mapped_column()


class _MoneyFilter(FilterSet):
    amount = NumberFilter(type_=Decimal, lookups=["exact", "gt"])

    class Meta:
        model = _Money


class TestNumericTypes:
    def test_decimal_coerced(self) -> None:
        fs = _MoneyFilter.from_query_params({"amount__gt": "10.50"})
        assert fs.invocations == [("amount", "gt", Decimal("10.50"))]


class _Status(enum.Enum):
    OPEN = "open"
    CLOSED = "closed"


class _StatusBase(DeclarativeBase):
    pass


class _Ticket(_StatusBase):
    __tablename__ = "_fsp_ticket"
    id: Mapped[int] = mapped_column(primary_key=True)
    status: Mapped[str] = mapped_column(String(10))
    ref: Mapped[str] = mapped_column(String(36))
    when: Mapped[date] = mapped_column()


class _TicketFilter(FilterSet):
    status = EnumFilter(enum=_Status, lookups=["exact", "in"])
    ref = UUIDFilter(lookups=["exact"])
    when = DateFilter(lookups=["exact", "year"])

    class Meta:
        model = _Ticket


class TestEdgeCases:
    def test_malformed_uuid_aggregates_under_field_name(self) -> None:
        with pytest.raises(FilterValidationError) as ei:
            _TicketFilter.from_query_params({"ref": "not-a-uuid"})
        assert "ref" in ei.value.errors
        assert "uuid" in ei.value.errors["ref"].lower()

    def test_malformed_date_aggregates(self) -> None:
        with pytest.raises(FilterValidationError) as ei:
            _TicketFilter.from_query_params({"when": "march"})
        assert "when" in ei.value.errors

    def test_malformed_year_aggregates(self) -> None:
        with pytest.raises(FilterValidationError) as ei:
            _TicketFilter.from_query_params({"when__year": "abc"})
        assert "when" in ei.value.errors

    def test_enum_by_value(self) -> None:
        fs = _TicketFilter.from_query_params({"status": "open"})
        assert fs.invocations == [("status", "exact", _Status.OPEN)]

    def test_enum_by_name(self) -> None:
        fs = _TicketFilter.from_query_params({"status": "OPEN"})
        assert fs.invocations == [("status", "exact", _Status.OPEN)]

    def test_enum_unknown_aggregates(self) -> None:
        with pytest.raises(FilterValidationError) as ei:
            _TicketFilter.from_query_params({"status": "purple"})
        assert "status" in ei.value.errors

    def test_enum_in_csv(self) -> None:
        fs = _TicketFilter.from_query_params({"status__in": "open,closed"})
        assert fs.invocations == [("status", "in", [_Status.OPEN, _Status.CLOSED])]

    def test_uppercase_lookup_falls_through_to_default(self) -> None:
        """Lookups are case-sensitive — ``ICONTAINS`` is not the same as ``icontains``.

        The trailing token doesn't match a known lookup, so the entire
        key is treated as a candidate field name. Since no such field
        exists, the key is silently ignored under the default
        non-strict mode.
        """
        fs = PostFilter.from_query_params({"title__ICONTAINS": "py"})
        assert fs.invocations == []

    def test_unsupported_lookup_treated_as_unknown_key(self) -> None:
        """A field declared with a subset of lookups won't match the rest.

        ``title`` here only enables ``exact`` / ``icontains`` / ``in``;
        ``startswith`` is unsupported, so the trailing token cannot
        attach to the field. The key is silently ignored.
        """
        fs = PostFilter.from_query_params({"title__startswith": "py"})
        assert fs.invocations == []

    def test_unsupported_lookup_strict_mode_reports(self) -> None:
        with pytest.raises(FilterValidationError) as ei:
            StrictPostFilter.from_query_params({"title__startswith": "py"})
        assert "title__startswith" in ei.value.errors

    def test_empty_value_for_in_lookup_aggregates(self) -> None:
        with pytest.raises(FilterValidationError) as ei:
            PostFilter.from_query_params({"title__in": ""})
        assert "title" in ei.value.errors

    def test_to_filters_index_consistency_under_subclassing(self) -> None:
        """Subclasses inherit parent invocations parsing too."""
        fs = StrictPostFilter.from_query_params({"title": "x"})
        assert fs.invocations == [("title", "exact", "x")]
