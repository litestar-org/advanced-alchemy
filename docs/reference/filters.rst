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
    :members: append_to_statement
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
    :members:
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.filters.LogicalOperatorMap
    :members:
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
