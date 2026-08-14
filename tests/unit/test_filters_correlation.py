"""Correlation behaviour of :class:`ExistsFilter` and :class:`NotExistsFilter`."""

import pytest
from sqlalchemy import ForeignKey, String, literal_column, select, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from advanced_alchemy.filters import ExistsFilter, NotExistsFilter, UncorrelatedSubqueryWarning

pytestmark = pytest.mark.unit


class Base(DeclarativeBase):
    pass


class Organization(Base):
    __tablename__ = "correlation_organization"

    id: Mapped[int] = mapped_column(primary_key=True)


class User(Base):
    __tablename__ = "correlation_user"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("correlation_organization.id"))
    email: Mapped[str] = mapped_column(String(length=100))


def _compiled(filter_: "ExistsFilter | NotExistsFilter") -> str:
    return str(filter_.append_to_statement(select(Organization), Organization))


@pytest.mark.parametrize("filter_type", [ExistsFilter, NotExistsFilter])
def test_conditions_missing_the_correlation_warn(filter_type: type) -> None:
    """An uncorrelated subquery matches every outer row instead of raising, so it has to be loud."""
    filter_ = filter_type(values=[User.email.like("%@example.com%")])
    with pytest.warns(UncorrelatedSubqueryWarning, match="not correlated"):
        compiled = _compiled(filter_)
    assert "correlation_organization" not in compiled.split("EXISTS", 1)[1]


@pytest.mark.parametrize("filter_type", [ExistsFilter, NotExistsFilter])
def test_correlated_conditions_do_not_warn(filter_type: type, recwarn: pytest.WarningsRecorder) -> None:
    filter_ = filter_type(values=[User.organization_id == Organization.id, User.email.like("%@example.com%")])
    compiled = _compiled(filter_)
    assert not [w for w in recwarn if issubclass(w.category, UncorrelatedSubqueryWarning)]
    assert "correlation_user.organization_id = correlation_organization.id" in compiled


@pytest.mark.parametrize("filter_type", [ExistsFilter, NotExistsFilter])
def test_self_referential_conditions_do_not_warn(filter_type: type, recwarn: pytest.WarningsRecorder) -> None:
    """A condition on the outer table itself is already correlated — the common single-table usage."""
    filter_ = filter_type(values=[Organization.id > 1])
    _compiled(filter_)
    assert not [w for w in recwarn if issubclass(w.category, UncorrelatedSubqueryWarning)]


@pytest.mark.parametrize("filter_type", [ExistsFilter, NotExistsFilter])
@pytest.mark.parametrize(
    "raw",
    [
        text("correlation_user.organization_id = correlation_organization.id"),
        literal_column("correlation_organization.id") == User.organization_id,
    ],
    ids=["text", "literal_column"],
)
def test_raw_sql_conditions_do_not_warn(filter_type: type, raw: object, recwarn: pytest.WarningsRecorder) -> None:
    """Raw SQL hides its tables, so a correlation written that way must not be reported as missing."""
    filter_ = filter_type(values=[raw])
    _compiled(filter_)
    assert not [w for w in recwarn if issubclass(w.category, UncorrelatedSubqueryWarning)]
