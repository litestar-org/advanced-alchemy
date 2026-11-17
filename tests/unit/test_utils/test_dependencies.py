"""Unit tests for shared dependency-injection utilities."""

import datetime as dt
from decimal import Decimal
from enum import Enum
from typing import Any, Optional, cast
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, Numeric, String, Text, Time, TypeDecorator, Uuid
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from advanced_alchemy.exceptions import ImproperConfigurationError
from advanced_alchemy.filters import (
    ComparisonFilter,
    InCollectionFilter,
    NotNullFilter,
    NullFilter,
    OrderByFilter,
    RelationshipFilter,
    SearchFilter,
)
from advanced_alchemy.utils.dependencies import (
    ChoiceField,
    DependencyCache,
    FieldNameType,
    FilterConfig,
    build_field_filter,
    build_field_filters,
    build_order_by_filters,
    filter_parameter_type,
    group_filter_fields,
    make_hashable,
    normalize_choice_field_types,
    normalize_sort_field,
    normalize_sort_fields,
    resolve_filter_fields,
    resolve_pagination_bounds,
)
from advanced_alchemy.utils.singleton import SingletonMeta

pytestmark = pytest.mark.unit


class StatusChoice(str, Enum):
    ACTIVE = "active"
    PENDING = "pending"


def test_field_name_type_is_named_tuple_with_default_type_hint() -> None:
    field = FieldNameType(name="id")

    assert field.name == "id"
    assert field.type_hint is str
    assert tuple(field) == ("id", str)


def test_filter_config_allows_empty_config() -> None:
    config: FilterConfig = {}

    assert config == {}


def test_make_hashable_dict_order_invariant() -> None:
    left: dict[str, Any] = {"x": 1, "y": 2}
    right: dict[str, Any] = {"y": 2, "x": 1}

    assert make_hashable(left) == make_hashable(right)


def test_make_hashable_nested_values() -> None:
    config: FilterConfig = cast(
        "FilterConfig",
        {
            "sort_field": ("a", "b"),
            "search_ignore_case": True,
            "in_fields": [FieldNameType("tag")],
            "choice_fields": [ChoiceField("status", ["active", "pending"])],
        },
    )

    assert make_hashable(config) == make_hashable(dict(config))


def test_make_hashable_set_order_invariant() -> None:
    assert make_hashable({1, 2, 3}) == make_hashable({3, 2, 1})


def test_make_hashable_preserves_list_order() -> None:
    assert make_hashable(["name", "id"]) != make_hashable(["id", "name"])


def test_normalize_sort_field_preserves_list_order() -> None:
    assert normalize_sort_field(["name", "id"]) == "name"


def test_normalize_sort_field_sorts_set_values() -> None:
    assert normalize_sort_field({"name", "id"}) == "id"


def test_normalize_choice_field_types_supports_explicit_values() -> None:
    normalized = normalize_choice_field_types([ChoiceField("status", ["active", "pending"])])
    field = next(iter(normalized))

    assert field.name == "status"
    assert "active" in str(field.type_hint)
    assert "pending" in str(field.type_hint)


def test_normalize_choice_field_types_supports_explicit_value_tuples() -> None:
    normalized = normalize_choice_field_types(("status", ("active", "pending")))
    field = next(iter(normalized))

    assert field.name == "status"
    assert "active" in str(field.type_hint)
    assert "pending" in str(field.type_hint)


def test_normalize_choice_field_types_supports_type_hint_tuples() -> None:
    normalized = normalize_choice_field_types(("status", StatusChoice))
    field = next(iter(normalized))

    assert field.name == "status"
    assert field.type_hint is StatusChoice


def test_normalize_choice_field_types_preserves_list_order() -> None:
    normalized = normalize_choice_field_types([("visibility", ["public", "private"]), FieldNameType("status", str)])

    assert [field.name for field in normalized] == ["visibility", "status"]


def test_dependency_cache_singleton() -> None:
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(SingletonMeta, "_instances", {})
        first = DependencyCache()
        second = DependencyCache()

    assert first is second


def test_dependency_cache_add_get_dependencies() -> None:
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(SingletonMeta, "_instances", {})
        cache = DependencyCache()
        dependencies = {"filters": MagicMock()}

        cache.add_dependencies("key", dependencies)

        assert cache.get_dependencies("key") == dependencies
        assert cache.get_dependencies("missing") is None


def test_dependency_cache_get_set_by_config() -> None:
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(SingletonMeta, "_instances", {})
        cache = DependencyCache()
        config: FilterConfig = {"id_field": "uuid"}
        dependencies = {"filters": MagicMock()}

        cache.set(config, dependencies)

        assert cache.get(config) == dependencies


