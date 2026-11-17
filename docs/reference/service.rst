========
Services
========

.. py:module:: advanced_alchemy.service

Async Services
--------------

.. autoclass:: advanced_alchemy.service.SQLAlchemyAsyncRepositoryReadService
    :members: repository_type, get, count, list, list_and_count
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.service.SQLAlchemyAsyncRepositoryService
    :members: create, update, upsert, delete, to_model
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.service.SQLAlchemyAsyncQueryService
    :no-members:
    :no-inherited-members:
    :show-inheritance:

Sync Services
-------------

.. autoclass:: advanced_alchemy.service.SQLAlchemySyncRepositoryReadService
    :members: repository_type
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.service.SQLAlchemySyncRepositoryService
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.service.SQLAlchemySyncQueryService
    :no-members:
    :no-inherited-members:
    :show-inheritance:

Conversion, Pagination & Helpers
--------------------------------

:class:`ResultConverter`, :class:`OffsetPagination`, schema helpers, and the service type variables are documented in :doc:`service_conversion`.
