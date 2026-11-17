=================
Cursor Pagination
=================

.. py:currentmodule:: advanced_alchemy.filters

Keyset pagination filters, ordering keys, and the token codec hook. See
:doc:`/usage/repositories/filtering` for usage and :doc:`service_conversion` for the
:class:`~advanced_alchemy.service.CursorPagination` response container.

Filter
------

.. autoclass:: advanced_alchemy.filters.CursorFilter
    :members: build_page, keys, limit, cursor, backward, encrypted, ttl
    :no-inherited-members:
    :show-inheritance:

Ordering Keys
-------------

.. autoclass:: advanced_alchemy.filters.CursorKey
    :members: name
    :no-inherited-members:

.. autodata:: advanced_alchemy.filters.CursorKeys
    :no-value:

.. autofunction:: advanced_alchemy.filters.normalize_cursor_keys

Token Codec
-----------

.. autofunction:: advanced_alchemy.filters.register_cursor_type
