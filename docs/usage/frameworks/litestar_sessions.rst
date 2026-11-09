=====================================
Litestar Database and Server Sessions
=====================================

This guide covers two kinds of "sessions" in Litestar:

1. **Database sessions**: The SQLAlchemy connection used by your routes to read and save rows during a request.
2. **Server-side user sessions**: Keeping logged-in user state (like shopping carts or auth data) inside a database table instead of Redis.

Per-Request Database Sessions
-----------------------------

When ``SQLAlchemyPlugin`` is registered, Litestar injects a database session under the ``db_session`` parameter name. You can control when changes commit by setting ``before_send_handler`` on your config:

* ``"autocommit"`` saves changes automatically when a route returns a normal ``2xx`` response and rolls back on errors.
* ``"autocommit_include_redirects"`` also commits when a route returns a ``3xx`` redirect (useful for HTML form submissions).

Need a session outside a web request, such as in a startup hook or background script? Open one directly with ``async with config.get_session() as db_session:``.

Connecting Multiple Databases
-----------------------------

To talk to both a main database and an analytics database in one Litestar app, pass a list of configs with unique ``session_dependency_key``, ``engine_dependency_key``, and ``bind_key`` names:

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

Storing User Sessions in Your Database
--------------------------------------

Instead of running a separate Redis server just for user login cookies or rate-limit counters, you can store them in your SQL database using ``SQLAlchemyStore`` or ``SQLAlchemyAsyncSessionBackend``:

.. tab-set::

    .. tab-item:: 1. Store Table

        .. literalinclude:: /examples/litestar/session_store.py
            :language: python
            :pyobject: AppStoreModel

    .. tab-item:: 2. Route Handler

        .. literalinclude:: /examples/litestar/session_store.py
            :language: python
            :start-at: @post(path="/session/{key:str}/{value:str}")
            :end-before: @post(

    .. tab-item:: 3. App Wiring

        .. literalinclude:: /examples/litestar/session_store.py
            :language: python
            :pyobject: create_app

    .. tab-item:: Dedicated Session Backend

        .. code-block:: python

            from advanced_alchemy.extensions.litestar.session import (
                SQLAlchemyAsyncSessionBackend,
                SessionModelMixin,
            )


            class UserSessionModel(SessionModelMixin):
                __tablename__ = "litestar_user_sessions"


            assert issubclass(UserSessionModel, SessionModelMixin)
            assert SQLAlchemyAsyncSessionBackend is not None

Both approaches use native database upserts and include a ``delete_expired()`` helper to clear old session rows on a schedule.

Related Guides
--------------

* :doc:`/usage/frameworks/litestar` — Core Litestar plugin, DTOs, and controllers.
* :doc:`/usage/frameworks/litestar_storage` — Uploading files with ``StoredObject``.
* :doc:`/reference/extensions/litestar/store` — Store and session backend API reference.
