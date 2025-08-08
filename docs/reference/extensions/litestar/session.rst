================
Session Backends
================

.. currentmodule:: advanced_alchemy.extensions.litestar.session

This module provides SQLAlchemy-based session backends for Litestar's server-side session middleware.

Session Model Mixin
===================

.. autoclass:: SessionModelMixin
    :members:
    :show-inheritance:

Session Backend Base
====================

.. autoclass:: SQLAlchemySessionBackendBase
    :members:
    :show-inheritance:

Async Session Backend
=====================

.. autoclass:: SQLAlchemyAsyncSessionBackend
    :members:
    :show-inheritance:

Sync Session Backend
====================

.. autoclass:: SQLAlchemySyncSessionBackend
    :members:
    :show-inheritance:
