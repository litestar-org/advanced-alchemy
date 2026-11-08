========
litestar
========

.. py:module:: advanced_alchemy.extensions.litestar

Litestar framework integration providing plugins, session lifecycle handlers,
dependency injection providers, DTOs, server-side session backends, and CLI commands.

Session Lifecycle Handlers
--------------------------

.. autofunction:: advanced_alchemy.extensions.litestar.async_autocommit_before_send_handler

.. autofunction:: advanced_alchemy.extensions.litestar.async_autocommit_handler_maker

.. autofunction:: advanced_alchemy.extensions.litestar.async_default_before_send_handler

.. autofunction:: advanced_alchemy.extensions.litestar.async_default_handler_maker

.. autofunction:: advanced_alchemy.extensions.litestar.sync_autocommit_before_send_handler

.. autofunction:: advanced_alchemy.extensions.litestar.sync_autocommit_handler_maker

.. autofunction:: advanced_alchemy.extensions.litestar.sync_default_before_send_handler

.. autofunction:: advanced_alchemy.extensions.litestar.sync_default_handler_maker

Dependency Injection & CLI Plugin Helpers
-----------------------------------------

.. autofunction:: advanced_alchemy.extensions.litestar.get_database_migration_plugin

.. py:module:: advanced_alchemy.extensions.litestar.providers
    :no-typesetting:

.. autofunction:: advanced_alchemy.extensions.litestar.providers.create_service_dependencies

.. autofunction:: advanced_alchemy.extensions.litestar.providers.create_service_provider

.. autoclass:: advanced_alchemy.extensions.litestar.providers.FilterConfig
    :no-members:
    :no-inherited-members:
    :show-inheritance:

Additional API References
-------------------------

.. toctree::
    :titlesonly:

    dto
    plugins
    cli
    session
    store
