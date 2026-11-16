=========
FilterSet
=========

.. py:module:: advanced_alchemy.filterset

Reusable filter definitions combine typed field parameters, relationship predicates,
sorting, and inferred eager loading. See :doc:`/usage/repositories/filtersets` for
examples and matching semantics.

.. autoclass:: advanced_alchemy.filterset.FilterSet
    :members: to_statement_filters, load, inferred_load
    :no-inherited-members:
    :show-inheritance:
