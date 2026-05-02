"""Tests for ``FilterSet.to_openapi_parameters`` (Phases 6.1 + 6.2).

Phase 6.1 — structural contract:

* The method exists and returns a list of OpenAPI 3 parameter objects.
* Each parameter carries ``name``/``in``/``required``/``schema``.
* The default lookup uses the bare field name; non-default lookups use
  the ``name__lookup`` form.
* Array-shaped lookups (``in``, ``not_in``, ``between``) emit
  ``style: form`` and ``explode: false`` so the comma-separated form the
  parser already accepts is the documented one.
* :class:`OrderingFilter` emits a single parameter whose schema lists
  every allowed value plus the ``-``-prefixed counterpart.

Phase 6.2 — golden + per-filter coverage:

* :class:`TestGoldenOutput` pins the entire output for a fixture
  :class:`FilterSet` so any drift in shape, ordering, or content shows
  up in a diff.
* :class:`TestPerFilterSchemas` parametrizes every built-in field filter
  with the full lookup catalog and asserts the schema dict for each
  ``(filter, lookup)`` pair.
"""

import enum
from decimal import Decimal
from typing import Any, ClassVar
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


class _GoldenStatus(enum.Enum):
    DRAFT = "draft"
    PUBLISHED = "published"


class _GoldenAuthor(_Base):
    __tablename__ = "_fso_golden_author"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50))


class _GoldenPost(_Base):
    __tablename__ = "_fso_golden_post"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(120))
    views: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16))
    author_id: Mapped[int] = mapped_column(ForeignKey("_fso_golden_author.id"))
    author: Mapped[_GoldenAuthor] = relationship("_GoldenAuthor")


class _GoldenPostFilter(FilterSet):
    """Comprehensive fixture FilterSet for golden output assertion."""

    id = UUIDFilter(lookups=["exact", "in"])
    title = StringFilter(lookups=["exact", "icontains", "isnull"])
    views = NumberFilter(type_=int, lookups=["exact", "between"])
    status = EnumFilter(enum=_GoldenStatus, lookups=["exact", "in"])
    author__name = StringFilter(lookups=["iexact"])
    order_by = OrderingFilter(allowed=["views", "title"])

    class Meta:
        model = _GoldenPost
        allowed_relationships: ClassVar = ["author"]


_EXPECTED_GOLDEN_PARAMETERS: list[dict[str, Any]] = [
    {
        "name": "id",
        "in": "query",
        "required": False,
        "description": "Filter where `id` equals the given value.",
        "schema": {"type": "string", "format": "uuid"},
    },
    {
        "name": "id__in",
        "in": "query",
        "required": False,
        "description": "Filter where `id` is in the comma-separated list of values.",
        "schema": {"type": "array", "items": {"type": "string", "format": "uuid"}},
        "style": "form",
        "explode": False,
    },
    {
        "name": "title",
        "in": "query",
        "required": False,
        "description": "Filter where `title` equals the given value.",
        "schema": {"type": "string"},
    },
    {
        "name": "title__icontains",
        "in": "query",
        "required": False,
        "description": "Filter where `title` contains the given substring (case-insensitive).",
        "schema": {"type": "string"},
    },
    {
        "name": "title__isnull",
        "in": "query",
        "required": False,
        "description": "Filter where `title` is null when true, not null when false.",
        "schema": {"type": "boolean"},
    },
    {
        "name": "views__between",
        "in": "query",
        "required": False,
        "description": "Filter where `views` is between the two comma-separated values (inclusive).",
        "schema": {
            "type": "array",
            "items": {"type": "integer"},
            "minItems": 2,
            "maxItems": 2,
        },
        "style": "form",
        "explode": False,
    },
    {
        "name": "views",
        "in": "query",
        "required": False,
        "description": "Filter where `views` equals the given value.",
        "schema": {"type": "integer"},
    },
    {
        "name": "status",
        "in": "query",
        "required": False,
        "description": "Filter where `status` equals the given value.",
        "schema": {"type": "string", "enum": ["draft", "published"]},
    },
    {
        "name": "status__in",
        "in": "query",
        "required": False,
        "description": "Filter where `status` is in the comma-separated list of values.",
        "schema": {
            "type": "array",
            "items": {"type": "string", "enum": ["draft", "published"]},
        },
        "style": "form",
        "explode": False,
    },
    {
        "name": "author__name",
        "in": "query",
        "required": False,
        "description": "Filter where `author__name` equals the given value (case-insensitive).",
        "schema": {"type": "string"},
    },
    {
        "name": "order_by",
        "in": "query",
        "required": False,
        "description": ("Order results by one or more allowed fields. Prefix a field with '-' for descending."),
        "schema": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": ["views", "-views", "title", "-title"],
            },
        },
        "style": "form",
        "explode": False,
    },
]


class TestGoldenOutput:
    """Phase 6.2 — pin the entire output for a comprehensive fixture."""

    def test_golden_matches_full_expected_list(self) -> None:
        produced = _GoldenPostFilter().to_openapi_parameters()
        assert produced == _EXPECTED_GOLDEN_PARAMETERS

    def test_golden_emits_one_parameter_per_field_lookup_pair(self) -> None:
        produced = _GoldenPostFilter().to_openapi_parameters()
        names = [p["name"] for p in produced]
        assert len(names) == len(set(names)), "Parameter names must be unique."

    def test_golden_preserves_declaration_order(self) -> None:
        produced = _GoldenPostFilter().to_openapi_parameters()
        first_field_seen = []
        for param in produced:
            base = param["name"].split("__")[0]
            if base not in first_field_seen:
                first_field_seen.append(base)
        assert first_field_seen == ["id", "title", "views", "status", "author", "order_by"]


_STRING_LOOKUP_SCHEMAS: dict[str, dict[str, Any]] = {
    "exact": {"type": "string"},
    "iexact": {"type": "string"},
    "contains": {"type": "string"},
    "icontains": {"type": "string"},
    "startswith": {"type": "string"},
    "istartswith": {"type": "string"},
    "endswith": {"type": "string"},
    "iendswith": {"type": "string"},
    "in": {"type": "array", "items": {"type": "string"}},
    "not_in": {"type": "array", "items": {"type": "string"}},
    "isnull": {"type": "boolean"},
}

_INT_NUMBER_LOOKUP_SCHEMAS: dict[str, dict[str, Any]] = {
    "exact": {"type": "integer"},
    "gt": {"type": "integer"},
    "gte": {"type": "integer"},
    "lt": {"type": "integer"},
    "lte": {"type": "integer"},
    "between": {
        "type": "array",
        "items": {"type": "integer"},
        "minItems": 2,
        "maxItems": 2,
    },
    "in": {"type": "array", "items": {"type": "integer"}},
    "not_in": {"type": "array", "items": {"type": "integer"}},
    "isnull": {"type": "boolean"},
}

_BOOLEAN_LOOKUP_SCHEMAS: dict[str, dict[str, Any]] = {
    "exact": {"type": "boolean"},
    "isnull": {"type": "boolean"},
}

_DATE_LOOKUP_SCHEMAS: dict[str, dict[str, Any]] = {
    "exact": {"type": "string", "format": "date"},
    "gt": {"type": "string", "format": "date"},
    "gte": {"type": "string", "format": "date"},
    "lt": {"type": "string", "format": "date"},
    "lte": {"type": "string", "format": "date"},
    "between": {
        "type": "array",
        "items": {"type": "string", "format": "date"},
        "minItems": 2,
        "maxItems": 2,
    },
    "year": {"type": "integer"},
    "month": {"type": "integer"},
    "day": {"type": "integer"},
    "in": {"type": "array", "items": {"type": "string", "format": "date"}},
    "not_in": {"type": "array", "items": {"type": "string", "format": "date"}},
    "isnull": {"type": "boolean"},
}

_DATETIME_LOOKUP_SCHEMAS: dict[str, dict[str, Any]] = {
    **{
        lookup: ({"type": "string", "format": "date-time"} if schema.get("format") == "date" else schema)
        for lookup, schema in _DATE_LOOKUP_SCHEMAS.items()
    },
    "between": {
        "type": "array",
        "items": {"type": "string", "format": "date-time"},
        "minItems": 2,
        "maxItems": 2,
    },
    "in": {"type": "array", "items": {"type": "string", "format": "date-time"}},
    "not_in": {"type": "array", "items": {"type": "string", "format": "date-time"}},
    "hour": {"type": "integer"},
    "minute": {"type": "integer"},
    "second": {"type": "integer"},
}

