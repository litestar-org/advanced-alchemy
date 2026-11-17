====================
Litestar Integration
====================

Advanced Alchemy is the official SQLAlchemy integration for Litestar. ``SQLAlchemyPlugin`` configures engine lifecycles, per-request sessions, DTO and msgspec serialization, repository exception handlers, and ``litestar database`` CLI commands.

What's Included for Litestar
----------------------------

.. list-table::
   :header-rows: 1
   :widths: 26 48 26

   * - Feature
     - Capabilities
     - Guide & API
   * - **Plugin & Configs**
     - Starts engines on app startup, opens a session per request, and maps database errors to HTTP responses.
     - :doc:`API </reference/extensions/litestar/plugins>`
   * - **Service & Filter DI**
     - Injects services and OpenAPI search, sort, and pagination filters into controller routes.
     - :doc:`Guide <litestar_dtos>` · :doc:`API </reference/extensions/litestar/index>`
   * - **SQLAlchemy DTOs**
     - Auto-generates request/response DTOs from your SQLAlchemy models and ``@property`` fields.
     - :doc:`Guide <litestar_dtos>` · :doc:`API </reference/extensions/litestar/dto>`
   * - **Sessions & Stores**
     - Connects multiple databases and stores server-side user sessions or cache keys in SQL tables.
     - :doc:`Guide <litestar_sessions>` · :doc:`API </reference/extensions/litestar/store>`
   * - **File Storage**
     - Streams ``UploadFile`` payloads to local disk or S3/GCS and cleans up orphaned files on delete.
     - :doc:`Guide <litestar_storage>` · :doc:`API </reference/types>`
   * - **Database CLI**
     - Adds ``litestar database make-migrations``, ``upgrade``, and ``dump-data`` commands automatically. ``dump-data`` exports tables as JSON, JSON Lines, or CSV fixtures, with optional compression and size-based sharding.
     - :doc:`Guide </usage/cli_commands>` · :doc:`API </reference/extensions/litestar/cli>`

Installation
------------

.. tab-set::
    :sync-group: pkg

    .. tab-item:: uv
        :sync: uv

        .. code-block:: bash

            uv add "advanced-alchemy[litestar,aiosqlite]"

    .. tab-item:: pip
        :sync: pip

        .. code-block:: bash

            pip install "advanced-alchemy[litestar,aiosqlite]"

    .. tab-item:: pdm
        :sync: pdm

        .. code-block:: bash

            pdm add "advanced-alchemy[litestar,aiosqlite]"

    .. tab-item:: poetry
        :sync: poetry

        .. code-block:: bash

            poetry add "advanced-alchemy[litestar,aiosqlite]"

Building an Author API Step by Step
-----------------------------------

Connect a model, repository, service, controller, and ``SQLAlchemyPlugin``:

.. tab-set::

    .. tab-item:: 1. Models & Schemas

        .. literalinclude:: /examples/litestar/basic_app.py
            :language: python
            :start-at: class AuthorModel
            :end-before: class AuthorRepository

    .. tab-item:: 2. Repository & Service

        .. literalinclude:: /examples/litestar/basic_app.py
            :language: python
            :start-at: class AuthorRepository
            :end-before: class AuthorController

    .. tab-item:: 3. Controller & Filters

        .. literalinclude:: /examples/litestar/basic_app.py
            :language: python
            :pyobject: AuthorController

    .. tab-item:: 4. Plugin & App Setup

        .. literalinclude:: /examples/litestar/basic_app.py
            :language: python
            :pyobject: create_app

Auto-Generating DTOs from Models
--------------------------------

``SQLAlchemyDTO`` generates Litestar request and response DTOs directly from SQLAlchemy columns, relationships, and read-only ``@property`` or ``@cached_property`` descriptors:

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

Cursor Pagination
-----------------

Set ``pagination_type="cursor"`` in the controller's filter configuration and return a ``CursorPagination``. Clients pass ``next_cursor`` back as ``?cursor=``; invalid tokens and sort fields return 400:

.. literalinclude:: /examples/litestar/cursor_pagination.py
    :language: python
    :pyobject: ArticleController

See :doc:`/usage/repositories/cursor_pagination` for ordering keys, token signing, and indexing.

Complete Runnable App
---------------------

.. dropdown:: View Complete Litestar Application
    :icon: code

    .. literalinclude:: /examples/litestar/basic_app.py
        :language: python

More Litestar Guides
--------------------

* :doc:`litestar_dtos`: Injecting services, OpenAPI query filters, and auto-generated ``SQLAlchemyDTO`` schemas.
* :doc:`litestar_sessions`: Request transactions, multi-database setups, and server-side session stores.
* :doc:`litestar_storage`: File uploads and cloud or local object storage.
* `Litestar SQLAlchemy Docs <https://docs.litestar.dev/latest/usage/databases/sqlalchemy/>`_: Upstream Litestar framework guide.

.. toctree::
    :titlesonly:
    :hidden:

    Services, Filters & DTOs <litestar_dtos>
    Database & Server Sessions <litestar_sessions>
    File & Object Storage <litestar_storage>
