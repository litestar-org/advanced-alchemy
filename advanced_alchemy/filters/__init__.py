"""SQLAlchemy filter constructs for advanced query operations.

This package provides a comprehensive collection of filter datastructures designed to
enhance SQLAlchemy query construction. It implements type-safe, reusable filter patterns
for common database query operations.

Features:
    Type-safe filter construction, datetime range filtering, collection-based filtering,
    pagination support, search operations, and customizable ordering.

Note:
    All filter classes implement the :class:`StatementFilter` ABC, ensuring consistent
    interface across different filter types.

See Also:
    - :class:`sqlalchemy.sql.expression.Select`: Core SQLAlchemy select expression
    - :class:`sqlalchemy.orm.Query`: SQLAlchemy ORM query interface
    - :mod:`advanced_alchemy.base`: Base model definitions

"""

from typing import Any, Union

from typing_extensions import TypeAlias

from advanced_alchemy.filters._base import (
    FilterMap,
    InAnyFilter,
    LogicalOperatorMap,
    PaginationFilter,
    StatementFilter,
    StatementFilterT,
    StatementTypeT,
)
from advanced_alchemy.filters._columns import (
    BeforeAfter,
    CollectionFilter,
    ComparisonFilter,
    NotInCollectionFilter,
    NotNullFilter,
    NullFilter,
    OnBeforeAfter,
)
from advanced_alchemy.filters._fields import (
    BooleanFilter,
    DateFilter,
    DatePartFilter,
    DateTimeFilter,
    EnumFilter,
    NumberFilter,
    StringFilter,
    UUIDFilter,
)
from advanced_alchemy.filters._filterset import UNSET, BaseFieldFilter, FieldSpec
from advanced_alchemy.filters._logical import (
    ExistsFilter,
    FilterGroup,
    MultiFilter,
    NotExistsFilter,
)
from advanced_alchemy.filters._pagination import LimitOffset, OrderBy
from advanced_alchemy.filters._relationship import RelationshipFilter
from advanced_alchemy.filters._search import NotInSearchFilter, SearchFilter

__all__ = (
    "UNSET",
    "BaseFieldFilter",
    "BeforeAfter",
    "BooleanFilter",
    "CollectionFilter",
    "ComparisonFilter",
    "DateFilter",
    "DatePartFilter",
    "DateTimeFilter",
    "EnumFilter",
    "ExistsFilter",
    "FieldSpec",
    "FilterGroup",
    "FilterMap",
    "FilterTypes",
    "InAnyFilter",
    "LimitOffset",
    "LogicalOperatorMap",
    "MultiFilter",
    "NotExistsFilter",
    "NotInCollectionFilter",
    "NotInSearchFilter",
    "NotNullFilter",
    "NullFilter",
    "NumberFilter",
    "OnBeforeAfter",
    "OrderBy",
    "PaginationFilter",
    "RelationshipFilter",
    "SearchFilter",
    "StatementFilter",
    "StatementFilterT",
    "StatementTypeT",
    "StringFilter",
    "UUIDFilter",
)


FilterTypes: TypeAlias = Union[
    BeforeAfter,
    OnBeforeAfter,
    CollectionFilter[Any],
    LimitOffset,
    NullFilter,
    NotNullFilter,
    OrderBy,
    SearchFilter,
    NotInCollectionFilter[Any],
    NotInSearchFilter,
    ExistsFilter,
    NotExistsFilter,
    ComparisonFilter,
    MultiFilter,
    FilterGroup,
    RelationshipFilter,
]
