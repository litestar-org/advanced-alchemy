Flask Integration
=================

Advanced Alchemy provides seamless integration with Flask applications through its Flask extension.

Installation
------------

The Flask extension is included with Advanced Alchemy by default. No additional installation is required.

Basic Usage
-----------

Here's a basic example of using Advanced Alchemy with Flask:

.. code-block:: python

    from flask import Flask
    from sqlalchemy import select
    from advanced_alchemy.extensions.flask import (
        AdvancedAlchemy,
        SQLAlchemySyncConfig,
        EngineConfig,
    )

    app = Flask(__name__)
    db_config = SQLAlchemySyncConfig(connection_string="sqlite:///local.db", commit_mode="autocommit", create_all=True)
    alchemy = AdvancedAlchemy(db_config, app)

    # Use standard SQLAlchemy session in your routes
    @app.route("/users")
    def list_users():
        db_session = alchemy.get_sync_session()
        users = db_session.execute(select(User))
        return {"users": [user.dict() for user in users.scalars()]}

Multiple Databases
------------------

Advanced Alchemy supports multiple database configurations:

.. note::

    The ``bind_key`` option is used to specify the database to use for a given session.

    When using multiple databases and you do not have at least one database with a ``bind_key`` of ``default``, and exception will be raised when calling ``db.get_session()`` without a bind key.

    This only applies when using multiple configuration.  If you are using a single configuration, the engine will be returned even if the ``bind_key`` is not ``default``.

.. code-block:: python

    configs = [
        SQLAlchemySyncConfig(connection_string="sqlite:///users.db", bind_key="users"),
        SQLAlchemySyncConfig(connection_string="sqlite:///products.db", bind_key="products"),
    ]

    alchemy = AdvancedAlchemy(configs, app)

    # Get session for specific database
    users_session = alchemy.get_sync_session("users")
    products_session = alchemy.get_sync_session("products")

Async Support
-------------

Advanced Alchemy supports async SQLAlchemy with Flask:

.. code-block:: python

    from advanced_alchemy.extensions.flask import (
        AdvancedAlchemy,
        SQLAlchemyAsyncConfig,
    )
    from sqlalchemy import select

    app = Flask(__name__)
    db_config = SQLAlchemyAsyncConfig(connection_string="postgresql+asyncpg://user:pass@localhost/db", create_all=True)
    alchemy = AdvancedAlchemy(db_config, app)

    # Use async session in your routes
    @app.route("/users")
    async def list_users():
        db_session = alchemy.get_async_session()
        users = await db_session.execute(select(User))
        return {"users": [user.dict() for user in users.scalars()]}

You can also safely use an AsyncSession in your routes within a sync context.


.. warning::

    This is experimental and may change in the future.

.. code-block:: python

    @app.route("/users")
    def list_users():
        db_session = alchemy.get_async_session()
        users = alchemy.portal.call(db_session.execute, select(User))
        return {"users": [user.dict() for user in users.scalars()]}

Configuration
-------------

SQLAlchemy Configuration
~~~~~~~~~~~~~~~~~~~~~~~~

Both sync and async configurations support these options:

.. list-table::
   :header-rows: 1

   * - Option
     - Type
     - Description
     - Default
   * - ``engine_config``
     - ``EngineConfig``
     - SQLAlchemy engine configuration
     - Required
   * - ``bind_key``
     - ``str``
     - Key for multiple database support
     - "default"
   * - ``create_all``
     - ``bool``
     - Create tables on startup
     - ``False``
   * - ``commit_mode``
     - ``"autocommit", "autocommit_include_redirect", "manual"``
     - Session commit behavior
     - ``"manual"``

Commit Modes
~~~~~~~~~~~~

The ``commit_mode`` option controls how database sessions are committed:

- ``"manual"`` (default): No automatic commits
- ``"autocommit"``: Commit on successful responses (2xx status codes)
- ``"autocommit_include_redirect"``: Commit on successful responses and redirects (2xx and 3xx status codes)

Services
--------

The ``FlaskServiceMixin`` adds Flask-specific functionality to services:

Here's an example of a service that uses the ``FlaskServiceMixin`` with all CRUD operations, route pagination, and msgspec serialization for JSON

.. code-block:: python

    import datetime
    from typing import Optional
    from uuid import UUID

    from msgspec import Struct
    from flask import Flask
    from sqlalchemy.orm import Mapped, mapped_column
    from advanced_alchemy.extensions.flask import (
        AdvancedAlchemy,
        FlaskServiceMixin,
        service,
        repository,
        SQLAlchemySyncConfig,
        base,
    )

    class Author(base.UUIDBase):
        """Author model."""

        name: Mapped[str]
        dob: Mapped[Optional[datetime.date]]

    class AuthorSchema(Struct):
        """Author schema."""

        name: str
        id: Optional[UUID] = None
        dob: Optional[datetime.date] = None


    class AuthorService(FlaskServiceMixin, service.SQLAlchemySyncRepositoryService[Author]):
        class Repo(repository.SQLAlchemySyncRepository[Author]):
            model_type = Author

        repository_type = Repo

    app = Flask(__name__)
    config = SQLAlchemySyncConfig(connection_string="sqlite:///local.db", commit_mode="autocommit", create_all=True)
    alchemy = AdvancedAlchemy(config, app)


    @app.route("/authors", methods=["GET"])
    def list_authors():
        """List authors with pagination."""
        page, page_size = request.args.get("currentPage", 1, type=int), request.args.get("pageSize", 10, type=int)
        limit_offset = filters.LimitOffset(limit=page_size, offset=page_size * (page - 1))
        service = AuthorService(session=alchemy.get_sync_session())
        results, total = service.list_and_count(limit_offset)
        response = service.to_schema(results, total, filters=[limit_offset], schema_type=AuthorSchema)
        return service.jsonify(response)


    @app.route("/authors", methods=["POST"])
    def create_author():
        """Create a new author."""
        service = AuthorService(session=alchemy.get_sync_session())
        obj = service.create(**request.get_json())
        return service.jsonify(obj)


    @app.route("/authors/<uuid:author_id>", methods=["GET"])
    def get_author(author_id: UUID):
        """Get an existing author."""
        service = AuthorService(session=alchemy.get_sync_session(), load=[Author.books])
        obj = service.get(author_id)
        return service.jsonify(obj)


    @app.route("/authors/<uuid:author_id>", methods=["PATCH"])
    def update_author(author_id: UUID):
        """Update an author."""
        service = AuthorService(session=alchemy.get_sync_session(), load=[Author.books])
        obj = service.update(**request.get_json(), item_id=author_id)
        return service.jsonify(obj)


    @app.route("/authors/<uuid:author_id>", methods=["DELETE"])
    def delete_author(author_id: UUID):
        """Delete an author."""
        service = AuthorService(session=alchemy.get_sync_session())
        service.delete(author_id)
        return "", 204

The ``jsonify`` method is analogous to Flask's ``jsonify`` function.  However, this implementation will serialize with the configured Advanced Alchemy serialize (i.e. Msgspec or Orjson based on installation).

Database Migrations
-------------------

When the extension is configured for Flask, database commands are automatically added to the Flask CLI.  These are the same commands available to you when running the ``alchemy`` standalone CLI.

Here's an example of the commands available to Flask

.. code-block:: bash

    # Initialize migrations
    flask database init

    # Create a new migration
    flask database revision --autogenerate -m "Add users table"

    # Apply migrations
    flask database upgrade

    # Revert migrations
    flask database downgrade

    # Show migration history
    flask database history

    # Show all commands
    flask database --help
