====================
Litestar Integration
====================

.. seealso::

    :external+litestar:doc:`Litestar's documentation for SQLAlchemy integration <usage/databases/sqlalchemy/index>`

Advanced Alchemy provides first-class integration with Litestar through :class:`~advanced_alchemy.extensions.litestar.SQLAlchemyPlugin`, which re-exports core models, repositories, services, filters, and data transfer objects under ``advanced_alchemy.extensions.litestar``.

Installation
------------

Install Advanced Alchemy with the ``litestar`` extra using your preferred package manager:

.. tab-set::
    :sync-group: pkg

    .. tab-item:: uv
        :sync: uv

        .. code-block:: bash

            uv add "advanced-alchemy[litestar]" aiosqlite

    .. tab-item:: pip
        :sync: pip

        .. code-block:: bash

            pip install "advanced-alchemy[litestar]" aiosqlite

    .. tab-item:: pdm
        :sync: pdm

        .. code-block:: bash

            pdm add "advanced-alchemy[litestar]" aiosqlite

    .. tab-item:: poetry
        :sync: poetry

        .. code-block:: bash

            poetry add "advanced-alchemy[litestar]" aiosqlite

Plugin and Engine Configuration
-------------------------------

Configure :class:`~advanced_alchemy.extensions.litestar.SQLAlchemyAsyncConfig` or :class:`~advanced_alchemy.extensions.litestar.SQLAlchemySyncConfig` and register :class:`~advanced_alchemy.extensions.litestar.SQLAlchemyPlugin` on your Litestar application. The plugin manages engine lifecycles, request-scoped database sessions, exception handling, and CLI migration commands:

.. literalinclude:: /examples/litestar/basic_app.py
    :language: python
    :pyobject: create_app

Models, Schemas, and Data Transfer Objects
------------------------------------------

Define declarative models using the base classes in :mod:`advanced_alchemy.base` (re-exported as ``advanced_alchemy.extensions.litestar.base``), alongside :class:`msgspec.Struct` schemas or :class:`~advanced_alchemy.extensions.litestar.dto.SQLAlchemyDTO` definitions:

.. literalinclude:: /examples/litestar/basic_app.py
    :language: python
    :start-at: class AuthorModel
    :end-before: class AuthorRepository

:class:`~advanced_alchemy.extensions.litestar.dto.SQLAlchemyDTO` automatically inspects model columns, relationships, and ``@property`` / ``@cached_property`` descriptors (exposing properties as read-only fields):

.. code-block:: python

    from functools import cached_property
    from sqlalchemy.orm import Mapped
    from advanced_alchemy.extensions.litestar import SQLAlchemyDTO, base


    class UserAccount(base.UUIDAuditBase):
        __tablename__ = "litestar_doc_user_account"
        first_name: Mapped[str]
        last_name: Mapped[str]

        @property
        def full_name(self) -> str:
            return f"{self.first_name} {self.last_name}"

        @cached_property
        def display_length(self) -> int:
            return len(self.full_name)


    UserAccountDTO = SQLAlchemyDTO[UserAccount]

Repositories and Services
-------------------------

Bind a model to a repository and service class to encapsulate query execution, pagination, and schema serialization:

.. literalinclude:: /examples/litestar/basic_app.py
    :language: python
    :start-at: class AuthorRepository
    :end-before: class AuthorController

Controllers and Dependency Injection
------------------------------------

Use :func:`~advanced_alchemy.extensions.litestar.providers.create_service_dependencies` to wire service instances and query filter dependencies (such as ID filters, search filters, date bounds, and limit/offset pagination) directly into route handlers:

.. literalinclude:: /examples/litestar/basic_app.py
    :language: python
    :pyobject: AuthorController

Complete Runnable Example
-------------------------

The full runnable module is located in ``docs/examples/litestar/basic_app.py`` and can be verified in-process with Litestar's test client:

.. literalinclude:: /examples/litestar/basic_app.py
    :language: python

Related Guides
--------------

- :doc:`litestar_sessions` — Session management, multi-database configurations, and server-side session backends.
- :doc:`litestar_storage` — Declarative file uploads and storage backends.
- :doc:`/reference/extensions/litestar/cli` — CLI migration commands.
