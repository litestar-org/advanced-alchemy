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

Framework Settings
------------------

Options the Litestar and FastAPI filter dependencies resolve for each request. See
:doc:`/usage/repositories/cursor_pagination` for how the secret is configured.

.. autoclass:: advanced_alchemy.utils.dependencies.CursorSettings
    :members: build, token_options
    :no-inherited-members:

.. autofunction:: advanced_alchemy.utils.dependencies.resolve_cursor_settings

.. autoclass:: advanced_alchemy.utils.dependencies.CursorDefaults
    :no-members:
    :no-inherited-members:

.. autofunction:: advanced_alchemy.utils.dependencies.resolve_cursor_defaults

.. autodata:: advanced_alchemy.utils.dependencies.CURSOR_SECRET_ENV_VARS
