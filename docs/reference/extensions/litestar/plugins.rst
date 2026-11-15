=======================
Plugins & Configuration
=======================

.. py:module:: advanced_alchemy.extensions.litestar.plugins

Plugin Classes
--------------

.. autoclass:: advanced_alchemy.extensions.litestar.plugins.SQLAlchemyPlugin
    :members: config, on_app_init
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.extensions.litestar.plugins.SQLAlchemyInitPlugin
    :members: on_app_init
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.extensions.litestar.plugins.SQLAlchemySerializationPlugin
    :members: on_app_init, supports_type
    :no-inherited-members:
    :show-inheritance:

Plugin Configuration Classes
----------------------------

.. autoclass:: advanced_alchemy.extensions.litestar.plugins.SQLAlchemyAsyncConfig
    :members: provide_session, provide_engine, create_all_metadata
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.extensions.litestar.plugins.SQLAlchemySyncConfig
    :members: provide_session, provide_engine, create_all_metadata
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.extensions.litestar.plugins.EngineConfig
    :no-members:
    :no-inherited-members:
    :show-inheritance:
