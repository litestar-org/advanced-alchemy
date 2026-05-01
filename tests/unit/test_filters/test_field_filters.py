"""Tests for the concrete typed field filters.

Covers Phase 3.2-3.4 of the FilterSet roadmap. Each filter is exercised at
two levels:

* ``coerce()`` — raw query-string value → typed Python value (with the
  lookup-aware coercions for ``in``/``between``/``isnull``).
* ``compile()`` — ``(path, lookup, value)`` triple → Tier 1
  :class:`StatementFilter` instance with the right field and arguments.
"""

from decimal import Decimal
from typing import Any

import pytest

from advanced_alchemy.filters import (
    CollectionFilter,
    ComparisonFilter,
    NotInCollectionFilter,
    NotNullFilter,
    NullFilter,
    SearchFilter,
)
from advanced_alchemy.filters._fields import BooleanFilter, NumberFilter, StringFilter


class TestStringFilter:
    def test_supported_lookups_match_spec(self) -> None:
        assert StringFilter.supported_lookups == frozenset(
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

    def test_default_lookup_is_exact(self) -> None:
        assert StringFilter.default_lookup == "exact"

    @pytest.mark.parametrize("lookup", ["exact", "iexact", "contains", "icontains"])
    def test_coerce_passes_strings_through(self, lookup: str) -> None:
        assert StringFilter().coerce("hello", lookup) == "hello"

    def test_coerce_in_splits_comma_separated(self) -> None:
        assert StringFilter().coerce("python,sqlalchemy", "in") == ["python", "sqlalchemy"]

    def test_coerce_in_accepts_repeated_keys_as_list(self) -> None:
        assert StringFilter().coerce(["python", "sqlalchemy"], "in") == ["python", "sqlalchemy"]

    def test_coerce_in_strips_whitespace(self) -> None:
        assert StringFilter().coerce(" python , sqlalchemy ", "in") == ["python", "sqlalchemy"]

    def test_coerce_in_drops_empty_tokens(self) -> None:
        assert StringFilter().coerce("python,,sqlalchemy", "in") == ["python", "sqlalchemy"]

    def test_coerce_isnull_true_tokens(self) -> None:
        flt = StringFilter()
        for token in ("true", "1", "True", "TRUE", "yes", "on"):
            assert flt.coerce(token, "isnull") is True

    def test_coerce_isnull_false_tokens(self) -> None:
        flt = StringFilter()
        for token in ("false", "0", "False", "no", "off"):
            assert flt.coerce(token, "isnull") is False

    def test_coerce_isnull_invalid_raises(self) -> None:
        with pytest.raises(ValueError):
            StringFilter().coerce("maybe", "isnull")

    def test_compile_exact_uses_comparison_eq(self) -> None:
        result = StringFilter().compile(("title",), "exact", "python")
        assert isinstance(result, ComparisonFilter)
        assert result.field_name == "title"
        assert result.operator == "eq"
        assert result.value == "python"

    def test_compile_iexact_uses_comparison_ilike(self) -> None:
        result = StringFilter().compile(("title",), "iexact", "Python")
        assert isinstance(result, ComparisonFilter)
        assert result.operator == "ilike"
        assert result.value == "Python"

    def test_compile_contains_uses_search_filter(self) -> None:
        result = StringFilter().compile(("title",), "contains", "py")
        assert isinstance(result, SearchFilter)
        assert result.field_name == "title"
        assert result.value == "py"
        assert result.ignore_case is False

    def test_compile_icontains_uses_search_filter_ignore_case(self) -> None:
        result = StringFilter().compile(("title",), "icontains", "py")
        assert isinstance(result, SearchFilter)
        assert result.ignore_case is True

    def test_compile_startswith(self) -> None:
        result = StringFilter().compile(("title",), "startswith", "py")
        assert isinstance(result, ComparisonFilter)
        assert result.operator == "startswith"

    def test_compile_istartswith(self) -> None:
        result = StringFilter().compile(("title",), "istartswith", "py")
        assert isinstance(result, ComparisonFilter)
        assert result.operator == "istartswith"

    def test_compile_endswith(self) -> None:
        result = StringFilter().compile(("title",), "endswith", "py")
        assert isinstance(result, ComparisonFilter)
        assert result.operator == "endswith"

    def test_compile_iendswith(self) -> None:
        result = StringFilter().compile(("title",), "iendswith", "py")
        assert isinstance(result, ComparisonFilter)
        assert result.operator == "iendswith"

    def test_compile_in_uses_collection_filter(self) -> None:
        result = StringFilter().compile(("title",), "in", ["a", "b"])
        assert isinstance(result, CollectionFilter)
        assert result.field_name == "title"
        assert result.values == ["a", "b"]

    def test_compile_not_in_uses_not_in_collection(self) -> None:
        result = StringFilter().compile(("title",), "not_in", ["a", "b"])
        assert isinstance(result, NotInCollectionFilter)

    def test_compile_isnull_true_returns_null_filter(self) -> None:
        result = StringFilter().compile(("title",), "isnull", True)
        assert isinstance(result, NullFilter)
        assert result.field_name == "title"

    def test_compile_isnull_false_returns_not_null_filter(self) -> None:
        result = StringFilter().compile(("title",), "isnull", False)
        assert isinstance(result, NotNullFilter)
        assert result.field_name == "title"

    def test_compile_uses_terminal_path_segment(self) -> None:
        result = StringFilter().compile(("author", "name"), "exact", "Jane")
        assert isinstance(result, ComparisonFilter)
        assert result.field_name == "name"


class TestNumberFilter:
    def test_supported_lookups_match_spec(self) -> None:
        assert NumberFilter.supported_lookups == frozenset(
            {"exact", "gt", "gte", "lt", "lte", "between", "in", "not_in", "isnull"},
        )

    def test_default_type_is_int(self) -> None:
        assert NumberFilter().type_ is int

    def test_coerce_int(self) -> None:
        assert NumberFilter().coerce("42", "exact") == 42

    def test_coerce_float(self) -> None:
        assert NumberFilter(type_=float).coerce("3.14", "exact") == 3.14

    def test_coerce_decimal(self) -> None:
        assert NumberFilter(type_=Decimal).coerce("3.14", "exact") == Decimal("3.14")

    def test_coerce_invalid_raises(self) -> None:
        with pytest.raises(ValueError):
            NumberFilter().coerce("abc", "exact")

    def test_coerce_unsupported_type_rejected(self) -> None:
        with pytest.raises(TypeError):
            NumberFilter(type_=str)  # type: ignore[arg-type]

    def test_coerce_in_returns_list_of_int(self) -> None:
        assert NumberFilter().coerce("1,2,3", "in") == [1, 2, 3]

    def test_coerce_in_with_repeated_keys(self) -> None:
        assert NumberFilter().coerce(["1", "2", "3"], "in") == [1, 2, 3]

    def test_coerce_between_returns_two_tuple(self) -> None:
        assert NumberFilter().coerce("10,20", "between") == (10, 20)

    def test_coerce_between_with_repeated_keys(self) -> None:
        assert NumberFilter().coerce(["10", "20"], "between") == (10, 20)

    def test_coerce_between_requires_exactly_two(self) -> None:
        with pytest.raises(ValueError):
            NumberFilter().coerce("10", "between")
        with pytest.raises(ValueError):
            NumberFilter().coerce("10,20,30", "between")

    def test_coerce_isnull_returns_bool(self) -> None:
        assert NumberFilter().coerce("true", "isnull") is True
        assert NumberFilter().coerce("0", "isnull") is False

    def test_compile_exact_uses_eq(self) -> None:
        result = NumberFilter().compile(("age",), "exact", 30)
        assert isinstance(result, ComparisonFilter)
        assert result.operator == "eq"
        assert result.value == 30

    @pytest.mark.parametrize(
        ("lookup", "operator"),
        [("gt", "gt"), ("gte", "ge"), ("lt", "lt"), ("lte", "le")],
    )
    def test_compile_comparisons(self, lookup: str, operator: str) -> None:
        result = NumberFilter().compile(("age",), lookup, 30)
        assert isinstance(result, ComparisonFilter)
        assert result.operator == operator

    def test_compile_between(self) -> None:
        result = NumberFilter().compile(("age",), "between", (18, 65))
        assert isinstance(result, ComparisonFilter)
        assert result.operator == "between"
        assert result.value == (18, 65)

    def test_compile_in(self) -> None:
        result = NumberFilter().compile(("age",), "in", [10, 20, 30])
        assert isinstance(result, CollectionFilter)
        assert result.values == [10, 20, 30]

    def test_compile_isnull_true(self) -> None:
        assert isinstance(NumberFilter().compile(("age",), "isnull", True), NullFilter)

    def test_compile_isnull_false(self) -> None:
        assert isinstance(NumberFilter().compile(("age",), "isnull", False), NotNullFilter)


class TestBooleanFilter:
    def test_supported_lookups_match_spec(self) -> None:
        assert BooleanFilter.supported_lookups == frozenset({"exact", "isnull"})

    @pytest.mark.parametrize("token", ["true", "1", "yes", "on", "True"])
    def test_coerce_truthy(self, token: str) -> None:
        assert BooleanFilter().coerce(token, "exact") is True

    @pytest.mark.parametrize("token", ["false", "0", "no", "off", "False"])
    def test_coerce_falsy(self, token: str) -> None:
        assert BooleanFilter().coerce(token, "exact") is False

    def test_coerce_invalid_raises(self) -> None:
        with pytest.raises(ValueError):
            BooleanFilter().coerce("maybe", "exact")

    def test_compile_exact_true(self) -> None:
        result = BooleanFilter().compile(("active",), "exact", True)
        assert isinstance(result, ComparisonFilter)
        assert result.operator == "eq"
        assert result.value is True

    def test_compile_exact_false(self) -> None:
        result = BooleanFilter().compile(("active",), "exact", False)
        assert isinstance(result, ComparisonFilter)
        assert result.value is False

    def test_compile_isnull(self) -> None:
        assert isinstance(BooleanFilter().compile(("active",), "isnull", True), NullFilter)
        assert isinstance(BooleanFilter().compile(("active",), "isnull", False), NotNullFilter)


class TestPackageReExports:
    def test_string_filter_importable_from_package(self) -> None:
        from advanced_alchemy.filters import StringFilter as Reexport

        assert Reexport is StringFilter

    def test_number_filter_importable_from_package(self) -> None:
        from advanced_alchemy.filters import NumberFilter as Reexport

        assert Reexport is NumberFilter

    def test_boolean_filter_importable_from_package(self) -> None:
        from advanced_alchemy.filters import BooleanFilter as Reexport

        assert Reexport is BooleanFilter


class TestUnusedHelperImports:
    """Regression: the field filters need ``Any`` and ``Decimal`` to type-coerce."""

    def test_decimal_round_trip(self) -> None:
        coerced: Any = NumberFilter(type_=Decimal).coerce("1.50", "exact")
        assert coerced == Decimal("1.50")


class TestOperatorsMapISuffixOps:
    """Regression: ``istartswith`` and ``iendswith`` must produce distinct SQL.

    Before this phase, both lookups shared an ``ilike(v + "%")`` lambda, so
    ``iendswith`` silently behaved as ``istartswith``. StringFilter exposes
    both lookups, so the regression is now visible to every Tier 2 user.
    """

    def test_istartswith_uses_trailing_percent(self) -> None:
        from sqlalchemy import Column, String

        from advanced_alchemy.filters._columns import operators_map

        column = Column("title", String())
        clause = operators_map["istartswith"](column, "py")
        rendered = str(clause.compile(compile_kwargs={"literal_binds": True}))
        assert "py%" in rendered
        assert "%py" not in rendered.replace("py%", "")

    def test_iendswith_uses_leading_percent(self) -> None:
        from sqlalchemy import Column, String

        from advanced_alchemy.filters._columns import operators_map

        column = Column("title", String())
        clause = operators_map["iendswith"](column, "py")
        rendered = str(clause.compile(compile_kwargs={"literal_binds": True}))
        assert "%py" in rendered
        assert "py%" not in rendered.replace("%py", "")
