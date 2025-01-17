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
    from advanced_alchemy.extensions.flask import (
        AdvancedAlchemy,
        SQLAlchemySyncConfig,
        EngineConfig,
    )

    app = Flask(__name__)

    db_config = SQLAlchemySyncConfig(
        engine_config=EngineConfig(
            url="sqlite:///db.sqlite3",
        ),
        commit_mode="autocommit",
    )

    db = AdvancedAlchemy(config=db_config)
    db.init_app(app)

    # Use in your routes
    @app.route("/users")
    def list_users():
        session = db.get_session()
        users = session.query(User).all()
        return {"users": [user.dict() for user in users]}

Multiple Databases
------------------

Advanced Alchemy supports multiple database configurations:

.. note::

    The ``bind_key`` option is used to specify the database to use for a given session.

    When using multiple databases and you do not have at least one database with a ``bind_key`` of ``default``, and exception will be raised when calling ``db.get_session()`` without a bind key.

    This only applies when using multiple configuration.  If you are using a single configuration, the engine will be returned even if the ``bind_key`` is not ``default``.

.. code-block:: python

    configs = [
        SQLAlchemySyncConfig(
            engine_config=EngineConfig(url="sqlite:///users.db"),
            bind_key="users",
        ),
        SQLAlchemySyncConfig(
            engine_config=EngineConfig(url="sqlite:///products.db"),
            bind_key="products",
        ),
    ]

    db = AdvancedAlchemy(config=configs)
    db.init_app(app)

    # Get session for specific database
    users_session = db.get_session("users")
    products_session = db.get_session("products")

Async Support
-------------

Advanced Alchemy supports async SQLAlchemy with Flask:

.. code-block:: python

    from advanced_alchemy.extensions.flask import (
        AdvancedAlchemy,
        SQLAlchemyAsyncConfig,
    )

    db_config = SQLAlchemyAsyncConfig(
        engine_config=EngineConfig(
            url="postgresql+asyncpg://user:pass@localhost/db",
        ),
        create_all=True,
    )

    db = AdvancedAlchemy(config=db_config)
    db.init_app(app)

    # Use async session in your routes
    @app.route("/users")
    async def list_users():
        session = db.get_session()
        users = await session.execute(select(User))
        return {"users": [user.dict() for user in users.scalars()]}

You can also safely use an AsyncSession in your routes within a sync context:

.. code-block:: python

    @app.route("/users")
    def list_users():
        session = db.get_session()
        users = session.execute(select(User))
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

.. code-block:: python

    from advanced_alchemy.service import SQLAlchemyAsyncRepositoryService
    from advanced_alchemy.extensions.flask import FlaskServiceMixin

    class UserService(
        FlaskServiceMixin,
        SQLAlchemyAsyncRepositoryService[User],
    ):
        class Repo(repository.SQLAlchemySyncRepository[User]):
            model_type = User

        repository_type = Repo

        def get_user_response(self, user_id: int) -> Response:
            user = self.get(user_id)
            return self.jsonify(user.dict())

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