def _get_framework_filter_factories() -> tuple[Any, ...]:
    """Import FastAPI and Litestar filter factories when those optional frameworks are installed."""
    fastapi_providers = pytest.importorskip("advanced_alchemy.extensions.fastapi.providers")
    litestar_providers = pytest.importorskip("advanced_alchemy.extensions.litestar.providers")
    return (fastapi_providers.provide_filters, litestar_providers.create_filter_dependencies)


def test_filter_cache_uses_resolved_names_across_frameworks() -> None:
    class Generator:
        def __init__(self, prefix: str) -> None:
            self.prefix = prefix

        def __call__(self, name: str) -> str:
            return self.prefix + name

        def __bool__(self) -> bool:
            return False

    for factory in _get_framework_filter_factories():
        generator = Generator("first_")
        config: FilterConfig = {"search": "name", "alias_generator": generator}
        first = factory(config)
        assert first is factory({"search": "name", "alias_generator": Generator("first_")})
        generator.prefix = "second_"
        assert first is not factory(config)


def test_custom_alias_validation_is_opt_in_for_both_frameworks() -> None:
    for factory in _get_framework_filter_factories():
        factory({"boolean_fields": ["status_in"], "in_fields": ["status"]})
        with pytest.raises(ImproperConfigurationError, match="duplicate query parameter"):
            factory({"created_at": True, "alias_generator": lambda name: "same"})


def test_alias_presets_share_effective_names_across_frameworks() -> None:
    for factory in _get_framework_filter_factories():
        assert factory({"search": "name", "alias_generator": "snake_case"}) is factory(
            {"search": "name", "alias_generator": lambda name: name}
        )
        assert factory({"search": "name", "alias_generator": "camel_case"}) is factory({"search": "name"})
        with pytest.raises(ImproperConfigurationError, match="Unknown filter alias preset"):
            factory(cast(FilterConfig, {"search": "name", "alias_generator": "typo"}))


class _GridTestBase(DeclarativeBase):
    """Isolated base for filter metadata inference unit tests."""


class _GridTestAuthor(_GridTestBase):
    """Author model for dotted relationship filter metadata tests."""

    __tablename__ = "grid_meta_author"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    country: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    posts: Mapped[list["_GridTestPost"]] = relationship(back_populates="author")


class _GridTestPost(_GridTestBase):
    """Post model exercising every supported column type."""

    __tablename__ = "grid_meta_post"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    title: Mapped[str] = mapped_column(String(100))
    subtitle: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    views: Mapped[int] = mapped_column(Integer)
    rating: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    is_published: Mapped[bool] = mapped_column()
    status: Mapped[StatusChoice] = mapped_column(SAEnum(StatusChoice))
    published_date: Mapped[dt.date] = mapped_column(Date)
    published_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    publish_time: Mapped[dt.time] = mapped_column(Time)
    author_id: Mapped[UUID] = mapped_column(ForeignKey("grid_meta_author.id"))
    author: Mapped[_GridTestAuthor] = relationship(back_populates="posts")


@pytest.mark.parametrize(
    ("field_path", "expected_ops", "expected_type"),
    [
        ("title", ("eq", "ne", "contains", "startswith", "endswith", "in"), str),
        ("subtitle", ("eq", "ne", "contains", "startswith", "endswith", "in", "is_null"), str),
        ("views", ("eq", "ne", "gt", "ge", "lt", "le", "in"), int),
        ("rating", ("eq", "ne", "gt", "ge", "lt", "le", "in", "is_null"), float),
        ("price", ("eq", "ne", "gt", "ge", "lt", "le", "in"), Decimal),
        ("is_published", ("eq",), bool),
        ("status", ("eq", "ne", "in"), StatusChoice),
        ("id", ("eq", "ne", "in"), UUID),
        ("published_date", ("eq", "ne", "gt", "ge", "lt", "le", "in"), dt.date),
        ("published_at", ("eq", "ne", "gt", "ge", "lt", "le", "in", "is_null"), dt.datetime),
        ("publish_time", ("eq", "ne", "gt", "ge", "lt", "le", "in"), dt.time),
        ("author.name", ("eq", "ne", "contains", "startswith", "endswith", "in"), str),
        ("author.country", ("eq", "ne", "contains", "startswith", "endswith", "in", "is_null"), str),
    ],
)
def test_resolve_filter_fields_infers_column_operators(
    field_path: str,
    expected_ops: tuple[str, ...],
    expected_type: Any,
) -> None:
    specs = resolve_filter_fields([field_path], _GridTestPost)
    assert tuple(spec.operator for spec in specs) == expected_ops
    assert all(spec.value_type is expected_type for spec in specs)
    base_name = field_path.replace(".", "_")
    assert tuple(spec.param_name for spec in specs) == tuple(f"{base_name}_{op}" for op in expected_ops)