_UUID_LOOKUP_SCHEMAS: dict[str, dict[str, Any]] = {
    "exact": {"type": "string", "format": "uuid"},
    "in": {"type": "array", "items": {"type": "string", "format": "uuid"}},
    "not_in": {"type": "array", "items": {"type": "string", "format": "uuid"}},
    "isnull": {"type": "boolean"},
}


class _IntStatus(enum.IntEnum):
    LOW = 1
    HIGH = 2


_ENUM_STR_LOOKUP_SCHEMAS: dict[str, dict[str, Any]] = {
    "exact": {"type": "string", "enum": ["draft", "published"]},
    "in": {"type": "array", "items": {"type": "string", "enum": ["draft", "published"]}},
    "not_in": {"type": "array", "items": {"type": "string", "enum": ["draft", "published"]}},
    "isnull": {"type": "boolean"},
}

_ENUM_INT_LOOKUP_SCHEMAS: dict[str, dict[str, Any]] = {
    "exact": {"type": "integer", "enum": [1, 2]},
    "in": {"type": "array", "items": {"type": "integer", "enum": [1, 2]}},
    "not_in": {"type": "array", "items": {"type": "integer", "enum": [1, 2]}},
    "isnull": {"type": "boolean"},
}


@pytest.mark.parametrize(
    ("filter_factory", "expected"),
    [
        pytest.param(lambda: StringFilter(), _STRING_LOOKUP_SCHEMAS, id="StringFilter"),
        pytest.param(
            lambda: NumberFilter(type_=int),
            _INT_NUMBER_LOOKUP_SCHEMAS,
            id="NumberFilter[int]",
        ),
        pytest.param(lambda: BooleanFilter(), _BOOLEAN_LOOKUP_SCHEMAS, id="BooleanFilter"),
        pytest.param(lambda: DateFilter(), _DATE_LOOKUP_SCHEMAS, id="DateFilter"),
        pytest.param(lambda: DateTimeFilter(), _DATETIME_LOOKUP_SCHEMAS, id="DateTimeFilter"),
        pytest.param(lambda: UUIDFilter(), _UUID_LOOKUP_SCHEMAS, id="UUIDFilter"),
        pytest.param(
            lambda: EnumFilter(enum=_GoldenStatus),
            _ENUM_STR_LOOKUP_SCHEMAS,
            id="EnumFilter[str]",
        ),
        pytest.param(
            lambda: EnumFilter(enum=_IntStatus),
            _ENUM_INT_LOOKUP_SCHEMAS,
            id="EnumFilter[int]",
        ),
    ],
)
class TestPerFilterSchemas:
    """Phase 6.2 — every (filter, lookup) pair produces the right schema."""

    def test_every_supported_lookup_has_schema_entry(
        self,
        filter_factory: "object",
        expected: dict[str, dict[str, Any]],
    ) -> None:
        instance = filter_factory()  # type: ignore[operator]
        assert set(instance.supported_lookups) == set(expected), (
            f"Test fixture out of sync with {type(instance).__name__}.supported_lookups."
        )

    def test_each_emitted_parameter_has_expected_schema(
        self,
        filter_factory: "object",
        expected: dict[str, dict[str, Any]],
    ) -> None:
        instance = filter_factory()  # type: ignore[operator]
        params = instance.openapi_parameters(name="x")
        produced = {p["name"]: p["schema"] for p in params}
        default = instance.effective_default_lookup
        for lookup, expected_schema in expected.items():
            param_name = "x" if lookup == default else f"x__{lookup}"
            assert produced.get(param_name) == expected_schema, (
                f"Lookup {lookup!r} produced {produced.get(param_name)!r}, expected {expected_schema!r}."
            )


class TestOrderingFilterSelfContained:
    """OrderingFilter ignores supported_lookups; verify standalone shape."""

    def test_emits_exactly_one_parameter(self) -> None:
        params = OrderingFilter(allowed=["a", "b"]).openapi_parameters(name="sort")
        assert len(params) == 1

    def test_signed_enum_pairs_each_allowed(self) -> None:
        params = OrderingFilter(allowed=["a", "b", "c"]).openapi_parameters(name="sort")
        items = params[0]["schema"]["items"]
        assert items["enum"] == ["a", "-a", "b", "-b", "c", "-c"]

    def test_form_style_no_explode(self) -> None:
        params = OrderingFilter(allowed=["a"]).openapi_parameters(name="sort")
        assert params[0]["style"] == "form"
        assert params[0]["explode"] is False
