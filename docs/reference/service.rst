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

.. autoclass:: advanced_alchemy.service.ResultConverter
    :members: to_schema
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.service.OffsetPagination
    :members: items, limit, offset, total
    :no-inherited-members:
    :show-inheritance:

.. autofunction:: advanced_alchemy.service.find_filter

.. autoclass:: advanced_alchemy.service.SchemaDumpConfig
    :members:
    :no-inherited-members:

.. autofunction:: advanced_alchemy.service.schema_dump

.. autofunction:: advanced_alchemy.service.fields

.. autodata:: advanced_alchemy.service.ModelDTOT
    :no-value:

.. autodata:: advanced_alchemy.service.ModelDictT
    :no-value:

.. autodata:: advanced_alchemy.service.ModelDictListT
    :no-value:

.. autodata:: advanced_alchemy.service.FilterTypeT
    :no-value:

.. autodata:: advanced_alchemy.service.SupportedSchemaModel
    :no-value:

.. autoclass:: advanced_alchemy.service.AttrsInstance
    :no-members:
    :no-inherited-members:

.. py:data:: ATTRS_INSTALLED
    :type: bool

    Boolean flag indicating whether ``attrs`` is installed.
