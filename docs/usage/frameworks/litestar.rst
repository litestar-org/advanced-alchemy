====================
Litestar Integration
====================

Advanced Alchemy provides first-class integration with Litestar through its SQLAlchemy plugin, repository, and service patterns. This guide demonstrates building a complete CRUD API for a book management system.

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

    from datetime import date
    from uuid import UUID
    from sqlalchemy import ForeignKey
    from sqlalchemy.orm import Mapped, mapped_column, relationship
    from litestar.plugins.sqlalchemy.base import UUIDAuditBase, UUIDBase


    class AuthorModel(UUIDBase):
        __tablename__ = "author"
        name: Mapped[str]
        dob: Mapped[date | None]
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

    from datetime import date
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
        dob: Optional[date] = None

    class AuthorCreate(BaseSchema):
        """Schema for creating authors."""
        name: str
        dob: Optional[date] = None

    class AuthorUpdate(BaseSchema):
        """Schema for updating authors."""
        name: Optional[str] = None
        dob: Optional[date] = None

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

Create repository, service classes, and dependency injection provider function:

.. code-block:: python

    from sqlalchemy.ext.asyncio import AsyncSession
    from advanced_alchemy.repository import SQLAlchemyAsyncRepository
    from advanced_alchemy.service import SQLAlchemyAsyncRepositoryService
    from typing import AsyncGenerator

    class AuthorRepository(SQLAlchemyAsyncRepository[AuthorModel]):
        """Author repository."""
        model_type = AuthorModel

    class AuthorService(SQLAlchemyAsyncRepositoryService[AuthorModel]):
        """Author service."""
        repository_type = AuthorRepository

    async def provide_authors_service(db_session: AsyncSession) -> AsyncGenerator[AuthorService, None]:
        """This provides the default Authors repository."""
        async with AuthorService.new(session=db_session) as service:
            yield service

Controllers
-----------

Create a controller class to handle HTTP endpoints. The controller uses dependency injection for services and includes built-in pagination:

.. code-block:: python

    from litestar import Controller, get, post, patch, delete
    from litestar.di import Provide
    from litestar.params import Parameter
    from litestar.pagination import OffsetPagination
    from litestar.repository.filters import LimitOffset

    class AuthorController(Controller):
        """Author CRUD endpoints."""

        path = "/authors"
        dependencies = {"authors_service": Provide(provide_authors_service)}
        tags = ["Authors"]

        @get()
        async def list_authors(
            self,
            authors_service: AuthorService,
            limit_offset: LimitOffset,
        ) -> OffsetPagination[Author]:
            """List all authors with pagination."""
            results, total = await authors_service.list_and_count(limit_offset)
            return authors_service.to_schema(
                data=results,
                total=total,
                filters=[limit_offset],
                schema_type=Author,
            )

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
    from litestar.plugins.sqlalchemy.filters import FilterTypes, LimitOffset
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


    def provide_limit_offset_pagination(
        current_page: int = Parameter(ge=1, query="currentPage", default=1, required=False),
        page_size: int = Parameter(
            query="pageSize",
            ge=1,
            default=10,
            required=False,
        ),
    ) -> FilterTypes:
        """Add offset/limit pagination."""
        return LimitOffset(page_size, page_size * (current_page - 1))

    app = Litestar(
        route_handlers=[AuthorController],
        plugins=[alchemy],
        dependencies={"limit_offset": Provide(provide_limit_offset_pagination, sync_to_thread=False)},
    )

Database Sessions
-----------------

Sessions in Controllers
^^^^^^^^^^^^^^^^^^^^^^^

You can access the database session from the controller by using the `db_session` parameter, which is automatically injected by the SQLAlchemy plugin. The session is automatically committed at the end of the request. If an exception occurs, the session is rolled back:

.. code-block:: python

    from litestar import Litestar, get
    from advanced_alchemy.extensions.litestar import (
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

Sessions in Middleware
^^^^^^^^^^^^^^^^^^^^^^

Dependency injection is not available in middleware. Instead, you can create a new session using the `provide_session` method:

.. code-block:: python

    from litestar import Litestar
    from litestar.types import ASGIApp, Scope, Receive, Send
    from advanced_alchemy.extensions.litestar import (
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

    def middleware_factory(app: ASGIApp) -> ASGIApp:
        async def my_middleware(scope: Scope, receive: Receive, send: Send) -> None:
            # NOTE: You can also access the app state from `ASGIConnection`.
            db_session = await alchemy.provide_session(scope["app"].state, scope)
            # Access the database session here.
            await db_session.close()
            ...
            await app(scope, receive, send)
    return my_middleware

    app = Litestar(
        route_handlers=[...],
        middleware=[middleware_factory],
        plugins=[alchemy]
    )

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

Assuming that you are using the default configuration for the SQLAlchemy configuration, you can run the following.

.. code-block:: bash

    # Initialize migrations directory
    litestar database init ./migrations

If you use a different path than `./migrations`, be sure to also set this in your SQLAlchemy config.  For instance, if you'd like to use `./alembic`:

.. code-block:: python

    config = SQLAlchemyAsyncConfig(
        alembic_config=AlembicAsyncConfig(
            script_location="./alembic/",
        ),
    )

And then run the following:

.. code-block:: bash

    # Initialize migrations directory
    litestar database init ./alembic

You will now be configured to use the alternate directory for migrations.

Generate New Migrations
^^^^^^^^^^^^^^^^^^^^^^^

Once configured, you can run the following command to auto-generate new alembic migrations:

.. code-block:: bash

    # Create a new migration
    litestar database make-migrations


Upgrading a Database
^^^^^^^^^^^^^^^^^^^^

You can upgrade a database to the latest version by running the following command:

.. code-block:: bash

    litestar database upgrade
