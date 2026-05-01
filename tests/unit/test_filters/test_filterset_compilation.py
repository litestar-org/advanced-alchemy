"""Tests for FilterSet compilation (Phase 5).

Covers two compile-time concerns:

* :func:`~advanced_alchemy.filters._filterset._compile_path` — wraps a
  Tier 1 leaf filter in nested :class:`RelationshipFilter` instances when
  the resolved path traverses one or more relationships.
* :meth:`FilterSet.to_filters` — walks ``self._invocations`` in
  declaration order, calls each field filter's ``compile``, applies the
  path-wrapping helper, and emits :class:`OrderingApply` last so the
  ``WHERE`` clause stays stable across runs.
"""

from typing import ClassVar
from uuid import UUID

import pytest
from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from advanced_alchemy.filters import (
    CollectionFilter,
    ComparisonFilter,
    FilterSet,
    NumberFilter,
    OrderingApply,
    OrderingFilter,
    RelationshipFilter,
    StringFilter,
)
from advanced_alchemy.filters._filterset import _compile_path


class _Base(DeclarativeBase):
    pass


class _Country(_Base):
    __tablename__ = "_fsc_country"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(2))


class _Org(_Base):
    __tablename__ = "_fsc_org"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50))
    country_id: Mapped[int] = mapped_column(ForeignKey("_fsc_country.id"))
    country: Mapped[_Country] = relationship("_Country")


class _Author(_Base):
    __tablename__ = "_fsc_author"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50))
    org_id: Mapped[int] = mapped_column(ForeignKey("_fsc_org.id"))
    org: Mapped[_Org] = relationship("_Org")


class _Post(_Base):
    __tablename__ = "_fsc_post"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(120))
    views: Mapped[int] = mapped_column(Integer)
    author_id: Mapped[int] = mapped_column(ForeignKey("_fsc_author.id"))
    author: Mapped[_Author] = relationship("_Author")


class TestCompilePath:
    def test_depth_zero_returns_leaf_unchanged(self) -> None:
        leaf = ComparisonFilter(field_name="title", operator="eq", value="hello")
        result = _compile_path(("title",), leaf)
        assert result is leaf

    def test_depth_one_wraps_in_single_relationship_filter(self) -> None:
        leaf = ComparisonFilter(field_name="name", operator="eq", value="ada")
        result = _compile_path(("author", "name"), leaf)
        assert isinstance(result, RelationshipFilter)
        assert result.relationship == "author"
        assert list(result.filters) == [leaf]
        assert result.negate is False

    def test_depth_two_nests_relationship_filters(self) -> None:
        leaf = CollectionFilter(field_name="code", values=["US", "UK"])
        result = _compile_path(("author", "org", "country", "code"), leaf)
        assert isinstance(result, RelationshipFilter)
        assert result.relationship == "author"
        assert len(result.filters) == 1
        inner_org = result.filters[0]
        assert isinstance(inner_org, RelationshipFilter)
        assert inner_org.relationship == "org"
        inner_country = inner_org.filters[0]
        assert isinstance(inner_country, RelationshipFilter)
        assert inner_country.relationship == "country"
        assert list(inner_country.filters) == [leaf]

    def test_empty_path_rejected(self) -> None:
        leaf = ComparisonFilter(field_name="x", operator="eq", value=1)
        with pytest.raises(ValueError, match="non-empty"):
            _compile_path((), leaf)


class _PostFilter(FilterSet):
    title = StringFilter(lookups=["exact", "icontains"])
    views = NumberFilter(type_=int, lookups=["gt", "lt", "exact"])
    author__name = StringFilter(lookups=["iexact"])
    author__org__country__code = StringFilter(lookups=["in"])
    order_by = OrderingFilter(allowed=["views", "title"])

    class Meta:
        model = _Post
        allowed_relationships: ClassVar = ["author", "org", "country"]
        max_relationship_depth: ClassVar = 3


class TestToFilters:
    def test_empty_invocations_yield_empty_list(self) -> None:
        instance = _PostFilter()
        assert instance.to_filters() == []

    def test_simple_column_filter_compiles_to_leaf(self) -> None:
        instance = _PostFilter.from_query_params({"title": "hello"})
        result = instance.to_filters()
        assert len(result) == 1
        assert isinstance(result[0], ComparisonFilter)
        assert result[0].field_name == "title"
        assert result[0].operator == "eq"
        assert result[0].value == "hello"

    def test_relationship_path_compiles_to_relationship_filter(self) -> None:
        instance = _PostFilter.from_query_params({"author__name__iexact": "ada"})
        result = instance.to_filters()
        assert len(result) == 1
        wrapper = result[0]
        assert isinstance(wrapper, RelationshipFilter)
        assert wrapper.relationship == "author"
        assert len(wrapper.filters) == 1
        leaf = wrapper.filters[0]
        assert isinstance(leaf, ComparisonFilter)
        assert leaf.field_name == "name"
        assert leaf.operator == "ilike"
        assert leaf.value == "ada"

    def test_nested_relationship_path_compiles_to_nested_chain(self) -> None:
        instance = _PostFilter.from_query_params(
            {"author__org__country__code__in": "US,UK"},
        )
        result = instance.to_filters()
        assert len(result) == 1
        outer = result[0]
        assert isinstance(outer, RelationshipFilter)
        assert outer.relationship == "author"
        org_filter = outer.filters[0]
        assert isinstance(org_filter, RelationshipFilter)
        assert org_filter.relationship == "org"
        country_filter = org_filter.filters[0]
        assert isinstance(country_filter, RelationshipFilter)
        assert country_filter.relationship == "country"
        leaf = country_filter.filters[0]
        assert isinstance(leaf, CollectionFilter)
        assert leaf.field_name == "code"
        assert leaf.values == ["US", "UK"]

    def test_declaration_order_is_preserved(self) -> None:
        instance = _PostFilter.from_query_params(
            {"views__gt": "10", "title__icontains": "py"},
        )
        result = instance.to_filters()
        assert len(result) == 2
        first, second = result
        assert isinstance(first, ComparisonFilter)
        assert first.field_name == "views"
        assert first.operator == "gt"
        from advanced_alchemy.filters import SearchFilter

        assert isinstance(second, SearchFilter)
        assert second.field_name == "title"

    def test_ordering_filter_appended_last(self) -> None:
        instance = _PostFilter.from_query_params(
            {"order_by": "-views,title", "title": "hello"},
        )
        result = instance.to_filters()
        assert len(result) == 2
        first, last = result
        assert isinstance(first, ComparisonFilter)
        assert isinstance(last, OrderingApply)
        assert last.orderings == [("views", "desc"), ("title", "asc")]

    def test_ordering_only(self) -> None:
        instance = _PostFilter.from_query_params({"order_by": "title"})
        result = instance.to_filters()
        assert len(result) == 1
        assert isinstance(result[0], OrderingApply)
        assert result[0].orderings == [("title", "asc")]

    def test_to_filters_is_idempotent(self) -> None:
        instance = _PostFilter.from_query_params({"title": "x", "order_by": "title"})
        first_call = instance.to_filters()
        second_call = instance.to_filters()
        assert len(first_call) == len(second_call) == 2
        assert isinstance(first_call[0], ComparisonFilter)
        assert isinstance(second_call[0], ComparisonFilter)
        assert first_call[0].value == second_call[0].value
        assert isinstance(first_call[-1], OrderingApply)
        assert isinstance(second_call[-1], OrderingApply)
