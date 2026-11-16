===================
Memory Repositories
===================

.. py:module:: advanced_alchemy.repository.memory

Mock repositories evaluate basic column predicates against loaded model values.
Boolean and null literals in comparisons retain SQL filtering semantics, including
``is_(True)``, ``is_not(False)``, and ``is_(None)``. SQL function expressions require
a database-backed repository.

Async Memory Repositories
-------------------------

.. autoclass:: advanced_alchemy.repository.memory.SQLAlchemyAsyncMockRepository
    :members: add, add_many, count, delete, delete_many, delete_where, exists, get, get_and_update, get_one, get_one_or_none, get_or_upsert, list, list_and_count, update, update_many, upsert, upsert_many, check_health
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.repository.memory.SQLAlchemyAsyncMockSlugRepository
    :members: get_by_slug, get_available_slug
    :no-inherited-members:
    :show-inheritance:

Sync Memory Repositories
------------------------

.. autoclass:: advanced_alchemy.repository.memory.SQLAlchemySyncMockRepository
    :members: check_health
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.repository.memory.SQLAlchemySyncMockSlugRepository
    :members: get_by_slug, get_available_slug
    :no-inherited-members:
    :show-inheritance:
