===============
Bulk Operations
===============

.. py:module:: advanced_alchemy.operations

Upsert & Merge Constructs
-------------------------

.. autoclass:: advanced_alchemy.operations.OnConflictUpsert
    :members: supports_native_upsert, create_upsert, create_upsert_many, create_merge_upsert, create_merge_many, create_insert_or_update_many
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.operations.MergeStatement
    :no-members:
    :no-inherited-members:
    :show-inheritance:

Strategy Resolution & Validation
--------------------------------

.. autoclass:: advanced_alchemy.operations.UpsertStrategy
    :members: kind, supports_returning, conflict_columns, dialect_name
    :no-inherited-members:
    :show-inheritance:

.. autofunction:: advanced_alchemy.operations.resolve_upsert_strategy

.. autofunction:: advanced_alchemy.operations.resolve_column_default

.. autofunction:: advanced_alchemy.operations.validate_identifier

.. py:data:: UpsertKind
    :type: typing.TypeAlias

    Literal union of supported dialect upsert execution strategies.
