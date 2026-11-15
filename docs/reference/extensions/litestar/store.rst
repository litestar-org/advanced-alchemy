================
SQLAlchemy Store
================

.. py:module:: advanced_alchemy.extensions.litestar.store

This module provides a SQLAlchemy-backed implementation of Litestar's
:class:`Store <litestar.stores.base.Store>` protocol. Register a
:class:`SQLAlchemyStore` under the ``"sessions"`` store name to back Litestar's
server-side session middleware with your SQLAlchemy database. Invalid store or
model configuration raises :exc:`litestar.exceptions.ImproperlyConfiguredException`.

Store Model Mixin
-----------------

.. autoclass:: advanced_alchemy.extensions.litestar.store.StoreModelMixin
    :members: key, namespace, value, expires_at, is_expired
    :no-inherited-members:
    :show-inheritance:

Store Implementation
--------------------

.. autoclass:: advanced_alchemy.extensions.litestar.store.SQLAlchemyStore
    :members: get, set, delete, delete_all, exists, expires_in, delete_expired, with_namespace
    :no-inherited-members:
    :show-inheritance:
