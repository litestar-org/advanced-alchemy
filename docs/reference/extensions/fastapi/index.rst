=======
fastapi
=======

API Reference for the ``FastAPI`` extensions module.

.. py:module:: advanced_alchemy.extensions.fastapi

Extension & CLI
---------------

.. autoclass:: AdvancedAlchemy
    :members:
    :no-inherited-members:
    :show-inheritance:

.. autofunction:: assign_cli_group

.. autofunction:: get_database_migration_plugin

Configuration
-------------

FastAPI re-exports the Starlette configuration classes:

- :class:`~advanced_alchemy.extensions.starlette.SQLAlchemyAsyncConfig`
- :class:`~advanced_alchemy.extensions.starlette.SQLAlchemySyncConfig`
- :class:`~advanced_alchemy.extensions.starlette.EngineConfig`
- :class:`~advanced_alchemy.config.AlembicAsyncConfig`
- :class:`~advanced_alchemy.config.AlembicSyncConfig`
- :class:`~advanced_alchemy.config.AsyncSessionConfig`
- :class:`~advanced_alchemy.config.SyncSessionConfig`

Dependency Providers
--------------------

.. py:module:: advanced_alchemy.extensions.fastapi.providers

.. autofunction:: provide_service

.. autofunction:: provide_filters

.. autoclass:: DependencyDefaults
    :members:
    :no-inherited-members:

.. autodata:: DEPENDENCY_DEFAULTS
    :no-value:
