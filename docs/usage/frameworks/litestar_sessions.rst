========================================
Litestar Database and Server Sessions
========================================

Advanced Alchemy manages both request-scoped SQLAlchemy database sessions and database-backed server-side HTTP sessions for Litestar applications.

Request-Scoped Database Sessions
--------------------------------

When :class:`~advanced_alchemy.extensions.litestar.SQLAlchemyPlugin` is registered, Litestar injects a request-scoped SQLAlchemy session under the ``db_session`` dependency key (configurable via ``session_dependency_key`` on :class:`~advanced_alchemy.extensions.litestar.SQLAlchemyAsyncConfig` or :class:`~advanced_alchemy.extensions.litestar.SQLAlchemySyncConfig`).

Configure ``before_send_handler`` on the plugin configuration to control transaction commit behavior at the end of each HTTP response:

- ``"autocommit"`` commits the transaction when the response succeeds and rolls back on unhandled exceptions or error status codes.
- ``"autocommit_include_redirect"`` also commits on ``3xx`` redirect responses.

Outside a request handler (such as in lifespan hooks or CLI tasks), open a managed session directly with ``async with config.get_session() as db_session:`` or retrieve the request session from ASGI scope via ``config.provide_session(app.state, scope)``.

Multi-Database Configurations
-----------------------------

Pass a sequence of configuration objects to :class:`~advanced_alchemy.extensions.litestar.SQLAlchemyPlugin` with distinct ``session_dependency_key``, ``engine_dependency_key``, and ``bind_key`` values to connect a single Litestar application to multiple databases:

.. code-block:: python

    from advanced_alchemy.extensions.litestar import SQLAlchemyAsyncConfig, SQLAlchemyPlugin

    primary_config = SQLAlchemyAsyncConfig(
        connection_string="sqlite+aiosqlite:///:memory:",
        session_dependency_key="primary_session",
        engine_dependency_key="primary_engine",
        bind_key="primary",
    )
    analytics_config = SQLAlchemyAsyncConfig(
        connection_string="sqlite+aiosqlite:///:memory:",
        session_dependency_key="analytics_session",
        engine_dependency_key="analytics_engine",
        bind_key="analytics",
    )
    plugin = SQLAlchemyPlugin(config=[primary_config, analytics_config])

Store-Based Server-Side Sessions
--------------------------------

Advanced Alchemy provides :class:`~advanced_alchemy.extensions.litestar.store.SQLAlchemyStore` (a Litestar :class:`~litestar.stores.base.NamespacedStore`) and :class:`~advanced_alchemy.extensions.litestar.store.StoreModelMixin` for storing server-side sessions, rate-limit counters, or response cache entries in your relational database:

.. literalinclude:: /examples/litestar/session_store.py
    :language: python
    :pyobject: AppStoreModel

Wire :class:`~advanced_alchemy.extensions.litestar.store.SQLAlchemyStore` into Litestar's :class:`~litestar.stores.registry.StoreRegistry` and :class:`~litestar.middleware.session.server_side.ServerSideSessionConfig`:

.. literalinclude:: /examples/litestar/session_store.py
    :language: python
    :start-at: @post(path="/session/{key:str}/{value:str}")
    :end-before: @post(

.. literalinclude:: /examples/litestar/session_store.py
    :language: python
    :pyobject: create_app

Backend-Based Server-Side Sessions
----------------------------------

Alternatively, use :class:`~advanced_alchemy.extensions.litestar.session.SQLAlchemyAsyncSessionBackend` or :class:`~advanced_alchemy.extensions.litestar.session.SQLAlchemySyncSessionBackend` with a declarative model inheriting from :class:`~advanced_alchemy.extensions.litestar.session.SessionModelMixin`:

.. code-block:: python

    from advanced_alchemy.extensions.litestar.session import (
        SQLAlchemyAsyncSessionBackend,
        SessionModelMixin,
    )


    class UserSessionModel(SessionModelMixin):
        __tablename__ = "litestar_user_sessions"


    assert issubclass(UserSessionModel, SessionModelMixin)
    assert SQLAlchemyAsyncSessionBackend is not None

Both :class:`~advanced_alchemy.extensions.litestar.store.SQLAlchemyStore` and :class:`~advanced_alchemy.extensions.litestar.session.SQLAlchemyAsyncSessionBackend` execute dialect-optimized ``MERGE`` / ``ON CONFLICT`` upserts and provide ``delete_expired()`` maintenance methods for purging expired session rows.

Related Documentation
---------------------

- :doc:`/usage/frameworks/litestar` — Core Litestar setup, DTOs, repositories, and controllers.
- :doc:`/usage/frameworks/litestar_storage` — Declarative file storage and multipart uploads.
- :doc:`/reference/extensions/litestar/session` — Session backend API reference.
- :doc:`/reference/extensions/litestar/store` — General-purpose SQLAlchemy store API reference.
