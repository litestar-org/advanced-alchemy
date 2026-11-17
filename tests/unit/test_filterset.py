"""Native FilterSet query contracts."""

from typing import Optional, Union

import pytest
from sqlalchemy import ColumnElement, ForeignKey, create_engine, func, select
from sqlalchemy.ext.associationproxy import AssociationProxy, association_proxy
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship

from advanced_alchemy.exceptions import ImproperConfigurationError
from advanced_alchemy.filters import ComparisonFilter, FilterSet, LimitOffsetFilter, RelationshipFilter


class Base(DeclarativeBase):
    pass


class Customer(Base):
    __tablename__ = "filterset_customer"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    orders: Mapped[list["Order"]] = relationship()
    order_statuses: AssociationProxy[list[str]] = association_proxy("orders", "status")


class Order(Base):
    __tablename__ = "filterset_order"
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey(Customer.id))
    status: Mapped[str]
    price: Mapped[int]
    active: Mapped[bool] = mapped_column(default=True)
    items: Mapped[list["Item"]] = relationship()


class Item(Base):
    __tablename__ = "filterset_item"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey(Order.id))
    price: Mapped[int]


class CustomerFilters(FilterSet[Customer]):
    filter_fields = {"orders.status": {"eq"}, "orders.price": {"ge", "le"}, "name": {"contains"}}
    sort_fields = {"name"}
    search_fields = {"name", "orders.status"}

    def filter_named(self, value: str) -> ComparisonFilter:
        return ComparisonFilter(field_name="name", operator="eq", value=value)


def test_native_definition_and_parameters() -> None:
    assert CustomerFilters.model_type is Customer
    assert {s.param_name for s in CustomerFilters.parameter_specs()} >= {
        "orders__price__ge",
        "orders__price__le",
        "named",
    }
    assert CustomerFilters().to_statement_filters() == []
    with pytest.raises(ValueError, match="Unknown"):
        CustomerFilters(name__typo="x")


def test_independent_fields_and_grouped_range() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all(
            [
                Customer(
                    id=1,
                    name="outside",
                    orders=[Order(id=1, status="paid", price=5), Order(id=2, status="unpaid", price=30)],
                ),
                Customer(
                    id=2,
                    name="inside",
                    orders=[Order(id=3, status="paid", price=5), Order(id=4, status="unpaid", price=15)],
                ),
            ]
        )
        session.commit()
        filters = CustomerFilters(orders__status__eq="paid", orders__price__ge=10, orders__price__le=20)
        stmt = select(Customer)
        for filter_ in filters.to_statement_filters():
            stmt = filter_.append_to_statement(stmt, Customer)
        assert [v.id for v in session.scalars(stmt)] == [2]
        assert len(filters.load) == 1
    engine.dispose()


def test_custom_and_search_filters() -> None:
    assert CustomerFilters(named="bob").to_statement_filters()[0].value == "bob"
    assert "EXISTS" in str(CustomerFilters(search="paid").append_to_statement(select(Customer), Customer))


def test_invalid_declared_path() -> None:
    with pytest.raises(ImproperConfigurationError):

        class Bad(FilterSet[Customer]):
            filter_fields = {"orders.no_such_field": {"eq"}}

        Bad.parameter_specs()


def test_explicit_pagination_and_sort() -> None:
    class Paged(CustomerFilters):
        config = {"pagination_type": "limit_offset", "pagination_size": 10}

    filters = Paged(page=2, orderBy="-name").to_statement_filters()
    page = next(f for f in filters if isinstance(f, LimitOffsetFilter))
    assert (page.offset, page.limit) == (10, 10)
    with pytest.raises(ValueError, match="sort"):
        Paged(orderBy="orders__price").to_statement_filters()


def test_deep_bounds_and_independent_shared_prefixes() -> None:
    class Deep(FilterSet[Customer]):
        filter_fields = {"orders.status": {"eq"}, "orders.items.price": {"ge", "le"}}

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all(
            [
                Customer(
                    id=1,
                    name="outside",
                    orders=[Order(id=1, status="paid", price=0, items=[Item(id=1, price=5), Item(id=2, price=30)])],
                ),
                Customer(
                    id=2,
                    name="inside",
                    orders=[
                        Order(id=2, status="paid", price=0, items=[]),
                        Order(id=3, status="unpaid", price=0, items=[Item(id=3, price=15)]),
                    ],
                ),
            ]
        )
        session.commit()
        filters = Deep(orders__status__eq="paid", orders__items__price__ge=10, orders__items__price__le=20)
        assert [v.id for v in session.scalars(filters.append_to_statement(select(Customer), Customer))] == [2]
        assert ("orders", "items") in filters._active_relationship_paths()
    engine.dispose()


def test_proxy_alias_and_bad_suffix() -> None:
    class Proxy(FilterSet[Customer]):
        filter_fields = {"order_statuses": {"eq"}}

    spec = Proxy.parameter_specs()[0]
    assert (spec.param_name, spec.rel_path, spec.leaf_field) == ("order_statuses__eq", ("orders",), "status")
    assert isinstance(Proxy(order_statuses__eq="paid").to_statement_filters()[0], RelationshipFilter)
    with pytest.raises(ImproperConfigurationError):

        class Bad(FilterSet[Customer]):
            filter_fields = {"order_statuses.typo": {"eq"}}

        Bad.parameter_specs()


def test_false_zero_and_hook_none() -> None:
    class Typed(FilterSet[Order]):
        filter_fields = {"active": {"eq"}, "price": {"ge"}}

        def filter_enabled(self, value: bool) -> None:
            return None

    filters = Typed(active__eq=False, price__ge=0, enabled=False).to_statement_filters()
    assert [f.value for f in filters] == [False, 0]


def test_auto_loading_can_be_disabled() -> None:
    class NoLoad(CustomerFilters):
        auto_load = False

    assert NoLoad(orders__status__eq="paid").load == []


def test_explicit_model_and_string_search_configuration() -> None:
    class Explicit(FilterSet):
        model_type = Customer
        config = {"search": "name"}

    assert Explicit(search="bob").to_statement_filters()


def test_scalar_selects_do_not_get_entity_loading_options() -> None:
    filters = CustomerFilters(orders__status__eq="paid")
    assert "EXISTS" in str(filters.append_to_statement(select(Customer.id), Customer))
    assert "count" in str(filters.append_to_statement(select(func.count(Customer.id)), Customer))


def test_custom_hook_compiles_once() -> None:
    calls = []

    class Hook(FilterSet[Customer]):
        def filter_name(self, value: str) -> ComparisonFilter:
            calls.append(value)
            return ComparisonFilter(field_name="name", operator="eq", value=value)

    value = Hook(name="alice")
    value.to_statement_filters()
    value.to_statement_filters()
    assert calls == ["alice"]


def test_default_related_ordering_infers_loading() -> None:
    class Related(FilterSet[Customer]):
        sort_fields = {"orders.status"}

    with pytest.raises(ImproperConfigurationError):
        Related()

    class Ordered(FilterSet[Order]):
        sort_fields = {"customer.name"}
        config = {"sort_field": "customer.name"}

    Order.customer = relationship(Customer, overlaps="orders")
    filters = Ordered()
    assert ("customer",) in filters._active_relationship_paths()
    assert len(filters.load) == 1


def test_invalid_configuration_and_custom_results() -> None:
    with pytest.raises(ImproperConfigurationError, match="mapped model"):
        FilterSet()
    with pytest.raises(ImproperConfigurationError, match="Invalid field path"):

        class BadPath(FilterSet[Customer]):
            filter_fields = {"orders..status": {"eq"}}

        BadPath()
    with pytest.raises(ImproperConfigurationError, match="one typed value"):

        class BadHook(FilterSet[Customer]):
            def filter_bad(self) -> None:
                return None

        BadHook()
    with pytest.raises(ImproperConfigurationError, match="annotate"):

        class Untyped(FilterSet[Customer]):
            def filter_bad(self, value) -> None:  # type: ignore[no-untyped-def]
                return None

        Untyped()
    with pytest.raises(ValueError, match="must return"):

        class WrongReturn(FilterSet[Customer]):
            def filter_bad(self, value: bool) -> bool:
                return value

        WrongReturn(bad=True)


def test_custom_sql_and_class_pagination_options() -> None:
    class SQL(FilterSet[Customer]):
        pagination_type = "limit_offset"
        pagination_size = 5

        def filter_name(self, value: str) -> ColumnElement[bool]:
            return Customer.name == value

    assert "name" in str(SQL(name="alice").append_to_statement(select(Customer), Customer))
    with pytest.raises(ValueError, match="positive"):
        SQL(page=0)
    with pytest.raises(ValueError, match="No sort"):
        SQL(orderBy=[])
    with pytest.raises(ValueError, match="does not match"):
        SQL().append_to_statement(select(Order), Order)


@pytest.mark.parametrize("default", [["name"], {"name"}])
def test_default_sort_shorthands(default: Union[list[str], set[str]]) -> None:
    class DefaultSort(FilterSet[Customer]):
        config = {"sort_field": default}

    filter_ = DefaultSort().to_statement_filters()[0]
    assert filter_.field_name == "name"
    assert filter_.sort_order == "desc"


def test_pagination_max_size_config_and_class_attr() -> None:
    class CappedViaConfig(CustomerFilters):
        config = {"pagination_type": "limit_offset", "pagination_max_size": 10}

    class CappedViaAttr(CustomerFilters):
        pagination_type = "limit_offset"
        pagination_size = 5
        pagination_max_size: Optional[int] = 10

    class OverriddenToUnbounded(CappedViaAttr):
        pagination_max_size = None

    default_limit = next(f.limit for f in CappedViaConfig().to_statement_filters() if isinstance(f, LimitOffsetFilter))
    assert default_limit == 10

    at_limit = next(
        f.limit for f in CappedViaConfig(pageSize=10).to_statement_filters() if isinstance(f, LimitOffsetFilter)
    )
    assert at_limit == 10

    attr_default = next(f.limit for f in CappedViaAttr().to_statement_filters() if isinstance(f, LimitOffsetFilter))
    assert attr_default == 5

    with pytest.raises(ValueError, match="exceeds maximum allowed size 10"):
        CappedViaConfig(pageSize=11)

    with pytest.raises(ValueError, match="exceeds maximum allowed size 10"):
        CappedViaAttr(page_size=11)

    unbounded_limit = next(
        f.limit for f in OverriddenToUnbounded(pageSize=100).to_statement_filters() if isinstance(f, LimitOffsetFilter)
    )
    assert unbounded_limit == 100


@pytest.mark.parametrize(
    ("cfg", "match"),
    [
        ({"pagination_type": "limit_offset", "pagination_max_size": 0}, "pagination_max_size"),
        ({"pagination_type": "limit_offset", "pagination_max_size": -1}, "pagination_max_size"),
        ({"pagination_type": "limit_offset", "pagination_max_size": True}, "pagination_max_size"),
        ({"pagination_type": "limit_offset", "pagination_max_size": "10"}, "pagination_max_size"),
        ({"pagination_type": "limit_offset", "pagination_size": 20, "pagination_max_size": 10}, "cannot exceed"),
    ],
)
def test_pagination_max_size_invalid_config_raises(cfg: dict[str, object], match: str) -> None:
    class BadPaged(FilterSet[Customer]):
        config = cfg  # type: ignore[assignment]

    with pytest.raises(ImproperConfigurationError, match=match):
        BadPaged()