def test_resolve_filter_fields_narrowing_and_grouping() -> None:
    specs = resolve_filter_fields(
        {
            "title": {"contains", "eq"},
            "views": {"le", "ge"},
            "author.name": {"contains", "eq"},
        },
        _GridTestPost,
    )
    assert [(spec.param_name, spec.operator) for spec in specs] == [
        ("title_eq", "eq"),
        ("title_contains", "contains"),
        ("views_ge", "ge"),
        ("views_le", "le"),
        ("author_name_eq", "eq"),
        ("author_name_contains", "contains"),
    ]

    groups = group_filter_fields(specs)
    assert len(groups) == 3
    rel_group = next(group for group in groups if group[0] == ("author",))
    assert [spec.param_name for spec in rel_group[2]] == ["author_name_eq", "author_name_contains"]

    built_rel = build_field_filters(
        rel_group[2],
        {"author_name_eq": "Ada", "author_name_contains": "da"},
        rel_path=("author",),
    )
    assert isinstance(built_rel, RelationshipFilter)
    assert built_rel.relationship == "author"
    assert isinstance(built_rel.filters[0], ComparisonFilter)
    assert isinstance(built_rel.filters[1], SearchFilter)


def test_field_filter_query_types_and_filter_builders() -> None:
    specs = resolve_filter_fields(
        {"subtitle": {"contains", "is_null"}, "views": {"in", "ge"}},
        _GridTestPost,
    )
    by_name = {spec.param_name: spec for spec in specs}
    assert filter_parameter_type(by_name["subtitle_contains"]) == Optional[str]
    assert filter_parameter_type(by_name["subtitle_is_null"]) == Optional[bool]
    assert filter_parameter_type(by_name["views_in"]) == Optional[list[int]]
    assert filter_parameter_type(by_name["views_ge"]) == Optional[int]

    assert isinstance(build_field_filter(by_name["subtitle_is_null"], True), NullFilter)
    assert isinstance(build_field_filter(by_name["subtitle_is_null"], False), NotNullFilter)
    assert isinstance(build_field_filter(by_name["views_in"], [10, 20]), InCollectionFilter)
    assert build_field_filter(by_name["views_in"], []) is None


@pytest.mark.parametrize(
    ("filter_fields", "model", "match"),
    [
        (["title"], None, "requires a SQLAlchemy model"),
        ({"views": {"contains"}}, _GridTestPost, "String filter operator 'contains'"),
        ({"title": {"ge"}}, _GridTestPost, "Range filter operator 'ge'"),
        ({"is_published": {"gt"}}, _GridTestPost, "Range filter operator 'gt'"),
        (cast(Any, {"views": {"bogus"}}), _GridTestPost, "Unsupported filter operator 'bogus'"),
        (["missing"], _GridTestPost, "Unknown column 'missing'"),
        (["author.missing"], _GridTestPost, "Unknown column 'missing'"),
        (["missing_rel.name"], _GridTestPost, "Unknown relationship 'missing_rel'"),
        (["bad..path"], _GridTestPost, "Invalid field path"),
    ],
)
def test_resolve_filter_fields_rejects_invalid_config(
    filter_fields: Any,
    model: Optional[type[Any]],
    match: str,
) -> None:
    with pytest.raises(ImproperConfigurationError, match=match):
        resolve_filter_fields(filter_fields, model)


def test_normalize_sort_fields_and_collection_rejection() -> None:
    assert normalize_sort_fields(["views", "author.name", "views"], _GridTestPost) == ("views", "author.name")
    assert normalize_sort_fields({"views", "title"}, _GridTestPost) == ("title", "views")
    with pytest.raises(ImproperConfigurationError, match="only to-one paths are sortable"):
        normalize_sort_fields(["posts.title"], _GridTestAuthor)


@pytest.mark.parametrize(
    ("order_by_values", "sort_order", "default_field", "expected"),
    [
        (
            ["-views", "author.name"],
            None,
            "title",
            [OrderByFilter("views", "desc"), OrderByFilter("author.name", "asc")],
        ),
        (["+title"], "desc", None, [OrderByFilter("title", "asc")]),
        (["views"], "desc", None, [OrderByFilter("views", "desc")]),
        (None, None, "views", [OrderByFilter("views", "desc")]),
        (None, None, None, []),
    ],
)
def test_build_order_by_filters_valid_cases(
    order_by_values: Optional[list[str]],
    sort_order: Any,
    default_field: Optional[str],
    expected: list[OrderByFilter],
) -> None:
    result = build_order_by_filters(
        order_by_values,
        sort_order,
        allowed_fields={"title", "views", "author.name"},
        default_field=default_field,
        default_order="desc",
    )
    assert result == expected


@pytest.mark.parametrize("bad_values", [["secret"], ["-secret"], [""]])
def test_build_order_by_filters_rejects_disallowed_or_empty(bad_values: list[str]) -> None:
    with pytest.raises(ValueError):
        build_order_by_filters(bad_values, None, allowed_fields={"title", "views"})


