"""Cursor pagination through Litestar filter dependencies."""

from collections.abc import Iterator
from typing import Any, Optional

import msgspec
import pytest
from litestar import Litestar, get
from litestar.di import NamedDependency
from litestar.params import SkipValidation
from litestar.testing import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column
from sqlalchemy.pool import StaticPool

from advanced_alchemy.exceptions import InvalidCursorError, RepositoryError
from advanced_alchemy.extensions.litestar import SQLAlchemyPlugin, SQLAlchemySyncConfig
from advanced_alchemy.extensions.litestar.exception_handler import exception_to_http_response
from advanced_alchemy.extensions.litestar.plugins.init.plugin import signature_namespace_values
from advanced_alchemy.extensions.litestar.providers import DependencyDefaults, create_filter_dependencies
from advanced_alchemy.filters import CursorFilter, CursorKey, FilterSet, FilterTypes
from advanced_alchemy.repository import SQLAlchemySyncRepository
from advanced_alchemy.service import CursorPagination, ResultConverter
from advanced_alchemy.utils.dependencies import FilterConfig


class LitestarCursorBase(DeclarativeBase):
    pass


class Widget(LitestarCursorBase):
    __tablename__ = "litestar_cursor_widget"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    stock: Mapped[int]
    secret_code: Mapped[str]


class WidgetOut(msgspec.Struct):
    id: int
    name: str
    stock: int


class WidgetRepository(SQLAlchemySyncRepository[Widget]):
    pass


class Widgets(FilterSet[Widget]):
    filter_fields = {"stock": {"ge"}}
    sort_fields = ("name", "stock")
    config = {"pagination_type": "cursor", "pagination_size": 4}


CONFIG: FilterConfig = {
    "pagination_type": "cursor",
    "pagination_size": 5,
    "pagination_max_size": 10,
    "sort_field": "stock",
    "sort_order": "desc",
    "sort_fields": ["name", "stock"],
}


@pytest.fixture(scope="module")
def db() -> Iterator[Session]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    LitestarCursorBase.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all(Widget(id=i, name=f"w{i % 4}", stock=i % 6, secret_code=f"code-{i}") for i in range(1, 24))
        session.commit()
        yield session
    engine.dispose()


@pytest.fixture(autouse=True)
def cursor_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.setenv("ADVANCED_ALCHEMY_PAGINATION_CURSOR_SECRET", "environment-secret")


def make_client(db: Session, config: Any) -> TestClient[Any]:
    @get("/widgets-named", sync_to_thread=False, dependencies=create_filter_dependencies(config))
    def list_named(filters: NamedDependency[SkipValidation[list[FilterTypes]]]) -> CursorPagination[WidgetOut]:
        rows = WidgetRepository(session=db).get_many(*filters)
        return ResultConverter().to_schema(rows, filters=filters, schema_type=WidgetOut, pagination_type="cursor")

    return TestClient(Litestar([list_named], exception_handlers={RepositoryError: exception_to_http_response}))


def walk(client: TestClient[Any], path: str, params: dict[str, Any]) -> tuple[list[int], list[dict[str, Any]]]:
    ids: list[int] = []
    pages: list[dict[str, Any]] = []
    cursor: Optional[str] = None
    while True:
        response = client.get(path, params={**params, **({"cursor": cursor} if cursor else {})})
        assert response.status_code == 200, response.text
        page = response.json()
        pages.append(page)
        ids.extend(item["id"] for item in page["items"])
        if not page["has_next"]:
            return ids, pages
        cursor = page["next_cursor"]


def test_walk_forward_and_backward_over_http(db: Session) -> None:
    with make_client(db, CONFIG) as client:
        ids, pages = walk(client, "/widgets-named", {"orderBy": ["-stock", "name"], "pageSize": 4})
        backward: list[int] = [item["id"] for item in pages[-1]["items"]]
        cursor = pages[-1]["previous_cursor"]
        while cursor:
            page = client.get(
                "/widgets-named", params={"orderBy": ["-stock", "name"], "pageSize": 4, "cursor": cursor}
            ).json()
            backward = [item["id"] for item in page["items"]] + backward
            cursor = page["previous_cursor"]

    widgets = WidgetRepository(session=db).get_many()
    expected = [w.id for w in sorted(widgets, key=lambda w: (-w.stock, w.name, w.id))]
    assert ids == backward == expected
    assert set(pages[0]) == {"items", "limit", "next_cursor", "previous_cursor", "has_next", "has_previous"}
    assert "secret_code" not in pages[0]["items"][0]


def test_default_ordering_uses_configured_sort_field(db: Session) -> None:
    with make_client(db, CONFIG) as client:
        ids, _ = walk(client, "/widgets-named", {})

    widgets = WidgetRepository(session=db).get_many()
    assert ids == [w.id for w in sorted(widgets, key=lambda w: (-w.stock, -w.id))]


@pytest.mark.parametrize(
    "params",
    [
        {"cursor": "not-a-token!"},
        {"pageSize": 11},
        {"pageSize": 0},
        {"orderBy": "secret_code"},
    ],
)
def test_invalid_requests_return_400(db: Session, params: dict[str, Any]) -> None:
    with make_client(db, CONFIG) as client:
        response = client.get("/widgets-named", params=params)

    assert response.status_code == 400, response.text


def test_token_from_another_ordering_returns_400(db: Session) -> None:
    with make_client(db, CONFIG) as client:
        token = client.get("/widgets-named", params={"orderBy": "name"}).json()["next_cursor"]
        response = client.get("/widgets-named", params={"orderBy": "-stock", "cursor": token})

    assert response.status_code == 400
    assert "ordering mismatch" in response.text


def test_tampered_signed_token_returns_400(db: Session) -> None:
    config: FilterConfig = {**CONFIG, "pagination_cursor_secret": "server-secret"}
    with make_client(db, config) as client:
        token = client.get("/widgets-named").json()["next_cursor"]
        body, signature = token.split(".")
        assert client.get("/widgets-named", params={"cursor": token}).status_code == 200
        response = client.get("/widgets-named", params={"cursor": f"{body}.{signature[::-1]}"})

    assert response.status_code == 400


def test_openapi_exposes_bounded_cursor_parameters(db: Session) -> None:
    with make_client(db, CONFIG) as client:
        schema = client.get("/schema/openapi.json").json()

    parameters = {p["name"]: p for p in schema["paths"]["/widgets-named"]["get"]["parameters"]}
    assert set(parameters) == {"cursor", "pageSize", "orderBy", "sortOrder"}
    assert parameters["pageSize"]["schema"]["maximum"] == 10
    assert "currentPage" not in parameters


def test_cursor_without_sorting_exposes_only_cursor_and_page_size(db: Session) -> None:
    with make_client(db, {"pagination_type": "cursor"}) as client:
        schema = client.get("/schema/openapi.json").json()
        ids, _ = walk(client, "/widgets-named", {"pageSize": 7})

    parameters = {p["name"] for p in schema["paths"]["/widgets-named"]["get"]["parameters"]}
    assert parameters == {"cursor", "pageSize"}
    assert ids == sorted(ids)
    assert len(ids) == 23


def test_aliases_and_prefix_apply_to_cursor_parameters(db: Session) -> None:
    config: FilterConfig = {**CONFIG, "alias_generator": "snake_case"}
    dependencies = create_filter_dependencies(config, DependencyDefaults(prefix="widgets"))

    @get("/widgets-named", sync_to_thread=False, dependencies=dependencies)
    def endpoint(widgets_filters: NamedDependency[SkipValidation[list[FilterTypes]]]) -> CursorPagination[WidgetOut]:
        rows = WidgetRepository(session=db).get_many(*widgets_filters)
        return ResultConverter().to_schema(
            rows, filters=widgets_filters, schema_type=WidgetOut, pagination_type="cursor"
        )

    with TestClient(Litestar([endpoint])) as client:
        schema = client.get("/schema/openapi.json").json()
        response = client.get("/widgets-named", params={"widgets_page_size": 2})

    parameters = {p["name"] for p in schema["paths"]["/widgets-named"]["get"]["parameters"]}
    assert {"widgets_cursor", "widgets_page_size", "widgets_order_by", "widgets_sort_order"} <= parameters
    assert response.status_code == 200
    assert len(response.json()["items"]) == 2


def test_filterset_cursor_parameters(db: Session) -> None:
    @get("/", sync_to_thread=False, dependencies=create_filter_dependencies(Widgets))
    def endpoint(filters: NamedDependency[SkipValidation[list[FilterTypes]]]) -> CursorPagination[WidgetOut]:
        rows = WidgetRepository(session=db).get_many(*filters)
        return ResultConverter().to_schema(rows, filters=filters, schema_type=WidgetOut, pagination_type="cursor")

    with TestClient(Litestar([endpoint])) as client:
        schema = client.get("/schema/openapi.json").json()
        page = client.get("/").json()
        assert client.get("/", params={"cursor": "bad!"}).status_code == 400

    assert (len(page["items"]), page["has_next"]) == (4, True)

    parameters = {p["name"] for p in schema["paths"]["/"]["get"]["parameters"]}
    assert {"cursor", "pageSize", "orderBy"} <= parameters
    assert "currentPage" not in parameters


def test_invalid_cursor_raised_while_querying_returns_400() -> None:
    @get("/", sync_to_thread=False)
    def endpoint() -> None:
        msg = "Invalid pagination cursor: ordering mismatch"
        raise InvalidCursorError(msg)

    app = Litestar([endpoint], exception_handlers={RepositoryError: exception_to_http_response})
    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 400
    assert "ordering mismatch" in response.text


def test_signature_namespace_includes_cursor_types() -> None:
    assert signature_namespace_values["CursorFilter"] is CursorFilter
    assert signature_namespace_values["CursorKey"] is CursorKey
    assert signature_namespace_values["CursorPagination"] is CursorPagination


def test_prefixed_defaults_keep_custom_cursor_key() -> None:
    from advanced_alchemy.extensions.litestar.providers import _with_dep_defaults_prefix

    custom = DependencyDefaults(cursor_filter_key="page_token")
    scoped = _with_dep_defaults_prefix(custom, "orders")
    default_scoped = _with_dep_defaults_prefix(DependencyDefaults(), "orders")

    assert scoped.CURSOR_FILTER_DEPENDENCY_KEY == "orders_page_token"
    assert default_scoped.CURSOR_FILTER_DEPENDENCY_KEY == "orders_cursor_filter"


def plugin_client(db: Session, config: Any, **config_options: Any) -> TestClient[Any]:
    @get("/widgets", sync_to_thread=False, dependencies=create_filter_dependencies(config))
    def list_widgets(filters: NamedDependency[SkipValidation[list[FilterTypes]]]) -> CursorPagination[WidgetOut]:
        rows = WidgetRepository(session=db).get_many(*filters)
        return ResultConverter().to_schema(rows, filters=filters, schema_type=WidgetOut, pagination_type="cursor")

    plugin = SQLAlchemyPlugin(SQLAlchemySyncConfig(connection_string="sqlite://", **config_options))
    return TestClient(Litestar([list_widgets], plugins=[plugin], debug=True))


@pytest.mark.parametrize(("config", "keys", "limit"), [(CONFIG, [("stock", "desc")], 5), (Widgets, [], 4)])
def test_config_secret_signs_tokens_for_every_filter_dependency(
    db: Session, monkeypatch: pytest.MonkeyPatch, config: Any, keys: Any, limit: int
) -> None:
    monkeypatch.delenv("ADVANCED_ALCHEMY_PAGINATION_CURSOR_SECRET")

    with plugin_client(db, config, pagination_cursor_secret="config-secret") as client:
        token = client.get("/widgets").json()["next_cursor"]
        following = client.get("/widgets", params={"cursor": token})

    assert following.status_code == 200
    assert CursorFilter(keys, limit, token, "config-secret").cursor == token
    with pytest.raises(InvalidCursorError, match="signature"):
        CursorFilter(keys, limit, token, "environment-secret")


def test_filter_configuration_secret_overrides_the_config_secret(db: Session) -> None:
    config: FilterConfig = {**CONFIG, "pagination_cursor_secret": "route-secret"}

    with plugin_client(db, config, pagination_cursor_secret="config-secret") as client:
        token = client.get("/widgets").json()["next_cursor"]

    assert CursorFilter([("stock", "desc")], 5, token, "route-secret").cursor == token


@pytest.mark.parametrize("config", [CONFIG, Widgets])
def test_cursor_pagination_without_a_secret_is_a_configuration_error(
    db: Session, monkeypatch: pytest.MonkeyPatch, config: Any
) -> None:
    monkeypatch.delenv("ADVANCED_ALCHEMY_PAGINATION_CURSOR_SECRET")

    with plugin_client(db, config) as client:
        response = client.get("/widgets")

    assert response.status_code == 500
    assert "Cursor pagination requires a secret" in response.text
