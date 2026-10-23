"""Shared ABCs, type variables, and type aliases for ``advanced_alchemy.filters``.

This module is the bottom of the filters package dependency graph: every other
filters submodule may import from here, but ``_base`` may only depend on third
parties.
"""

import logging
from abc import ABC, abstractmethod
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Union,
    cast,
)

from sqlalchemy import (
    ColumnElement,
    Delete,
    Select,
    Update,
)
from sqlalchemy.sql.dml import ReturningDelete, ReturningUpdate
from typing_extensions import TypeAlias, TypedDict, TypeVar

from advanced_alchemy.base import ModelProtocol

if TYPE_CHECKING:
    from sqlalchemy.orm import InstrumentedAttribute

    from advanced_alchemy.filters._columns import (
        BeforeAfter,
        ChoicesFilter,
        CollectionFilter,
        ComparisonFilter,
        NotInCollectionFilter,
        NotNullFilter,
        NullFilter,
        OnBeforeAfter,
    )
    from advanced_alchemy.filters._fields import BooleanFilter
    from advanced_alchemy.filters._logical import (
        ExistsFilter,
        FilterGroup,
        NotExistsFilter,
    )
    from advanced_alchemy.filters._pagination import LimitOffset, OrderBy
    from advanced_alchemy.filters._relationship import RelationshipFilter
    from advanced_alchemy.filters._search import NotInSearchFilter, SearchFilter

    FilterFieldName: TypeAlias = Union[str, ColumnElement[Any], InstrumentedAttribute[Any]]
    InstrumentedField: TypeAlias = Union[ColumnElement[Any], InstrumentedAttribute[Any]]
else:
    FilterFieldName: TypeAlias = Any
    InstrumentedField: TypeAlias = Any

__all__ = (
    "FilterFieldName",
    "FilterMap",
    "InAnyFilter",
    "InstrumentedField",
    "LogicalOperatorMap",
    "ModelT",
    "PaginationFilter",
    "StatementFilter",
    "StatementFilterT",
    "StatementTypeT",
    "T",
    "logger",
)

T = TypeVar("T")
ModelT = TypeVar("ModelT", bound=ModelProtocol)
StatementFilterT = TypeVar("StatementFilterT", bound="StatementFilter")
StatementTypeT = TypeVar(
    "StatementTypeT",
    bound=Union[
        ReturningDelete[tuple[Any]], ReturningUpdate[tuple[Any]], Select[tuple[Any]], Select[Any], Update, Delete
    ],
)

logger = logging.getLogger("advanced_alchemy")


class FilterMap(TypedDict):
    before_after: "type[BeforeAfter]"
    on_before_after: "type[OnBeforeAfter]"
    boolean: "type[BooleanFilter]"
    choices: "type[ChoicesFilter[Any]]"
    collection: "type[CollectionFilter[Any]]"
    not_in_collection: "type[NotInCollectionFilter[Any]]"
    limit_offset: "type[LimitOffset]"
    null: "type[NullFilter]"
    not_null: "type[NotNullFilter]"
    order_by: "type[OrderBy]"
    search: "type[SearchFilter]"
    not_in_search: "type[NotInSearchFilter]"
    comparison: "type[ComparisonFilter]"
    exists: "type[ExistsFilter]"
    not_exists: "type[NotExistsFilter]"
    filter_group: "type[FilterGroup]"
    relationship: "type[RelationshipFilter]"


class LogicalOperatorMap(TypedDict):
    and_: Callable[..., ColumnElement[bool]]
    or_: Callable[..., ColumnElement[bool]]


class StatementFilter(ABC):
    """Abstract base class for SQLAlchemy statement filters.

    This class defines the interface for all filter types in the system. Each filter
    implementation must provide a method to append its filtering logic to an existing
    SQLAlchemy statement.
    """

    __slots__ = ()

    @abstractmethod
    def append_to_statement(
        self, statement: StatementTypeT, model: type[ModelT], *args: Any, **kwargs: Any
    ) -> StatementTypeT:
        """Append filter conditions to a SQLAlchemy statement.

        Args:
            statement: The SQLAlchemy statement to modify
            model: The SQLAlchemy model class
            *args: Additional positional arguments
            **kwargs: Additional keyword arguments

        Returns:
            StatementTypeT: Modified SQLAlchemy statement with filter conditions applied

        Raises:
            NotImplementedError: If the concrete class doesn't implement this method

        Note:
            This method must be implemented by all concrete filter classes.

        See Also:
            :meth:`sqlalchemy.sql.expression.Select.where`: SQLAlchemy where clause
        """
        return statement

    @staticmethod
    def _get_instrumented_attr(model: Any, key: FilterFieldName) -> InstrumentedField:
        """Get SQLAlchemy instrumented attribute from model.

        Args:
            model: SQLAlchemy model class or instance
            key: Attribute name or instrumented attribute

        Returns:
            InstrumentedAttribute[Any]: SQLAlchemy instrumented attribute

        See Also:
            :class:`sqlalchemy.orm.attributes.InstrumentedAttribute`: SQLAlchemy attribute
        """
        return cast("InstrumentedAttribute[Any]", getattr(model, key)) if isinstance(key, str) else key


class InAnyFilter(StatementFilter, ABC):
    """Base class for filters using IN or ANY operators.

    This abstract class provides common functionality for filters that check
    membership in a collection using either the SQL IN operator or the ANY operator.
    """

    __slots__ = ()


class PaginationFilter(StatementFilter, ABC):
    """Abstract base class for pagination filters.

    Subclasses should implement pagination logic, such as limit/offset or
    cursor-based pagination.
    """

    __slots__ = ()