class _WrappedTextType(TypeDecorator[str]):
    """Custom TypeDecorator delegating to String for filter type-inference coverage."""

    impl = String
    cache_ok = True


class _WrappedGridModel(_GridTestBase):
    """Model exercising TypeDecorator unwrapping and string-backed enums in filter inference."""

    __tablename__ = "grid_wrapped_model"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(_WrappedTextType(80))
    label: Mapped[str] = mapped_column(SAEnum("a", "b", name="label_enum"))


@pytest.mark.parametrize(
    ("operator", "ignore_case", "expected_op"),
    [
        ("startswith", True, "istartswith"),
        ("startswith", False, "startswith"),
        ("endswith", True, "iendswith"),
        ("endswith", False, "endswith"),
    ],
)
def test_build_field_filter_string_prefix_suffix_and_decorator_types(
    operator: Any,
    ignore_case: bool,
    expected_op: str,
) -> None:
    specs = resolve_filter_fields({"slug": {operator}, "label": {"eq"}}, _WrappedGridModel)
    target = next(spec for spec in specs if spec.field_path == "slug")
    built = build_field_filter(target, "pre", ignore_case=ignore_case)
    assert isinstance(built, ComparisonFilter)
    assert built.operator == expected_op
    assert built.value == "pre"
    label_spec = next(spec for spec in specs if spec.field_path == "label")
    assert label_spec.value_type is str

    with pytest.raises(ImproperConfigurationError, match="Expected a SQLAlchemy mapped model"):
        resolve_filter_fields(["name"], dict)


@pytest.mark.parametrize(
    ("sort_fields", "model", "expected_error"),
    [
        (["author.name"], None, None),
        ([""], _GridTestPost, "Invalid sort_fields entry"),
        (["bad name"], _GridTestPost, "Invalid column name"),
        (["unknown.name"], _GridTestPost, "Unknown relationship 'unknown'"),
    ],
)
def test_normalize_sort_fields_validation_and_without_model(
    sort_fields: list[str],
    model: Any,
    expected_error: Optional[str],
) -> None:
    if expected_error is not None:
        with pytest.raises(ImproperConfigurationError, match=expected_error):
            normalize_sort_fields(sort_fields, model=model)
        return
    assert normalize_sort_fields(sort_fields, model=model) == ("author.name",)


@pytest.mark.parametrize(
    ("config", "default_size", "expected"),
    [
        ({}, 20, (20, None)),
        ({}, 25, (25, None)),
        ({"pagination_max_size": None}, 20, (20, None)),
        ({"pagination_max_size": 10}, 20, (10, 10)),
        ({"pagination_max_size": 50}, 20, (20, 50)),
        ({"pagination_size": 10, "pagination_max_size": 50}, 20, (10, 50)),
        ({"pagination_size": 50, "pagination_max_size": 50}, 20, (50, 50)),
    ],
)
def test_resolve_pagination_bounds_valid(
    config: FilterConfig,
    default_size: int,
    expected: tuple[int, Optional[int]],
) -> None:
    assert resolve_pagination_bounds(config, default_size=default_size) == expected


@pytest.mark.parametrize(
    ("config", "match"),
    [
        ({"pagination_max_size": 0}, "pagination_max_size"),
        ({"pagination_max_size": -5}, "pagination_max_size"),
        ({"pagination_max_size": True}, "pagination_max_size"),
        ({"pagination_max_size": False}, "pagination_max_size"),
        ({"pagination_max_size": "10"}, "pagination_max_size"),
        ({"pagination_size": 0}, "pagination_size"),
        ({"pagination_size": -1}, "pagination_size"),
        ({"pagination_size": True}, "pagination_size"),
        ({"pagination_size": False}, "pagination_size"),
        ({"pagination_size": "10"}, "pagination_size"),
        ({"pagination_size": 51, "pagination_max_size": 50}, "cannot exceed"),
    ],
)
def test_resolve_pagination_bounds_invalid(config: dict[str, Any], match: str) -> None:
    with pytest.raises(ImproperConfigurationError, match=match):
        resolve_pagination_bounds(cast("FilterConfig", config))


def test_filter_cache_separates_pagination_max_size_across_frameworks() -> None:
    for factory in _get_framework_filter_factories():
        unbounded = factory({"pagination_type": "limit_offset"})
        capped_10 = factory({"pagination_type": "limit_offset", "pagination_max_size": 10})
        capped_20 = factory({"pagination_type": "limit_offset", "pagination_max_size": 20})
        assert unbounded is not capped_10
        assert capped_10 is not capped_20
        assert capped_10 is factory({"pagination_type": "limit_offset", "pagination_max_size": 10})
