===================
Memory Repositories
===================

.. py:module:: advanced_alchemy.repository.memory

Async Memory Repositories
-------------------------

.. autoclass:: advanced_alchemy.repository.memory.SQLAlchemyAsyncMockRepository
    :members: add, add_many, count, delete, delete_many, delete_where, exists, get, get_and_update, get_one, get_one_or_none, get_or_upsert, get_many, get_many_and_count, update, update_many, upsert, upsert_many, check_health
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
