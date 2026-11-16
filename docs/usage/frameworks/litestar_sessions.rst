=====================================
Litestar Database and Server Sessions
=====================================

This guide covers two distinct session layers in Litestar:

1. **Database sessions**: Per-request SQLAlchemy ``Session`` or ``AsyncSession`` instances used by repositories and services.
2. **Server-side HTTP sessions and key-value stores**: Persisting Litestar server-side session payloads and store entries in a SQL table instead of Redis.

Per-Request Database Sessions
-----------------------------

When ``SQLAlchemyPlugin`` is registered, Litestar injects a database session under the ``db_session`` parameter name. Control transaction commits by setting ``before_send_handler`` on your config:

* ``"autocommit"`` commits automatically when a route returns a ``2xx`` response and rolls back on errors.
* ``"autocommit_include_redirects"`` also commits when a route returns a ``3xx`` redirect (such as after HTML form submissions).

Outside an HTTP request (such as in a startup hook or background task), open a session directly with ``async with config.get_session() as db_session:``.

Connecting Multiple Databases
-----------------------------

To configure multiple databases in one Litestar application, pass a list of configs with unique ``session_dependency_key``, ``engine_dependency_key``, and ``bind_key`` names:

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

Persist server-side session payloads, rate-limit counters, or general key-value entries in SQL using ``SQLAlchemyStore`` or ``SQLAlchemyAsyncSessionBackend``:

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

Both backends use native database upserts and expose ``delete_expired()`` for removing expired rows from scheduled jobs or lifecycle hooks.

Related Guides
--------------

* :doc:`/usage/frameworks/litestar`: Core Litestar plugin, DTOs, and controllers.
* :doc:`/usage/frameworks/litestar_storage`: Uploading files with ``StoredObject``.
* :doc:`/reference/extensions/litestar/store`: Store and session backend API reference.
