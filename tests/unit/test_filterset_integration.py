"""FilterSet integration through repository and framework public APIs."""

from typing import Annotated, Any, cast
from unittest.mock import MagicMock

import pytest
from sqlalchemy import ForeignKey, create_engine, event, inspect, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, raiseload, relationship, selectinload

from advanced_alchemy.filters import FilterSet, FilterTypes, LimitOffsetFilter, StatementFilter
from advanced_alchemy.repository import SQLAlchemyAsyncRepository, SQLAlchemySyncRepository
from advanced_alchemy.repository.memory import SQLAlchemySyncMockRepository


class IntegrationBase(DeclarativeBase):
    pass


class Customer(IntegrationBase):
    __tablename__ = "filterset_customer"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    orders: Mapped[list["Order"]] = relationship()


class Order(IntegrationBase):
    __tablename__ = "filterset_order"
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey(Customer.id))
    price: Mapped[int]
    items: Mapped[list["LineItem"]] = relationship()


class LineItem(IntegrationBase):
    __tablename__ = "filterset_line_item"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey(Order.id))
    name: Mapped[str]


class Customers(FilterSet[Customer]):
    filter_fields = {"orders.price": {"ge", "le"}, "name": {"eq"}}
    sort_fields = ("id",)
    search_fields = ("name",)
    config = {"pagination_type": "limit_offset", "pagination_size": 1}


class CustomerRepository(SQLAlchemySyncRepository[Customer]):
    pass


def seed() -> list[Customer]:
    return [
        Customer(id=i, name=f"customer{i}", orders=[Order(id=i * 10, price=15), Order(id=i * 10 + 1, price=30)])
        for i in range(1, 4)
    ]


@pytest.fixture
def session() -> Any:
    engine = create_engine("sqlite://")
    IntegrationBase.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all(seed())
        session.commit()
        yield session
    engine.dispose()


def test_native_count_pagination_and_complete_collections(session: Session) -> None:
    repo = CustomerRepository(session=session)
    filters = Customers(orders__price__ge=10, orders__price__le=20, orderBy=["id"], page=2)
    rows, count = repo.get_many_and_count(filters)
    assert count == 3
    assert [row.id for row in rows] == [2]
    assert sorted(order.price for order in rows[0].orders) == [15, 30]
    assert repo.count(filters) == 3
    assert repo.exists(filters)
    assert repo.get_one(filters, id=1).id == 1


def test_auto_loading_batches_and_explicit_override(session: Session) -> None:
    engine = session.get_bind()
    calls = []

    def record(*args: Any) -> None:
        calls.append(1)

    event.listen(engine, "before_cursor_execute", record)
    try:
        filters = Customers(orders__price__ge=10, pageSize=20)
        rows = CustomerRepository(session=session).get_many(filters)
        assert len(rows) == 3
        assert all("orders" not in inspect(row).unloaded for row in rows)
        assert len(calls) == 2
        assert sum(len(row.orders) for row in rows) == 6
        assert len(calls) == 2
        session.expunge_all()
        rows = CustomerRepository(session=session).get_many(filters, load=[raiseload(Customer.orders)])
        assert "orders" in inspect(rows[0]).unloaded
        with pytest.raises(Exception, match="lazy='raise'"):
            _ = rows[0].orders
    finally:
        event.remove(engine, "before_cursor_execute", record)


def test_explicit_loader_criteria_survive(session: Session) -> None:
    rows = CustomerRepository(session=session).get_many(
        Customers(orders__price__ge=10), load=[selectinload(Customer.orders.and_(Order.price > 20))]
    )
    assert [order.price for order in rows[0].orders] == [30]


def test_mock_count_pagination_matches_sql(session: Session) -> None:
    class MockRepository(SQLAlchemySyncMockRepository[Customer]):
        pass

    MockRepository.__database_clear__()
    repo = MockRepository(session=MagicMock(spec=Session))
    try:
        repo.add_many(seed())
        filters = Customers(orders__price__ge=10, orders__price__le=20, orderBy=["id"], page=2)
        rows, count = repo.get_many_and_count(filters)
        assert ([row.id for row in rows], count) == ([2], 3)
    finally:
        MockRepository.__database_clear__()


async def test_async_repository_uses_same_load_and_count() -> None:
    class AsyncRepository(SQLAlchemyAsyncRepository[Customer]):
        pass

    engine = create_async_engine("sqlite+aiosqlite://")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(IntegrationBase.metadata.create_all)
        async with AsyncSession(engine) as session:
            session.add_all(seed())
            await session.commit()
            rows, count = await AsyncRepository(session=session).get_many_and_count(Customers(orders__price__ge=10))
            assert count == 3
            assert len(rows[0].orders) == 2
    finally:
        await engine.dispose()


def test_fastapi_filterset_dependency_parses_dunder_and_openapi() -> None:
    from fastapi import Depends, FastAPI
    from fastapi.testclient import TestClient

    from advanced_alchemy.extensions.fastapi.providers import provide_filters

    dependency = provide_filters(Customers)
    app = FastAPI()

    @app.get("/")
    def endpoint(filters: Annotated[list[FilterSet[Customer]], Depends(dependency)]) -> dict[str, Any]:
        return {
            "count": len(filters),
            "type": type(filters[0]).__name__,
            "pagination": next(f.limit for f in filters[0].to_statement_filters() if isinstance(f, LimitOffsetFilter)),
        }

    with TestClient(app) as client:
        response = client.get("/", params={"orders__price__ge": "10", "pageSize": "2"})
        assert response.status_code == 200, response.text
        assert response.json() == {"count": 1, "type": "Customers", "pagination": 2}
        assert "orders__price__ge" in {
            p["name"] for p in client.get("/openapi.json").json()["paths"]["/"]["get"]["parameters"]
        }
        assert client.get("/", params={"orders__price__ge": "bad"}).status_code == 422


def test_litestar_filterset_dependency_parses_dunder() -> None:
    from litestar import Litestar, get
    from litestar.di import NamedDependency
    from litestar.params import SkipValidation
    from litestar.testing import TestClient

    from advanced_alchemy.extensions.litestar.providers import create_filter_dependencies

    @get("/", sync_to_thread=False)
    def endpoint(filters: NamedDependency[SkipValidation[list[FilterTypes]]]) -> dict[str, Any]:
        return {"type": type(filters[0]).__name__}

    app = Litestar([endpoint], dependencies=create_filter_dependencies(Customers))
    with TestClient(app) as client:
        response = client.get("/", params={"orders__price__ge": "10"})
        assert response.status_code == 200, response.text
        assert response.json() == {"type": "Customers"}
        assert client.get("/", params={"orders__price__ge": "bad"}).status_code == 400


def test_scalar_count_has_no_inferred_loader_options(session: Session) -> None:
    statements = []

    def record(connection: Any, clause: Any, multiparams: Any, params: Any, options: Any) -> None:
        statements.append(clause)

    engine = session.get_bind()
    event.listen(engine, "before_execute", record)
    try:
        assert CustomerRepository(session=session).count(Customers(orders__price__ge=10)) == 3
        assert len(statements) == 1
        assert not getattr(statements[0], "_with_options", ())
    finally:
        event.remove(engine, "before_execute", record)


def test_wrong_model_is_rejected_for_sql_and_mock(session: Session) -> None:
    class Wrong(FilterSet[Order]):
        filter_fields = {"price": {"ge"}}

    class MockRepository(SQLAlchemySyncMockRepository[Customer]):
        pass

    for repo in (CustomerRepository(session=session), MockRepository(session=MagicMock(spec=Session))):
        with pytest.raises(ValueError, match="model does not match"):
            repo.get_many(Wrong(price__ge=10))


def test_mssql_composite_paging_keeps_user_order_first() -> None:
    from sqlalchemy import ForeignKeyConstraint
    from sqlalchemy.dialects.mssql import dialect

    from advanced_alchemy.repository._util import _filterset_loader_options

    class CompositeRoot(IntegrationBase):
        __tablename__ = "filterset_composite_root"
        id_a: Mapped[int] = mapped_column(primary_key=True)
        id_b: Mapped[int] = mapped_column(primary_key=True)
        name: Mapped[str]
        children: Mapped[list["CompositeChild"]] = relationship()

    class CompositeChild(IntegrationBase):
        __tablename__ = "filterset_composite_child"
        id: Mapped[int] = mapped_column(primary_key=True)
        root_a: Mapped[int]
        root_b: Mapped[int]
        score: Mapped[int]
        __table_args__ = (ForeignKeyConstraint(["root_a", "root_b"], [CompositeRoot.id_a, CompositeRoot.id_b]),)

    class CompositeFilters(FilterSet[CompositeRoot]):
        filter_fields = {"children.score": {"ge"}}
        sort_fields = ("name",)

    filters = CompositeFilters(children__score__ge=1, orderBy=["name"])
    statement = select(CompositeRoot)
    for filter_ in filters.to_statement_filters():
        assert isinstance(filter_, StatementFilter)
        statement = filter_.append_to_statement(statement, CompositeRoot)
    statement = LimitOffsetFilter(limit=2, offset=1).append_to_statement(statement, CompositeRoot)
    mssql_dialect = cast("Any", dialect)()
    statement = _filterset_loader_options(statement, [filters], mssql_dialect, paginated=True)
    compiled = str(statement.compile(dialect=mssql_dialect))
    assert (
        "ORDER BY filterset_composite_root.name ASC, filterset_composite_root.id_a, filterset_composite_root.id_b"
        in compiled
    )
    strategies = [
        getattr(entry, "strategy", ())
        for option in getattr(statement, "_with_options", ())
        for entry in getattr(option, "context", ())
    ]
    assert (("lazy", "subquery"),) in strategies


def test_service_group_filterset_dependency_scopes_members() -> None:
    from litestar import Litestar, get
    from litestar.di import NamedDependency
    from litestar.params import SkipValidation
    from litestar.testing import TestClient

    from advanced_alchemy.extensions.litestar.providers import create_service_dependencies
    from advanced_alchemy.service import ServiceGroup, SQLAlchemySyncRepositoryService

    class CustomerService(SQLAlchemySyncRepositoryService[Customer]):
        pass

    class Group(ServiceGroup):
        customers: CustomerService

    dependencies = create_service_dependencies(Group, "group", filters={"customers": Customers})

    @get("/", sync_to_thread=False)
    def endpoint(customers_filters: NamedDependency[SkipValidation[list[FilterSet[Customer]]]]) -> dict[str, Any]:
        return {"type": type(customers_filters[0]).__name__}

    with TestClient(
        Litestar([endpoint], dependencies=dependencies, signature_namespace={"Session": Session, "Group": Group})
    ) as client:
        response = client.get("/", params={"customers_orders__price__ge": "10"})
        assert response.status_code == 200, response.text
        assert response.json() == {"type": "Customers"}
        assert client.get("/", params={"customersOrderBy": "unknown"}).status_code == 400
        assert client.get("/", params={"customersPageSize": "0"}).status_code == 400
        parameters = client.get("/schema/openapi.json").json()["paths"]["/"]["get"]["parameters"]
        aliases = {parameter["name"] for parameter in parameters}
        assert {"customersOrderBy", "customersSearchString", "customersPageSize"} <= aliases


def test_nested_wildcard_overrides_inferred_descendants(session: Session) -> None:
    class NestedFilters(FilterSet[Customer]):
        filter_fields = {"orders.items.name": {"eq"}}

    session.add(LineItem(id=1, order_id=10, name="widget"))
    session.commit()
    rows = CustomerRepository(session=session).get_many(
        NestedFilters(orders__items__name__eq="widget"), load=[selectinload(Customer.orders).raiseload("*")]
    )
    assert len(rows) == 1
    assert "orders" not in inspect(rows[0]).unloaded
    with pytest.raises(Exception, match="lazy='raise'"):
        _ = rows[0].orders[0].items


@pytest.mark.parametrize("values", [{"name__eq": "customer1"}, {"orders__price__ge": 10}])
def test_mssql_default_pagination_has_primary_key_order(values: dict[str, Any]) -> None:
    from sqlalchemy.dialects.mssql import dialect

    from advanced_alchemy.repository._util import _filterset_loader_options

    filters = Customers(**values)
    statement = select(Customer)
    for filter_ in filters.to_statement_filters():
        assert isinstance(filter_, StatementFilter)
        statement = filter_.append_to_statement(statement, Customer)
    mssql_dialect = cast("Any", dialect)()
    statement = _filterset_loader_options(statement, [filters], mssql_dialect, paginated=True)
    compiled = str(statement.compile(dialect=mssql_dialect))
    assert "ROW_NUMBER() OVER (ORDER BY filterset_customer.id)" in compiled


def _extract_numeric_bounds(schema: dict[str, Any]) -> tuple[Any, Any]:
    if "minimum" in schema or "maximum" in schema:
        return schema.get("minimum"), schema.get("maximum")
    for key in ("anyOf", "oneOf"):
        for variant in schema.get(key, []):
            if "minimum" in variant or "maximum" in variant:
                return variant.get("minimum"), variant.get("maximum")
    return None, None


def test_filterset_pagination_max_size_litestar_and_fastapi() -> None:
    from fastapi import Depends, FastAPI
    from fastapi.testclient import TestClient as FastAPITestClient
    from litestar import Litestar, get
    from litestar.di import NamedDependency
    from litestar.openapi.config import OpenAPIConfig
    from litestar.params import SkipValidation
    from litestar.testing import TestClient as LitestarTestClient

    from advanced_alchemy.extensions.fastapi.providers import provide_filters
    from advanced_alchemy.extensions.litestar.providers import create_filter_dependencies

    class CappedCustomers(FilterSet[Customer]):
        filter_fields = {"name": {"eq"}}
        config = {"pagination_type": "limit_offset", "pagination_max_size": 5}

    fastapi_dep = provide_filters(CappedCustomers)
    fastapi_app = FastAPI()

    @fastapi_app.get("/")
    def fastapi_endpoint(filters: Annotated[list[FilterSet[Customer]], Depends(fastapi_dep)]) -> dict[str, int]:
        limit = next(f.limit for f in filters[0].to_statement_filters() if isinstance(f, LimitOffsetFilter))
        return {"limit": limit}

    with FastAPITestClient(fastapi_app) as client:
        assert client.get("/", params={"pageSize": "5"}).json() == {"limit": 5}
        assert client.get("/").json() == {"limit": 5}
        assert client.get("/", params={"pageSize": "6"}).status_code == 422
        assert client.get("/", params={"pageSize": "0"}).status_code == 422
        assert client.get("/", params={"currentPage": "0"}).status_code == 422
        params = {p["name"]: p["schema"] for p in client.get("/openapi.json").json()["paths"]["/"]["get"]["parameters"]}
        assert _extract_numeric_bounds(params["pageSize"]) == (1, 5)
        assert _extract_numeric_bounds(params["currentPage"]) == (1, None)

    @get("/", sync_to_thread=False)
    def litestar_endpoint(filters: NamedDependency[SkipValidation[list[FilterTypes]]]) -> dict[str, int]:
        limit = next(f.limit for f in filters[0].to_statement_filters() if isinstance(f, LimitOffsetFilter))  # type: ignore[union-attr]
        return {"limit": limit}

    litestar_app = Litestar(
        [litestar_endpoint],
        dependencies=create_filter_dependencies(CappedCustomers),
        openapi_config=OpenAPIConfig(title="Test", version="1.0.0", path="/schema"),
    )
    with LitestarTestClient(litestar_app) as litestar_client:
        assert litestar_client.get("/", params={"pageSize": "5"}).json() == {"limit": 5}
        assert litestar_client.get("/").json() == {"limit": 5}
        assert litestar_client.get("/", params={"pageSize": "6"}).status_code == 400
        assert litestar_client.get("/", params={"pageSize": "0"}).status_code == 400
        assert litestar_client.get("/", params={"currentPage": "0"}).status_code == 400
        params = {
            p["name"]: p["schema"]
            for p in litestar_client.get("/schema/openapi.json").json()["paths"]["/"]["get"]["parameters"]
        }
        assert _extract_numeric_bounds(params["pageSize"]) == (1, 5)
        assert _extract_numeric_bounds(params["currentPage"]) == (1, None)
