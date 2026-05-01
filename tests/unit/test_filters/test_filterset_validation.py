"""Tests for FilterSet class-creation validation.

Phase 3.5 of the FilterSet roadmap. Covers ``__init_subclass__``: every
declared field path is resolved against ``Meta.model`` at import time;
unknown columns, disallowed relationships, depth violations, and
unsupported lookups all raise :class:`ImproperConfigurationError`.
"""

import enum
from typing import ClassVar
from uuid import UUID

import pytest
from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from advanced_alchemy.exceptions import ImproperConfigurationError
from advanced_alchemy.filters import (
    BooleanFilter,
    EnumFilter,
    FieldSpec,
    FilterSet,
    NumberFilter,
    OrderingFilter,
    StringFilter,
    UUIDFilter,
)


class _Base(DeclarativeBase):
    pass


class _Color(enum.Enum):
    RED = "red"
    BLUE = "blue"


class _Org(_Base):
    __tablename__ = "_fsv_org"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50))
    country: Mapped[str] = mapped_column(String(2))


class _Author(_Base):
    __tablename__ = "_fsv_author"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50))
    is_staff: Mapped[bool] = mapped_column()
    org_id: Mapped[int] = mapped_column(ForeignKey("_fsv_org.id"))
    org: Mapped[_Org] = relationship("_Org")


class _Post(_Base):
    __tablename__ = "_fsv_post"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(120))
    body: Mapped[str] = mapped_column(String(2000))
    author_id: Mapped[int] = mapped_column(ForeignKey("_fsv_author.id"))
    author: Mapped[_Author] = relationship("_Author")


class TestHappyPathDeclaration:
    def test_simple_column_fields_resolve(self) -> None:
        class PostFilter(FilterSet):
            title = StringFilter(lookups=["exact", "icontains"])
            id = UUIDFilter(lookups=["exact"])

            class Meta:
                model = _Post

        specs = PostFilter._field_specs
        assert set(specs) == {"title", "id"}
        assert isinstance(specs["title"], FieldSpec)
        assert specs["title"].path == ("title",)
        assert specs["id"].path == ("id",)
        assert specs["id"].column is _Post.__table__.c.id

    def test_relationship_traversal_resolves(self) -> None:
        class PostFilter(FilterSet):
            author__name = StringFilter(lookups=["iexact"])

            class Meta:
                model = _Post
                allowed_relationships: ClassVar = ["author"]

        spec = PostFilter._field_specs["author__name"]
        assert spec.path == ("author", "name")
        assert spec.column is _Author.__table__.c.name

    def test_nested_relationship_traversal_resolves(self) -> None:
        class PostFilter(FilterSet):
            author__org__country = StringFilter(lookups=["in"])

            class Meta:
                model = _Post
                allowed_relationships: ClassVar = ["author", "org"]
                max_relationship_depth: ClassVar = 2

        spec = PostFilter._field_specs["author__org__country"]
        assert spec.path == ("author", "org", "country")
        assert spec.column is _Org.__table__.c.country

    def test_lookup_index_built(self) -> None:
        class PostFilter(FilterSet):
            title = StringFilter(lookups=["exact", "icontains"])

            class Meta:
                model = _Post

        idx = PostFilter._lookup_index
        assert ("title", "exact") in idx
        assert ("title", "icontains") in idx
        assert idx[("title", "exact")].path == ("title",)

    def test_field_specs_are_immutable(self) -> None:
        class PostFilter(FilterSet):
            title = StringFilter(lookups=["exact"])

            class Meta:
                model = _Post

        with pytest.raises(TypeError):
            PostFilter._field_specs["new"] = "x"  # type: ignore[index,assignment]


class TestColumnValidation:
    def test_unknown_column_raises(self) -> None:
        with pytest.raises(ImproperConfigurationError) as ei:

            class _Bad(FilterSet):
                ghost = StringFilter(lookups=["exact"])

                class Meta:
                    model = _Post

        assert "ghost" in str(ei.value)
        assert "_Post" in str(ei.value) or "Post" in str(ei.value)

    def test_terminal_relationship_segment_rejected(self) -> None:
        with pytest.raises(ImproperConfigurationError) as ei:

            class _Bad(FilterSet):
                author = StringFilter(lookups=["exact"])

                class Meta:
                    model = _Post
                    allowed_relationships: ClassVar = ["author"]

        assert "author" in str(ei.value)


class TestRelationshipValidation:
    def test_disallowed_relationship_rejected(self) -> None:
        with pytest.raises(ImproperConfigurationError) as ei:

            class _Bad(FilterSet):
                author__name = StringFilter(lookups=["exact"])

                class Meta:
                    model = _Post

        assert "author" in str(ei.value)

    def test_unknown_relationship_rejected(self) -> None:
        with pytest.raises(ImproperConfigurationError) as ei:

            class _Bad(FilterSet):
                ghost__name = StringFilter(lookups=["exact"])

                class Meta:
                    model = _Post
                    allowed_relationships: ClassVar = ["ghost"]

        assert "ghost" in str(ei.value)

    def test_depth_exceeded_rejected(self) -> None:
        with pytest.raises(ImproperConfigurationError) as ei:

            class _Bad(FilterSet):
                author__org__country = StringFilter(lookups=["exact"])

                class Meta:
                    model = _Post
                    allowed_relationships: ClassVar = ["author", "org"]
                    max_relationship_depth: ClassVar = 1

        assert "depth" in str(ei.value).lower()

    def test_default_depth_is_two(self) -> None:
        with pytest.raises(ImproperConfigurationError):

            class _Bad(FilterSet):
                a__b__c__d = StringFilter(lookups=["exact"])

                class Meta:
                    model = _Post


class TestMetaValidation:
    def test_missing_meta_treated_as_abstract(self) -> None:
        class _Abstract(FilterSet):
            pass

        assert _Abstract._field_specs == {}

    def test_meta_without_model_treated_as_abstract(self) -> None:
        class _Abstract(FilterSet):
            class Meta:
                pass

        assert _Abstract._field_specs == {}

    def test_filter_without_model_with_declared_field_rejected(self) -> None:
        with pytest.raises(ImproperConfigurationError):

            class _Bad(FilterSet):
                title = StringFilter(lookups=["exact"])

                class Meta:
                    pass

    def test_python_dunder_field_name_rejected(self) -> None:
        with pytest.raises(ImproperConfigurationError):

            class _Bad(FilterSet):
                __init__ = StringFilter(lookups=["exact"])  # type: ignore[assignment]

                class Meta:
                    model = _Post


class TestSubclassing:
    def test_subclass_inherits_field_specs(self) -> None:
        class BaseFilter(FilterSet):
            title = StringFilter(lookups=["exact"])

            class Meta:
                model = _Post

        class ExtendedFilter(BaseFilter):
            body = StringFilter(lookups=["icontains"])

            class Meta:
                model = _Post

        assert "title" in ExtendedFilter._field_specs
        assert "body" in ExtendedFilter._field_specs

    def test_subclass_can_override_field(self) -> None:
        class BaseFilter(FilterSet):
            title = StringFilter(lookups=["exact"])

            class Meta:
                model = _Post

        class ExtendedFilter(BaseFilter):
            title = StringFilter(lookups=["icontains"])

            class Meta:
                model = _Post

        idx = ExtendedFilter._lookup_index
        assert ("title", "icontains") in idx
        assert ("title", "exact") not in idx


class TestAutoGeneration:
    def test_auto_fields_generates_filters_with_inferred_types(self) -> None:
        class AuthorFilter(FilterSet):
            class Meta:
                model = _Author
                auto_fields: ClassVar = ["name", "is_staff", "id"]

        specs = AuthorFilter._field_specs
        assert {"name", "is_staff", "id"} <= set(specs)
        assert isinstance(specs["name"].filter, StringFilter)
        assert isinstance(specs["is_staff"].filter, BooleanFilter)
        assert isinstance(specs["id"].filter, NumberFilter)

    def test_auto_fields_does_not_override_explicit(self) -> None:
        class AuthorFilter(FilterSet):
            name = StringFilter(lookups=["exact"])

            class Meta:
                model = _Author
                auto_fields: ClassVar = ["name", "id"]

        idx = AuthorFilter._lookup_index
        assert ("name", "exact") in idx
        assert ("name", "icontains") not in idx

    def test_auto_lookups_overrides_default_lookups(self) -> None:
        class AuthorFilter(FilterSet):
            class Meta:
                model = _Author
                auto_fields: ClassVar = ["name"]
                auto_lookups: ClassVar = {"name": ["exact"]}

        idx = AuthorFilter._lookup_index
        assert ("name", "exact") in idx
        assert ("name", "icontains") not in idx

    def test_auto_field_unknown_column_rejected(self) -> None:
        with pytest.raises(ImproperConfigurationError):

            class _Bad(FilterSet):
                class Meta:
                    model = _Author
                    auto_fields: ClassVar = ["ghost"]


class TestOrderingFilterDeclaration:
    def test_ordering_filter_recognized(self) -> None:
        class PostFilter(FilterSet):
            order_by = OrderingFilter(allowed=["title", "id"])

            class Meta:
                model = _Post

        assert "order_by" in PostFilter._field_specs
        assert isinstance(
            PostFilter._field_specs["order_by"].filter,
            OrderingFilter,
        )


class TestEnumFilterDeclaration:
    def test_enum_filter_recognized(self) -> None:
        class _ColorBase(DeclarativeBase):
            pass

        class _Item(_ColorBase):
            __tablename__ = "_fsv_item"
            id: Mapped[int] = mapped_column(primary_key=True)
            color: Mapped[str] = mapped_column(String(10))

        class ItemFilter(FilterSet):
            color = EnumFilter(enum=_Color, lookups=["exact", "in"])

            class Meta:
                model = _Item

        assert "color" in ItemFilter._field_specs


class TestPackageReExport:
    def test_filterset_importable_from_package(self) -> None:
        from advanced_alchemy import filters

        assert filters.FilterSet is FilterSet
