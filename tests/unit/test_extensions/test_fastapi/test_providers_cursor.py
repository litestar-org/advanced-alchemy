"""Cursor pagination through FastAPI filter dependencies."""

from collections.abc import Iterator
from typing import Annotated, Any, Optional

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column
from sqlalchemy.pool import StaticPool

from advanced_alchemy.exceptions import ImproperConfigurationError, InvalidCursorError
from advanced_alchemy.extensions.fastapi import AdvancedAlchemy, SQLAlchemySyncConfig
from advanced_alchemy.extensions.fastapi.providers import provide_filters
from advanced_alchemy.extensions.litestar.providers import create_filter_dependencies
from advanced_alchemy.filters import CursorFilter, FilterSet, FilterTypes
from advanced_alchemy.filters._cursor import encode_cursor, order_fingerprint
from advanced_alchemy.repository import SQLAlchemySyncRepository
from advanced_alchemy.service import CursorPagination, ResultConverter
from advanced_alchemy.utils.dependencies import FilterConfig


class FastAPICursorBase(DeclarativeBase):
    pass


class Gadget(FastAPICursorBase):
    __tablename__ = "fastapi_cursor_gadget"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    price: Mapped[int]


class GadgetOut(BaseModel):
    id: int
    name: str
    price: int


class GadgetRepository(SQLAlchemySyncRepository[Gadget]):
    pass


class Gadgets(FilterSet[Gadget]):
    sort_fields = ("price",)
    config = {"pagination_type": "cursor", "pagination_size": 3}


CONFIG: FilterConfig = {
    "pagination_type": "cursor",
    "pagination_size": 4,
    "pagination_max_size": 8,
    "sort_field": "price",
    "sort_fields": ["name", "price"],
}


@pytest.fixture(scope="module")
def db() -> Iterator[Session]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    FastAPICursorBase.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all(Gadget(id=i, name=f"g{i % 3}", price=i % 5) for i in range(1, 20))
        session.commit()
        yield session
    engine.dispose()


@pytest.fixture(autouse=True)
def cursor_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.setenv("ADVANCED_ALCHEMY_PAGINATION_CURSOR_SECRET", "environment-secret")


def make_client(db: Session, config: Any) -> TestClient:
    app = FastAPI()
    dependency = provide_filters(config)

    @app.get("/gadgets")
    def list_gadgets(filters: Annotated[list[FilterTypes], Depends(dependency)]) -> CursorPagination[GadgetOut]:
        rows = GadgetRepository(session=db).get_many(*filters)
        return ResultConverter().to_schema(rows, filters=filters, schema_type=GadgetOut, pagination_type="cursor")

    return TestClient(app)


def walk(client: TestClient, params: dict[str, Any]) -> list[int]:
    ids: list[int] = []
    cursor: Optional[str] = None
    while True:
        response = client.get("/gadgets", params={**params, **({"cursor": cursor} if cursor else {})})
        assert response.status_code == 200, response.text
        page = response.json()
        ids.extend(item["id"] for item in page["items"])
        if not page["has_next"]:
            return ids
        cursor = page["next_cursor"]


def test_walk_over_http(db: Session) -> None:
    with make_client(db, CONFIG) as client:
        ids = walk(client, {"orderBy": ["-price", "name"], "pageSize": 5})

    gadgets = GadgetRepository(session=db).get_many()
    assert ids == [g.id for g in sorted(gadgets, key=lambda g: (-g.price, g.name, g.id))]


@pytest.mark.parametrize(
    ("params", "loc"),
    [
        ({"cursor": "not-a-token!"}, "cursor"),
        ({"orderBy": "id; drop table"}, "orderBy"),
        ({"pageSize": 9}, "pageSize"),
        ({"pageSize": 0}, "pageSize"),
    ],
)
def test_invalid_requests_return_422_at_the_parameter(db: Session, params: dict[str, Any], loc: str) -> None:
    with make_client(db, CONFIG) as client:
        response = client.get("/gadgets", params=params)

    assert response.status_code == 422, response.text
    assert response.json()["detail"][0]["loc"] == ["query", loc]


def test_token_from_another_ordering_returns_422(db: Session) -> None:
    with make_client(db, CONFIG) as client:
        token = client.get("/gadgets", params={"orderBy": "name"}).json()["next_cursor"]
        response = client.get("/gadgets", params={"orderBy": "price", "cursor": token})

    assert response.status_code == 422
    assert "ordering mismatch" in response.text


def test_openapi_parameters_match_litestar(db: Session) -> None:
    from litestar import Litestar, get
    from litestar.di import NamedDependency
    from litestar.params import SkipValidation
    from litestar.testing import TestClient as LitestarClient

    with make_client(db, CONFIG) as client:
        fastapi_params = {
            p["name"]: p for p in client.get("/openapi.json").json()["paths"]["/gadgets"]["get"]["parameters"]
        }

    @get("/gadgets", sync_to_thread=False, dependencies=create_filter_dependencies(CONFIG))
    def endpoint(filters: NamedDependency[SkipValidation[list[FilterTypes]]]) -> None:
        return None

    with LitestarClient(Litestar([endpoint])) as litestar_client:
        litestar_params = {
            p["name"]
            for p in litestar_client.get("/schema/openapi.json").json()["paths"]["/gadgets"]["get"]["parameters"]
        }

    assert set(fastapi_params) == litestar_params == {"cursor", "pageSize", "orderBy", "sortOrder"}
    assert fastapi_params["pageSize"]["schema"]["maximum"] == 8


def test_cursor_without_sorting_exposes_only_cursor_and_page_size(db: Session) -> None:
    with make_client(db, {"pagination_type": "cursor"}) as client:
        params = {p["name"] for p in client.get("/openapi.json").json()["paths"]["/gadgets"]["get"]["parameters"]}
        ids = walk(client, {"pageSize": 6})

    assert params == {"cursor", "pageSize"}
    assert ids == list(range(1, 20))


def test_filterset_cursor_parameter(db: Session) -> None:
    app = FastAPI()
    dependency = provide_filters(Gadgets)

    @app.get("/")
    def endpoint(filters: Annotated[list[FilterSet[Any]], Depends(dependency)]) -> dict[str, int]:
        return {"rows": len(GadgetRepository(session=db).get_many(*filters))}

    with TestClient(app) as client:
        params = {p["name"] for p in client.get("/openapi.json").json()["paths"]["/"]["get"]["parameters"]}
        ok = client.get("/")
        bad = client.get("/", params={"cursor": "bad!"})

    assert {"cursor", "pageSize", "orderBy"} <= params
    assert "currentPage" not in params
    assert ok.json() == {"rows": 4}
    assert bad.status_code == 422


def extension_client(db: Session, config: Any, **config_options: Any) -> TestClient:
    app = FastAPI()
    AdvancedAlchemy(SQLAlchemySyncConfig(connection_string="sqlite://", **config_options), app=app)
    dependency = provide_filters(config)

    @app.get("/gadgets")
    def list_gadgets(filters: Annotated[list[FilterTypes], Depends(dependency)]) -> CursorPagination[GadgetOut]:
        rows = GadgetRepository(session=db).get_many(*filters)
        return ResultConverter().to_schema(rows, filters=filters, schema_type=GadgetOut, pagination_type="cursor")

    return TestClient(app)


@pytest.mark.parametrize(("config", "keys", "limit"), [(CONFIG, [("price", "desc")], 4), (Gadgets, [], 3)])
def test_config_secret_signs_tokens_for_every_filter_dependency(
    db: Session, monkeypatch: pytest.MonkeyPatch, config: Any, keys: Any, limit: int
) -> None:
    monkeypatch.delenv("ADVANCED_ALCHEMY_PAGINATION_CURSOR_SECRET")

    with extension_client(db, config, pagination_cursor_secret="config-secret") as client:
        token = client.get("/gadgets").json()["next_cursor"]
        following = client.get("/gadgets", params={"cursor": token})

    assert following.status_code == 200
    assert CursorFilter(keys, limit, token, "config-secret").cursor == token
    with pytest.raises(InvalidCursorError, match="signature"):
        CursorFilter(keys, limit, token, "environment-secret")


@pytest.mark.parametrize("config", [CONFIG, Gadgets])
def test_cursor_pagination_without_a_secret_is_a_configuration_error(
    db: Session, monkeypatch: pytest.MonkeyPatch, config: Any
) -> None:
    monkeypatch.delenv("ADVANCED_ALCHEMY_PAGINATION_CURSOR_SECRET")

    with extension_client(db, config) as client, pytest.raises(ImproperConfigurationError, match="requires a secret"):
        client.get("/gadgets")


def test_token_values_that_do_not_fit_the_columns_return_422(db: Session) -> None:
    token = encode_cursor(
        ["not-a-price", 1], order_fingerprint([("price", "desc", None)]), secret=b"environment-secret"
    )

    with extension_client(db, CONFIG) as client:
        response = client.get("/gadgets", params={"cursor": token})

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["query", "cursor"]
