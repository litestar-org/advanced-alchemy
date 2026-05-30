=====
Store
=====

.. currentmodule:: advanced_alchemy.extensions.litestar.store

This module provides a SQLAlchemy-backed implementation of Litestar's
:class:`Store <litestar.stores.base.Store>` protocol. Register a
:class:`SQLAlchemyStore` under the ``"sessions"`` store name to back Litestar's
server-side session middleware with your SQLAlchemy database.

Store Model Mixin
=================

.. autoclass:: StoreModelMixin
    :members:
    :show-inheritance:

SQLAlchemy Store
================

.. autoclass:: SQLAlchemyStore
    :members:
    :show-inheritance:
