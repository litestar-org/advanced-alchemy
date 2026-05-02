"""Tests for ``FilterSet.to_openapi_parameters`` (Phase 6.1).

Asserts the structural contract of the OpenAPI fragment without locking
the full golden output yet (Phase 6.2 ships the per-filter golden):

* The method exists and returns a list of OpenAPI 3 parameter objects.
* Each parameter carries ``name``/``in``/``required``/``schema``.
* The default lookup uses the bare field name; non-default lookups use
  the ``name__lookup`` form.
* Array-shaped lookups (``in``, ``not_in``, ``between``) emit
  ``style: form`` and ``explode: false`` so the comma-separated form the
  parser already accepts is the documented one.
* :class:`OrderingFilter` emits a single parameter whose schema lists
  every allowed value plus the ``-``-prefixed counterpart.
"""

import enum
from decimal import Decimal
from typing import ClassVar
from uuid import UUID

import pytest
from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

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
    __tablename__ = "_fso_author"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50))


class _Status(enum.Enum):
    DRAFT = "draft"
    PUBLISHED = "published"


class _Post(_Base):
    __tablename__ = "_fso_post"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(120))
    views: Mapped[int] = mapped_column(Integer)
    author_id: Mapped[int] = mapped_column(ForeignKey("_fso_author.id"))
    author: Mapped[_Author] = relationship("_Author")


class _PostFilter(FilterSet):
    title = StringFilter(lookups=["exact", "icontains", "in"])
    views = NumberFilter(type_=int, lookups=["exact", "gt", "between"])
    author__name = StringFilter(lookups=["exact", "iexact"])
    order_by = OrderingFilter(allowed=["views", "title"])

    class Meta:
        model = _Post
        allowed_relationships: ClassVar = ["author"]


class TestStructure:
    def test_returns_list_of_dicts(self) -> None:
        params = _PostFilter().to_openapi_parameters()
        assert isinstance(params, list)
        assert all(isinstance(p, dict) for p in params)

    def test_each_parameter_has_required_keys(self) -> None:
        for param in _PostFilter().to_openapi_parameters():
            assert param["in"] == "query"
            assert param["required"] is False
            assert isinstance(param["name"], str)
            assert isinstance(param["schema"], dict)
            assert isinstance(param.get("description", ""), str)

    def test_default_lookup_uses_bare_name(self) -> None:
        names = {p["name"] for p in _PostFilter().to_openapi_parameters()}
        assert "title" in names
        assert "title__exact" not in names

    def test_non_default_lookup_uses_suffix(self) -> None:
        names = {p["name"] for p in _PostFilter().to_openapi_parameters()}
        assert "title__icontains" in names
        assert "title__in" in names
        assert "views__gt" in names
        assert "views__between" in names

    def test_relationship_path_preserves_dunder_name(self) -> None:
        names = {p["name"] for p in _PostFilter().to_openapi_parameters()}
        assert "author__name__iexact" in names


class TestSchemaShapes:
    def test_string_scalar_schema(self) -> None:
        param = _param_named(_PostFilter(), "title")
        assert param["schema"] == {"type": "string"}
        assert "explode" not in param

    def test_string_in_lookup_emits_array(self) -> None:
        param = _param_named(_PostFilter(), "title__in")
        assert param["schema"] == {"type": "array", "items": {"type": "string"}}
        assert param["style"] == "form"
        assert param["explode"] is False

    def test_number_scalar_int(self) -> None:
        param = _param_named(_PostFilter(), "views")
        assert param["schema"] == {"type": "integer"}

    def test_number_between_emits_fixed_size_array(self) -> None:
        param = _param_named(_PostFilter(), "views__between")
        assert param["schema"] == {
            "type": "array",
            "items": {"type": "integer"},
            "minItems": 2,
            "maxItems": 2,
        }
        assert param["explode"] is False


class TestOrderingFilter:
    def test_single_parameter_with_signed_enum(self) -> None:
        params = _PostFilter().to_openapi_parameters()
        ordering = [p for p in params if p["name"] == "order_by"]
        assert len(ordering) == 1
        param = ordering[0]
        assert param["schema"]["type"] == "array"
        assert param["schema"]["items"]["type"] == "string"
        enum_values = param["schema"]["items"]["enum"]
        assert set(enum_values) == {"views", "-views", "title", "-title"}
        assert param["style"] == "form"
        assert param["explode"] is False


class TestNumericVariants:
    def test_float_uses_number_format_double(self) -> None:
        class _F(FilterSet):
            views = NumberFilter(type_=float, lookups=["exact"])

            class Meta:
                model = _Post

        param = _param_named(_F(), "views")
        assert param["schema"] == {"type": "number", "format": "double"}

    def test_decimal_uses_number_format_decimal(self) -> None:
        class _F(FilterSet):
            views = NumberFilter(type_=Decimal, lookups=["exact"])

            class Meta:
                model = _Post

        param = _param_named(_F(), "views")
        assert param["schema"] == {"type": "number", "format": "decimal"}


class TestSpecialFilters:
    def test_boolean_filter(self) -> None:
        class _F(FilterSet):
            title = BooleanFilter(lookups=["exact"])

            class Meta:
                model = _Post

        param = _param_named(_F(), "title")
        assert param["schema"] == {"type": "boolean"}

    def test_uuid_exact(self) -> None:
        class _F(FilterSet):
            id = UUIDFilter(lookups=["exact"])

            class Meta:
                model = _Post

        param = _param_named(_F(), "id")
        assert param["schema"] == {"type": "string", "format": "uuid"}

    def test_isnull_is_always_boolean(self) -> None:
        class _F(FilterSet):
            title = StringFilter(lookups=["exact", "isnull"])

            class Meta:
                model = _Post

        param = _param_named(_F(), "title__isnull")
        assert param["schema"] == {"type": "boolean"}

    def test_date_format(self) -> None:
        class _F(FilterSet):
            id = DateFilter(lookups=["exact", "year"])

            class Meta:
                model = _Post

        scalar = _param_named(_F(), "id")
        year = _param_named(_F(), "id__year")
        assert scalar["schema"] == {"type": "string", "format": "date"}
        assert year["schema"] == {"type": "integer"}

    def test_datetime_format(self) -> None:
        class _F(FilterSet):
            id = DateTimeFilter(lookups=["exact", "hour"])

            class Meta:
                model = _Post

        scalar = _param_named(_F(), "id")
        hour = _param_named(_F(), "id__hour")
        assert scalar["schema"] == {"type": "string", "format": "date-time"}
        assert hour["schema"] == {"type": "integer"}

    def test_enum_emits_string_enum(self) -> None:
        class _F(FilterSet):
            id = EnumFilter(enum=_Status, lookups=["exact", "in"])

            class Meta:
                model = _Post

        scalar = _param_named(_F(), "id")
        listish = _param_named(_F(), "id__in")
        assert scalar["schema"] == {
            "type": "string",
            "enum": ["draft", "published"],
        }
        assert listish["schema"] == {
            "type": "array",
            "items": {"type": "string", "enum": ["draft", "published"]},
        }


class TestEmptyFilterSet:
    def test_no_fields_returns_empty(self) -> None:
        class _Empty(FilterSet):
            pass

        assert _Empty().to_openapi_parameters() == []


def _param_named(instance: FilterSet, name: str) -> dict:
    for param in instance.to_openapi_parameters():
        if param["name"] == name:
            return param
    pytest.fail(f"No parameter named {name!r} in {instance!r}")
