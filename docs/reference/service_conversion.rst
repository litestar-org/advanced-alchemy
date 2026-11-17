==============================
Schema Conversion & Pagination
==============================

.. py:currentmodule:: advanced_alchemy.service

Result conversion, pagination containers, schema helpers, and type variables exported from :mod:`advanced_alchemy.service`.

Conversion & Pagination
-----------------------

.. autoclass:: advanced_alchemy.service.ResultConverter
    :members: to_schema
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.service.OffsetPagination
    :members: items, limit, offset, total
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.service.CursorPagination
    :members: items, limit, next_cursor, previous_cursor, has_next, has_previous
    :no-inherited-members:
    :show-inheritance:

.. autodata:: advanced_alchemy.service.Pagination
    :no-value:

.. autofunction:: advanced_alchemy.service.find_filter

Schema Helpers
--------------

.. autoclass:: advanced_alchemy.service.SchemaDumpConfig
    :members:
    :no-inherited-members:

.. autofunction:: advanced_alchemy.service.schema_dump

.. autofunction:: advanced_alchemy.service.fields

Type Variables & Flags
----------------------

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
