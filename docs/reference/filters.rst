.. _filters:

=======
Filters
=======

.. py:module:: advanced_alchemy.filters

Base & Pagination Filters
-------------------------

.. autoclass:: advanced_alchemy.filters.StatementFilter
    :members: append_to_statement
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.filters.PaginationFilter
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.filters.LimitOffset
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.filters.OrderBy
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.filters.OrderingApply
    :no-members:
    :no-inherited-members:
    :show-inheritance:

Date, Time & Nullability Filters
--------------------------------

.. autoclass:: advanced_alchemy.filters.BeforeAfter
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.filters.OnBeforeAfter
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.filters.DatePartFilter
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.filters.NullFilter
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.filters.NotNullFilter
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.filters.BooleanFilter
    :no-members:
    :no-inherited-members:
    :show-inheritance:

Collection, Search & Comparison Filters
---------------------------------------

.. autoclass:: advanced_alchemy.filters.CollectionFilter
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.filters.InAnyFilter
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.filters.NotInCollectionFilter
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.filters.ChoicesFilter
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.filters.SearchFilter
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.filters.NotInSearchFilter
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.filters.ComparisonFilter
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.filters.ExistsFilter
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.filters.NotExistsFilter
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.filters.RelationshipFilter
    :no-members:
    :no-inherited-members:
    :show-inheritance:

Declarative FilterSet & Field Filters
-------------------------------------

.. autoclass:: advanced_alchemy.filters.FilterSet
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.filters.BaseFieldFilter
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.filters.FieldSpec
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.filters.StringFilter
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.filters.NumberFilter
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.filters.DateFilter
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.filters.DateTimeFilter
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.filters.UUIDFilter
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.filters.EnumFilter
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.filters.OrderingFilter
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. py:data:: UNSET
    :type: object

    Sentinel value used to distinguish omitted defaults from ``None``.

Composite Filters, Type Aliases & Helpers
-----------------------------------------

.. autoclass:: advanced_alchemy.filters.FilterGroup
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.filters.MultiFilter
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.filters.FilterMap
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.filters.LogicalOperatorMap
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autofunction:: advanced_alchemy.filters.escape_like_value

.. py:data:: LIKE_ESCAPE_CHAR
    :type: str

    Default escape character used in SQL ``LIKE`` and ``ILIKE`` patterns.

.. autodata:: advanced_alchemy.filters.FilterTypes
    :no-value:

.. autodata:: advanced_alchemy.filters.StatementFilterT
    :no-value:

.. autodata:: advanced_alchemy.filters.StatementTypeT
    :no-value:
