====================
Litestar Integration
====================

.. seealso::

    :external+litestar:doc:`Litestar's documentation for SQLAlchemy integration <usage/databases/sqlalchemy/index>`

Advanced Alchemy provides first-class integration with Litestar through its SQLAlchemy plugin, which re-exports many of the modules within Advanced Alchemy.

This guide demonstrates building a complete CRUD API for a book management system.

Key Features
------------

- SQLAlchemy plugin for session and transaction management
- Repository pattern for database operations
- Service layer for business logic and data transformation
- Built-in pagination and filtering
- CLI tools for database migrations

Basic Setup
-----------

First, configure the SQLAlchemy plugin with Litestar. The plugin handles database connection, session management, and dependency injection:

.. code-block:: python

    from litestar import Litestar
    from litestar.plugins.sqlalchemy import (
        AsyncSessionConfig,
        SQLAlchemyAsyncConfig,
        SQLAlchemyPlugin,
    )

    session_config = AsyncSessionConfig(expire_on_commit=False)
    sqlalchemy_config = SQLAlchemyAsyncConfig(
        connection_string="sqlite+aiosqlite:///test.sqlite",
        before_send_handler="autocommit",
        session_config=session_config,
        create_all=True,
    )
    alchemy = SQLAlchemyPlugin(config=sqlalchemy_config)


SQLAlchemy Models
-----------------

Define your SQLAlchemy models using Advanced Alchemy's enhanced base classes:

.. code-block:: python

    from __future__ import annotations
    import datetime
    from uuid import UUID
    from sqlalchemy import ForeignKey
    from sqlalchemy.orm import Mapped, mapped_column, relationship
    from advanced_alchemy.base import UUIDAuditBase, UUIDBase


    class AuthorModel(UUIDBase):
        __tablename__ = "author"
        name: Mapped[str]
        dob: Mapped[datetime.date | None]
        books: Mapped[list[BookModel]] = relationship(back_populates="author", lazy="selectin")

    class BookModel(UUIDAuditBase):
        __tablename__ = "book"
        title: Mapped[str]
        author_id: Mapped[UUID] = mapped_column(ForeignKey("author.id"))
        author: Mapped[AuthorModel] = relationship(lazy="joined", innerjoin=True, viewonly=True)

Pydantic Schemas
----------------

Define Pydantic schemas for input validation and response serialization:

.. code-block:: python

    import datetime
    from pydantic import BaseModel, ConfigDict
    from uuid import UUID
    from typing import Optional

    class BaseSchema(BaseModel):
        """Base Schema with ORM mode enabled."""
        model_config = ConfigDict(from_attributes=True)

    class Author(BaseSchema):
        """Author response schema."""
        id: UUID
        name: str
        dob: Optional[datetime.date] = None

    class AuthorCreate(BaseSchema):
        """Schema for creating authors."""
        name: str
        dob: Optional[datetime.date] = None

    class AuthorUpdate(BaseSchema):
        """Schema for updating authors."""
        name: Optional[str] = None
        dob: Optional[datetime.date] = None

    class Book(BaseSchema):
        """Book response schema with author details."""
        id: UUID
        title: str
        author_id: UUID
        author: Author

    class BookCreate(BaseSchema):
        """Schema for creating books."""
        title: str
        author_id: UUID

Repository and Service Layer
----------------------------

Create repository and service classes to interact with the model:

.. code-block:: python

    from typing import AsyncGenerator

    from advanced_alchemy.repository import SQLAlchemyAsyncRepository
    from advanced_alchemy.service import SQLAlchemyAsyncRepositoryService
    from sqlalchemy.ext.asyncio import AsyncSession

    class AuthorService(SQLAlchemyAsyncRepositoryService[AuthorModel]):
        """Author service."""
        class Repo(SQLAlchemyAsyncRepository[AuthorModel]):
            """Author repository."""
            model_type = AuthorModel
        repository_type = Repo


Controllers
-----------

Create a controller class to handle HTTP endpoints. The controller uses dependency injection for services and includes built-in pagination:

.. code-block:: python

    from typing import Annotated

    from litestar import Controller, get, post, patch, delete
    from litestar.di import Provide
    from litestar.params import Dependency, Parameter
    from advanced_alchemy.filters import FilterTypes
    from advanced_alchemy.extensions.litestar.providers import create_service_dependencies
    from advanced_alchemy.service import OffsetPagination

    class AuthorController(Controller):
        """Author CRUD endpoints."""

        path = "/authors"
        dependencies = create_service_dependencies(
            AuthorService,
            key="authors_service",
            filters={"id_filter": UUID, "pagination_type": "limit_offset", "search": "name"}
        )
        tags = ["Authors"]

        @get()
        async def list_authors(
            self,
            authors_service: AuthorService,
            filters: Annotated[list[FilterTypes], Dependency(skip_validation=True)],
        ) -> OffsetPagination[Author]:
            """List all authors with pagination."""
            results, total = await authors_service.list_and_count(*filters)
            return authors_service.to_schema(results, total, filters,schema_type=Author)

        @post()
        async def create_author(
            self,
            authors_service: AuthorService,
            data: AuthorCreate,
        ) -> Author:
            """Create a new author."""
            obj = await authors_service.create(data)
            return authors_service.to_schema(data=obj, schema_type=Author)

        @get(path="/{author_id:uuid}")
        async def get_author(
            self,
            authors_service: AuthorService,
            author_id: UUID = Parameter(
                title="Author ID",
                description="The author to retrieve.",
            ),
        ) -> Author:
            """Get an existing author."""
            obj = await authors_service.get(author_id)
            return authors_service.to_schema(data=obj, schema_type=Author)

        @patch(path="/{author_id:uuid}")
        async def update_author(
            self,
            authors_service: AuthorService,
            data: AuthorUpdate,
            author_id: UUID = Parameter(
                title="Author ID",
                description="The author to update.",
            ),
        ) -> Author:
            """Update an author."""
            obj = await authors_service.update(data=data, item_id=author_id)
            return authors_service.to_schema(obj, schema_type=Author)

        @delete(path="/{author_id:uuid}")
        async def delete_author(
            self,
            authors_service: AuthorService,
            author_id: UUID = Parameter(
                title="Author ID",
                description="The author to delete.",
            ),
        ) -> None:
            """Delete an author from the system."""
            _ = await authors_service.delete(author_id)

Application Configuration
-------------------------

Finally, configure your Litestar application with the plugin and dependencies:

.. code-block:: python

    from litestar import Litestar
    from litestar.di import Provide
    from litestar.plugins.sqlalchemy import (
        AsyncSessionConfig,
        SQLAlchemyAsyncConfig,
        SQLAlchemyPlugin,
    )
    from advanced_alchemy.filters import FilterTypes, LimitOffset

    sqlalchemy_config = SQLAlchemyAsyncConfig(
        connection_string="sqlite+aiosqlite:///test.sqlite",
        before_send_handler="autocommit",
        session_config=AsyncSessionConfig(expire_on_commit=False),
        create_all=True,
    )
    alchemy = SQLAlchemyPlugin(config=sqlalchemy_config)
    app = Litestar(
        route_handlers=[AuthorController],
        plugins=[alchemy]
    )

Database Sessions
-----------------

Sessions in Controllers
^^^^^^^^^^^^^^^^^^^^^^^

You can access the database session from the controller by using the session parameter, which is automatically injected by the SQLAlchemy plugin. The session is automatically committed at the end of the request. If an exception occurs, the session is rolled back:

By default, the session key is named "db_session". You can change this by setting the `session_dependency_key` parameter in the SQLAlchemyAsyncConfig.

.. code-block:: python

    from litestar import Litestar, get
    from litestar.plugins.sqlalchemy import (
        AsyncSessionConfig,
        SQLAlchemyAsyncConfig,
        SQLAlchemyPlugin,
    )

    session_config = AsyncSessionConfig(expire_on_commit=False)
    sqlalchemy_config = SQLAlchemyAsyncConfig(
        connection_string="sqlite+aiosqlite:///test.sqlite",
        before_send_handler="autocommit",
        session_config=session_config,
        create_all=True,
    )  # Create 'db_session' dependency.
    alchemy = SQLAlchemyPlugin(config=sqlalchemy_config)

    @get("/my-endpoint")
    async def my_controller(db_session: AsyncSession) -> str:
        # Access the database session here.
        return "Hello, World!"

    app = Litestar(
        route_handlers=[my_controller],
        plugins=[alchemy],
    )

Sessions in Application
^^^^^^^^^^^^^^^^^^^^^^^

You can use either ``provide_session`` or ``get_session`` to get session instances in your application. Each of these functions are useful for providing sessions in various places within your application, whether you are in the request/response scope or not.

``provide_session`` provides a session instance from request state if it exists, or creates a new session if it doesn't, while ``get_session`` always returns a new instance from the session maker.

- ``provide_session`` is useful in places where you are already in the request/response context such as guards and middleware.

.. code-block:: python

    from litestar import Litestar, get
    from litestar.connection import ASGIConnection
    from litestar.handlers.base import BaseRouteHandler
    from litestar.plugins.sqlalchemy import (
        AsyncSessionConfig,
        SQLAlchemyAsyncConfig,
        SQLAlchemyPlugin,
    )
    from sqlalchemy import text

    session_config = AsyncSessionConfig(expire_on_commit=False)
    sqlalchemy_config = SQLAlchemyAsyncConfig(
        connection_string="sqlite+aiosqlite:///test.sqlite",
        before_send_handler="autocommit",
        session_config=session_config,
        create_all=True,
    )
    alchemy = SQLAlchemyPlugin(config=sqlalchemy_config)


    async def my_guard(connection: ASGIConnection[Any, Any, Any, Any], _: BaseRouteHandler) -> None:
        db_session = sqlalchemy_config.provide_session(connection.app.state, connection.scope)
        a_value = await db_session.execute(text("SELECT 1"))

    @get("/", guards=[my_guard])
    async def hello() -> str:
        return "Hello, world!"


    app = Litestar(
        route_handlers=[hello],
        plugins=[alchemy],
    )

- ``get_session`` is useful anywhere outside of the request lifecycle in your application. This includes command line tasks and background jobs.

.. code-block:: python

    from click import Group
    from litestar import Litestar, get
    from litestar.plugins import CLIPluginProtocol, InitPluginProtocol
    from litestar.plugins.sqlalchemy import (
        AsyncSessionConfig,
        SQLAlchemyAsyncConfig,
        SQLAlchemyPlugin,
    )

    class ApplicationCore(CLIPluginProtocol):

        def on_cli_init(self, cli: Group) -> None:

            @cli.command('check-db-status')
            def check_db_status() -> None:
                import anyio
                async def _check_db_status() -> None:
                    async with sqlalchemy_config.get_session() as db_session:
                        a_value = await db_session.execute(text("SELECT 1"))
                        if a_value.scalar_one() == 1:
                            print("Database is healthy")
                        else:
                            print("Database is not healthy")
                anyio.run(_check_db_status)


    sqlalchemy_config = SQLAlchemyAsyncConfig(
        connection_string="sqlite+aiosqlite:///test.sqlite",
        before_send_handler="autocommit",
        session_config=AsyncSessionConfig(expire_on_commit=False),
        create_all=True,
    )
    alchemy = SQLAlchemyPlugin(config=sqlalchemy_config)
    app = Litestar(plugins=[alchemy, ApplicationCore()])

Database Migrations
-------------------

Advanced Alchemy integrates with Litestar's CLI to provide database migration tools powered by Alembic.  All alembic commands are integrated directly into the Litestar CLI.


Command List
^^^^^^^^^^^^

To get a listing of available commands, run the following:

.. code-block:: bash

    litestar database

.. code-block:: bash

    Usage: app database [OPTIONS] COMMAND [ARGS]...

    Manage SQLAlchemy database components.

    ╭─ Options ────────────────────────────────────────────────────────────────────╮
    │ --help  -h    Show this message and exit.                                    │
    ╰──────────────────────────────────────────────────────────────────────────────╯
    ╭─ Commands ───────────────────────────────────────────────────────────────────╮
    │ downgrade              Downgrade database to a specific revision.            │
    │ drop-all               Drop all tables from the database.                    │
    │ dump-data              Dump specified tables from the database to JSON       │
    │                        files.                                                │
    │ init                   Initialize migrations for the project.                │
    │ make-migrations        Create a new migration revision.                      │
    │ merge-migrations       Merge multiple revisions into a single new revision.  │
    │ show-current-revision  Shows the current revision for the database.          │
    │ stamp-migration        Mark (Stamp) a specific revision as current without   │
    │                        applying the migrations.                              │
    │ upgrade                Upgrade database to a specific revision.              │
    ╰──────────────────────────────────────────────────────────────────────────────╯


Initializing a new project
^^^^^^^^^^^^^^^^^^^^^^^^^^

If you would like to initial set of alembic migrations, you can easily scaffold out new templates to setup a project.

Assuming that you are using the default configuration for the SQLAlchemy configuration, you can run the following to initialize the migrations directory.

.. code-block:: shell-session

    $ litestar database init ./migrations

If you use a different path than `./migrations`, be sure to also set this in your SQLAlchemy config.  For instance, if you'd like to use `./alembic`:

.. code-block:: python

    config = SQLAlchemyAsyncConfig(
        alembic_config=AlembicAsyncConfig(
            script_location="./alembic/",
        ),
    )

And then run the following to initialize the migrations directory:

.. code-block:: shell-session

    $ litestar database init ./alembic

You will now be configured to use the alternate directory for migrations.

Generate New Migrations
^^^^^^^^^^^^^^^^^^^^^^^

Once configured, you can run the following command to auto-generate new alembic migrations:

.. code-block:: shell-session

    $ litestar database make-migrations


Upgrading a Database
^^^^^^^^^^^^^^^^^^^^

You can upgrade a database to the latest version by running the following command:

.. code-block:: shell-session

    $ litestar database upgrade
