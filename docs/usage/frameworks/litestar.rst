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
    from advanced_alchemy.extensions.litestar import (
        AsyncSessionConfig,
        SQLAlchemyAsyncConfig,
        SQLAlchemyPlugin,
    )

    session_config = AsyncSessionConfig(expire_on_commit=False)
    alchemy_config = SQLAlchemyAsyncConfig(
        connection_string="sqlite+aiosqlite:///test.sqlite",
        before_send_handler="autocommit",
        session_config=session_config,
        create_all=True,
    )
    alchemy = SQLAlchemyPlugin(config=alchemy_config)


SQLAlchemy Models
-----------------

Define your SQLAlchemy models using Advanced Alchemy's enhanced base classes:

.. code-block:: python

    import datetime
    from typing import Optional
    from uuid import UUID
    from sqlalchemy import ForeignKey
    from sqlalchemy.orm import Mapped, mapped_column, relationship
    from advanced_alchemy.extensions.litestar import base


    class AuthorModel(base.UUIDBase):
        __tablename__ = "author"
        name: Mapped[str]
        dob: Mapped[Optional[datetime.date]]
        books: Mapped[list[BookModel]] = relationship(back_populates="author", lazy="selectin")

    class BookModel(base.UUIDAuditBase):
        __tablename__ = "book"
        title: Mapped[str]
        author_id: Mapped[UUID] = mapped_column(ForeignKey("author.id"))
        author: Mapped[AuthorModel] = relationship(lazy="joined", innerjoin=True, viewonly=True)

Pydantic Schemas
----------------

Define Pydantic schemas for input validation and response serialization:

.. code-block:: python

    import datetime
    from pydantic import BaseModel
    from uuid import UUID
    from typing import Optional

    class Author(BaseModel):
        """Author response schema."""
        id: Optional[UUID] = None
        name: str
        dob: Optional[datetime.date] = None

    class AuthorCreate(BaseModel):
        """Schema for creating authors."""
        name: str
        dob: Optional[datetime.date] = None

    class AuthorUpdate(BaseModel):
        """Schema for updating authors."""
        name: Optional[str] = None
        dob: Optional[datetime.date] = None

Repository and Service Layer
----------------------------

Create repository and service classes to interact with the model:

.. code-block:: python

    from advanced_alchemy.extensions.litestar import repository, service

    class AuthorService(service.SQLAlchemyAsyncRepositoryService[AuthorModel]):
        """Author service."""
        class Repo(repository.SQLAlchemyAsyncRepository[AuthorModel]):
            """Author repository."""
            model_type = AuthorModel
        repository_type = Repo


Controllers
-----------

Create a controller class to handle HTTP endpoints. The controller uses dependency injection for services and includes built-in pagination:

.. code-block:: python

    from typing import Annotated

    from litestar import Controller, get, post, patch, delete
    from litestar.params import Dependency, Parameter
    from advanced_alchemy.extensions.litestar import filters, providers, service

    class AuthorController(Controller):
        """Author CRUD endpoints."""

        dependencies = providers.create_service_dependencies(
            AuthorService,
            "authors_service",
            load=[AuthorModel.books],
            filters={"pagination_type": "limit_offset", "id_filter": UUID, "search": "name", "search_ignore_case": True},
        )

        @get(path="/authors")
        async def list_authors(
            self,
            authors_service: AuthorService,
            filters: Annotated[list[filters.FilterTypes], Dependency(skip_validation=True)],
        ) -> service.OffsetPagination[Author]:
            """List all authors with pagination."""
            results, total = await authors_service.list_and_count(*filters)
            return authors_service.to_schema(results, total, filters=filters, schema_type=Author)

        @post(path="/authors")
        async def create_author(
            self,
            authors_service: AuthorService,
            data: AuthorCreate,
        ) -> Author:
            """Create a new author."""
            obj = await authors_service.create(data)
            return authors_service.to_schema(obj, schema_type=Author)

        @get(path="/authors/{author_id:uuid}")
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
            return authors_service.to_schema(obj, schema_type=Author)

        @patch(path="/authors/{author_id:uuid}")
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
            obj = await authors_service.update(data, item_id=author_id, auto_commit=True)
            return authors_service.to_schema(obj, schema_type=Author)

        @delete(path="/authors/{author_id:uuid}")
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
    from advanced_alchemy.extensions.litestar import (
        AsyncSessionConfig,
        SQLAlchemyAsyncConfig,
        SQLAlchemyPlugin,
    )

    alchemy_config = SQLAlchemyAsyncConfig(
        connection_string="sqlite+aiosqlite:///test.sqlite",
        before_send_handler="autocommit",
        session_config=AsyncSessionConfig(expire_on_commit=False),
        create_all=True,
    )

    app = Litestar(
        route_handlers=[AuthorController],
        plugins=[SQLAlchemyPlugin(config=alchemy_config)],
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
    alchemy_config = SQLAlchemyAsyncConfig(
        connection_string="sqlite+aiosqlite:///test.sqlite",
        before_send_handler="autocommit",
        session_config=session_config,
        create_all=True,
    )  # Auto creates 'db_session' dependency.

    @get("/my-endpoint")
    async def my_controller(db_session: AsyncSession) -> str:
        # Access the database session here.
        return "Hello, World!"

    app = Litestar(
        route_handlers=[my_controller],
        plugins=[SQLAlchemyPlugin(config=alchemy_config)],
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
    alchemy_config = SQLAlchemyAsyncConfig(
        connection_string="sqlite+aiosqlite:///test.sqlite",
        before_send_handler="autocommit",
        session_config=session_config,
        create_all=True,
    )
    alchemy = SQLAlchemyPlugin(config=alchemy_config)


    async def my_guard(connection: ASGIConnection[Any, Any, Any, Any], _: BaseRouteHandler) -> None:
        db_session = alchemy_config.provide_session(connection.app.state, connection.scope)
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
                    async with alchemy_config.get_session() as db_session:
                        a_value = await db_session.execute(text("SELECT 1"))
                        if a_value.scalar_one() == 1:
                            print("Database is healthy")
                        else:
                            print("Database is not healthy")
                anyio.run(_check_db_status)


    alchemy_config = SQLAlchemyAsyncConfig(
        connection_string="sqlite+aiosqlite:///test.sqlite",
        before_send_handler="autocommit",
        session_config=AsyncSessionConfig(expire_on_commit=False),
        create_all=True,
    )
    alchemy = SQLAlchemyPlugin(config=alchemy_config)
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

Session Middleware
------------------

Advanced Alchemy provides SQLAlchemy-based session backends for Litestar's server-side session middleware. This allows you to store session data in your existing SQLAlchemy database instead of using external stores like Redis or file-based storage.

Overview
^^^^^^^^

The SQLAlchemy session backend provides:

- **Database persistence**: Session data is stored in your SQLAlchemy database
- **Automatic expiration**: Built-in session expiration handling
- **Both sync and async support**: Works with both sync and async SQLAlchemy configurations
- **UUID-based sessions**: Uses UUIDv7 for session identifiers
- **Timezone-aware timestamps**: Proper handling of session expiration times

Quick Setup
^^^^^^^^^^^

To use the SQLAlchemy session backend, you need to:

1. Create a session model using the provided mixin
2. Configure the SQLAlchemy session backend
3. Register the session middleware with your Litestar application

.. code-block:: python

    from litestar import Litestar
    from litestar.middleware.session.server_side import ServerSideSessionConfig
    from litestar.plugins.sqlalchemy import SQLAlchemyAsyncConfig, SQLAlchemyPlugin
    from advanced_alchemy.extensions.litestar.session import (
        SessionModelMixin,
        SQLAlchemyAsyncSessionBackend,
    )

    # 1. Create your session model
    class UserSession(SessionModelMixin):
        __tablename__ = "user_sessions"

    # 2. Configure SQLAlchemy
    alchemy_config = SQLAlchemyAsyncConfig(
        connection_string="postgresql+asyncpg://user:password@localhost/mydb",
        create_all=True,
    )

    # 3. Configure session backend
    session_config = ServerSideSessionConfig(
        secret="your-secret-key-here",  # Use a secure secret in production
        max_age=3600,  # 1 hour
    )

    # 4. Create the session backend
    session_backend = SQLAlchemyAsyncSessionBackend(
        config=session_config,
        alchemy_config=alchemy_config,
        model=UserSession,
    )

    # 5. Create your Litestar app
    app = Litestar(
        route_handlers=[],
        plugins=[SQLAlchemyPlugin(config=alchemy_config)],
        middleware=[session_config.middleware],
    )

Session Model Configuration
^^^^^^^^^^^^^^^^^^^^^^^^^^^

The session model must inherit from ``SessionModelMixin``, which provides the required fields and database constraints:

.. code-block:: python

    from advanced_alchemy.extensions.litestar.session import SessionModelMixin

    class UserSession(SessionModelMixin):
        __tablename__ = "user_sessions"

        # The mixin provides these fields automatically:
        # - id: UUIDv7 primary key
        # - session_id: String(255) session identifier
        # - data: LargeBinary session data
        # - expires_at: DateTime expiration timestamp
        # - created_at, updated_at: Audit timestamps

The ``SessionModelMixin`` automatically creates:

- A unique constraint on ``session_id`` (or unique index for Spanner)
- An index on ``expires_at`` for efficient cleanup
- Hybrid properties for checking expiration status

Advanced Configuration
^^^^^^^^^^^^^^^^^^^^^^

**Custom Table Arguments**

You can customize table arguments while keeping the mixin's constraints:

.. code-block:: python

    from sqlalchemy import Index
    from advanced_alchemy.extensions.litestar.session import SessionModelMixin

    class UserSession(SessionModelMixin):
        __tablename__ = "user_sessions"

        @declared_attr.directive
        @classmethod
        def __table_args__(cls):
            # Get the mixin's default constraints
            base_args = super().__table_args__()
            # Add your custom indexes/constraints
            return base_args + (
                Index("ix_user_sessions_custom", cls.session_id, cls.created_at),
            )

**Sync vs Async Configuration**

For synchronous SQLAlchemy configurations, use ``SQLAlchemySyncSessionBackend``:

.. code-block:: python

    from litestar.plugins.sqlalchemy import SQLAlchemySyncConfig
    from advanced_alchemy.extensions.litestar.session import SQLAlchemySyncSessionBackend

    # Sync configuration
    alchemy_config = SQLAlchemySyncConfig(
        connection_string="postgresql://user:password@localhost/mydb",
        create_all=True,
    )

    session_backend = SQLAlchemySyncSessionBackend(
        config=session_config,
        alchemy_config=alchemy_config,
        model=UserSession,
    )

**Session Cleanup**

Both session backends provide automatic cleanup of expired sessions:

.. code-block:: python

    # Clean up expired sessions
    await session_backend.delete_expired()  # For async backend
    # or
    await session_backend.delete_expired()  # For sync backend (wrapped with async_)

You can set up periodic cleanup using Litestar's task system or external schedulers.

Using Sessions in Routes
^^^^^^^^^^^^^^^^^^^^^^^^

Once configured, sessions work exactly like other Litestar session backends:

.. code-block:: python

    from litestar import Litestar, get, post
    from litestar.connection import ASGIConnection
    from litestar.response import Response

    @get("/login")
    async def login_form() -> str:
        return "<form method='post'><input name='username'><button>Login</button></form>"

    @post("/login")
    async def login(request: ASGIConnection) -> Response:
        form = await request.form()
        username = form.get("username")

        # Set session data
        request.set_session({"user_id": 123, "username": username})

        return Response("Logged in!", status_code=200)

    @get("/profile")
    async def profile(request: ASGIConnection) -> dict:
        # Access session data
        user_id = request.session.get("user_id")
        username = request.session.get("username")

        if not user_id:
            return {"error": "Not logged in"}

        return {"user_id": user_id, "username": username}

    @post("/logout")
    async def logout(request: ASGIConnection) -> str:
        # Clear session
        request.clear_session()
        return "Logged out!"

Database Schema
^^^^^^^^^^^^^^^

The session table created by ``SessionModelMixin`` has the following structure:

.. code-block:: sql

    CREATE TABLE user_sessions (
        id UUID PRIMARY KEY,
        session_id VARCHAR(255) NOT NULL,
        data BYTEA NOT NULL,
        expires_at TIMESTAMP WITH TIME ZONE,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL,
        updated_at TIMESTAMP WITH TIME ZONE NOT NULL,

        CONSTRAINT uq_user_sessions_session_id UNIQUE (session_id)
    );

    CREATE INDEX ix_user_sessions_expires_at ON user_sessions (expires_at);
    CREATE INDEX ix_user_sessions_session_id_unique ON user_sessions (session_id);

**Session ID Handling**

- Session IDs are limited to 255 characters and automatically truncated if longer
- UUIDv7 is used for the primary key, providing time-ordered identifiers
- Expired sessions are automatically filtered out during retrieval

Security Considerations
^^^^^^^^^^^^^^^^^^^^^^^

**Secret Key Management**

Always use a secure secret key for session encryption:

.. code-block:: python

    import secrets

    # Generate a secure random secret
    secret_key = secrets.token_urlsafe(32)

    session_config = ServerSideSessionConfig(
        secret=secret_key,
        max_age=3600,
        https_only=True,  # Require HTTPS in production
        samesite="strict",  # CSRF protection
    )

**Session Expiration**

Configure appropriate session timeouts:

.. code-block:: python

    session_config = ServerSideSessionConfig(
        secret="your-secret-key",
        max_age=1800,  # 30 minutes
        # Sessions are automatically renewed on each request
    )

**Database Security**

Ensure your database connection uses proper security:

- Use encrypted connections (SSL/TLS)
- Restrict database user permissions
- Regular security updates
- Consider encrypting session data at rest

Performance Optimization
^^^^^^^^^^^^^^^^^^^^^^^^

**Indexing Strategy**

The mixin automatically creates optimal indexes, but you can add application-specific indexes:

.. code-block:: python

    class UserSession(SessionModelMixin):
        __tablename__ = "user_sessions"

        # Add indexes for common query patterns
        __table_args__ = SessionModelMixin.__table_args__ + (
            Index("ix_user_sessions_created_user", "created_at", "session_id"),
        )

**Connection Pooling**

Configure appropriate connection pooling for session workloads:

.. code-block:: python

    from sqlalchemy.pool import QueuePool

    alchemy_config = SQLAlchemyAsyncConfig(
        connection_string="postgresql+asyncpg://user:password@localhost/mydb",
        engine_config=EngineConfig(
            poolclass=QueuePool,
            pool_size=20,
            max_overflow=30,
            pool_pre_ping=True,
        ),
    )

**Cleanup Strategy**

Implement regular cleanup of expired sessions:

.. code-block:: python

    from litestar import Litestar
    from litestar.events import BaseEventEmitter

    async def cleanup_expired_sessions():
        """Background task to clean expired sessions."""
        await session_backend.delete_expired()

    # Schedule cleanup every hour
    app = Litestar(
        # ... your configuration
        on_startup=[cleanup_expired_sessions],
    )

Complete Example
^^^^^^^^^^^^^^^^

Here's a complete working example:

.. code-block:: python

    from litestar import Litestar, get, post
    from litestar.connection import ASGIConnection
    from litestar.middleware.session.server_side import ServerSideSessionConfig
    from litestar.plugins.sqlalchemy import (
        AsyncSessionConfig,
        SQLAlchemyAsyncConfig,
        SQLAlchemyPlugin,
    )
    from litestar.response import Template

    from advanced_alchemy.extensions.litestar.session import (
        SessionModelMixin,
        SQLAlchemyAsyncSessionBackend,
    )

    # Session model
    class WebSession(SessionModelMixin):
        __tablename__ = "web_sessions"

    # Database configuration
    alchemy_config = SQLAlchemyAsyncConfig(
        connection_string="sqlite+aiosqlite:///sessions.db",
        session_config=AsyncSessionConfig(expire_on_commit=False),
        create_all=True,
    )

    # Session configuration
    session_config = ServerSideSessionConfig(
        secret="your-super-secret-key-change-in-production",
        max_age=3600,  # 1 hour
    )

    # Session backend
    session_backend = SQLAlchemyAsyncSessionBackend(
        config=session_config,
        alchemy_config=alchemy_config,
        model=WebSession,
    )

    # Routes
    @get("/")
    async def home(request: ASGIConnection) -> dict:
        username = request.session.get("username")
        return {"message": f"Hello {username}!" if username else "Hello stranger!"}

    @post("/login")
    async def login(request: ASGIConnection) -> dict:
        form = await request.form()
        username = form.get("username")

        if username:
            request.set_session({"username": username, "login_time": "now"})
            return {"message": f"Welcome {username}!"}

        return {"error": "Username required"}

    @post("/logout")
    async def logout(request: ASGIConnection) -> dict:
        request.clear_session()
        return {"message": "Logged out successfully"}

    # Application
    app = Litestar(
        route_handlers=[home, login, logout],
        plugins=[SQLAlchemyPlugin(config=alchemy_config)],
        middleware=[session_config.middleware],
    )

This example provides a complete session-enabled application using SQLAlchemy for session storage.

File Object Storage
===================

Advanced Alchemy provides built-in support for file storage with various backends. Here's how to handle file uploads and storage:

.. code-block:: python

    from typing import Annotated, Any, Optional, Union
    from uuid import UUID

    from litestar import Controller, Litestar, delete, get, patch, post
    from litestar.datastructures import UploadFile
    from litestar.params import Dependency
    from pydantic import BaseModel, Field, computed_field
    from sqlalchemy.orm import Mapped, mapped_column

    from advanced_alchemy.extensions.litestar import (
        AsyncSessionConfig,
        SQLAlchemyAsyncConfig,
        SQLAlchemyPlugin,
        base,
        filters,
        providers,
        repository,
        service,
    )
    from advanced_alchemy.types import FileObject, storages
    from advanced_alchemy.types.file_object.backends.obstore import ObstoreBackend
    from advanced_alchemy.types.file_object.data_type import StoredObject

    # Configure file storage backend
    s3_backend = ObstoreBackend(
        key="local",
        fs="s3://static-files/",
        aws_endpoint="http://localhost:9000",
        aws_access_key_id="minioadmin",
        aws_secret_access_key="minioadmin",
    )
    storages.register_backend(s3_backend)

    # Model with file storage
    class DocumentModel(base.UUIDBase):
        __tablename__ = "document"

        name: Mapped[str]
        file: Mapped[FileObject] = mapped_column(StoredObject(backend="local"))

    # Schema with file URL generation
    class Document(BaseModel):
        id: Optional[UUID] = None
        name: str
        file: Optional[FileObject] = Field(default=None, exclude=True)

        @computed_field
        def file_url(self) -> Optional[Union[str, list[str]]]:
            if self.file is None:
                return None
            return self.file.sign()

    # Service
    class DocumentService(service.SQLAlchemyAsyncRepositoryService[DocumentModel]):
        """Document repository."""

        class Repo(repository.SQLAlchemyAsyncRepository[DocumentModel]):
            """Document repository."""
            model_type = DocumentModel

        repository_type = Repo

    # Controller with file handling
    class DocumentController(Controller):
        path = "/documents"
        dependencies = providers.create_service_dependencies(
            DocumentService,
            "documents_service",
            load=[DocumentModel.file],
            filters={
                "pagination_type": "limit_offset",
                "id_filter": UUID,
                "search": "name",
                "search_ignore_case": True
            },
        )

        @get(path="/", response_model=service.OffsetPagination[Document])
        async def list_documents(
            self,
            documents_service: DocumentService,
            filters: Annotated[list[filters.FilterTypes], Dependency(skip_validation=True)],
        ) -> service.OffsetPagination[Document]:
            results, total = await documents_service.list_and_count(*filters)
            return documents_service.to_schema(results, total, filters=filters, schema_type=Document)

        @post(path="/")
        async def create_document(
            self,
            documents_service: DocumentService,
            name: str,
            file: Annotated[Optional[UploadFile], None] = None,
        ) -> Document:
            obj = await documents_service.create(
                DocumentModel(
                    name=name,
                    file=FileObject(
                        backend="local",
                        filename=file.filename or "uploaded_file",
                        content_type=file.content_type,
                        content=await file.read(),
                    )
                    if file
                    else None,
                )
            )
            return documents_service.to_schema(obj, schema_type=Document)

        @get(path="/{document_id:uuid}")
        async def get_document(
            self,
            documents_service: DocumentService,
            document_id: UUID,
        ) -> Document:
            obj = await documents_service.get(document_id)
            return documents_service.to_schema(obj, schema_type=Document)

        @patch(path="/{document_id:uuid}")
        async def update_document(
            self,
            documents_service: DocumentService,
            document_id: UUID,
            name: Optional[str] = None,
            file: Annotated[Optional[UploadFile], None] = None,
        ) -> Document:
            update_data: dict[str, Any] = {}
            if name is not None:
                update_data["name"] = name
            if file is not None:
                update_data["file"] = FileObject(
                    backend="local",
                    filename=file.filename or "uploaded_file",
                    content_type=file.content_type,
                    content=await file.read(),
                )

            obj = await documents_service.update(update_data, item_id=document_id)
            return documents_service.to_schema(obj, schema_type=Document)

        @delete(path="/{document_id:uuid}")
        async def delete_document(
            self,
            documents_service: DocumentService,
            document_id: UUID,
        ) -> None:
            _ = await documents_service.delete(document_id)

    # Application setup
    alchemy_config = SQLAlchemyAsyncConfig(
        connection_string="sqlite+aiosqlite:///test.sqlite",
        session_config=AsyncSessionConfig(expire_on_commit=False),
        before_send_handler="autocommit",
        create_all=True,
    )
    app = Litestar(
        route_handlers=[DocumentController],
        plugins=[SQLAlchemyPlugin(config=alchemy_config)]
    )

File storage features:

- **Multiple backends**: Local filesystem, S3, GCS, Azure and other object storage
- **Automatic URL signing**: Generate secure, time-limited URLs for file access
- **Content type detection**: Automatic MIME type handling
- **File validation**: Built-in validation for file types and sizes
- **Metadata storage**: Store file metadata alongside binary data

**Supported Storage Backends**:

- **Local filesystem**: For development and simple deployments
- **Cloud Storage Integration**: For production object storage
- **Memory**: For testing and temporary storage
- **Custom backends**: Implement your own storage backend

Alternative Patterns
====================

.. collapse:: Repository-Only Pattern

    If for some reason you don't want to use the service layer abstraction, you can use repositories directly. This approach removes the services abstraction, but still offers the benefits of Advanced Alchemy's repository features:

    .. code-block:: python

        from __future__ import annotations

        import datetime
        from typing import TYPE_CHECKING, Optional
        from uuid import UUID

        from litestar import Controller, Litestar, delete, get, patch, post
        from litestar.di import Provide
        from litestar.pagination import OffsetPagination
        from litestar.params import Parameter
        from pydantic import BaseModel, TypeAdapter
        from sqlalchemy import ForeignKey
        from sqlalchemy.orm import Mapped, mapped_column, relationship

        from advanced_alchemy.base import UUIDAuditBase, UUIDBase
        from advanced_alchemy.config import AsyncSessionConfig
        from advanced_alchemy.extensions.litestar.plugins import SQLAlchemyAsyncConfig, SQLAlchemyPlugin
        from advanced_alchemy.filters import LimitOffset
        from advanced_alchemy.repository import SQLAlchemyAsyncRepository

        if TYPE_CHECKING:
            from sqlalchemy.ext.asyncio import AsyncSession

        class BaseModel(BaseModel):
            """Extend Pydantic's BaseModel to enable ORM mode"""
            model_config = {"from_attributes": True}

        # Models
        class AuthorModel(UUIDBase):
            __tablename__ = "author"
            name: Mapped[str]
            dob: Mapped[Optional[datetime.date]]
            books: Mapped[list[BookModel]] = relationship(back_populates="author", lazy="noload")

        # Repository
        class AuthorRepository(SQLAlchemyAsyncRepository[AuthorModel]):
            """Author repository."""
            model_type = AuthorModel

        # Dependency providers
        async def provide_authors_repo(db_session: AsyncSession) -> AuthorRepository:
            """This provides the default Authors repository."""
            return AuthorRepository(session=db_session)

        async def provide_author_details_repo(db_session: AsyncSession) -> AuthorRepository:
            """Repository with eager loading for author details."""
            return AuthorRepository(load=[AuthorModel.books], session=db_session)

        def provide_limit_offset_pagination(
            current_page: int = Parameter(ge=1, query="currentPage", default=1, required=False),
            page_size: int = Parameter(query="pageSize", ge=1, default=10, required=False),
        ) -> LimitOffset:
            """Add offset/limit pagination."""
            return LimitOffset(page_size, page_size * (current_page - 1))

        # Controller
        class AuthorController(Controller):
            """Author CRUD using repository pattern."""

            dependencies = {"authors_repo": Provide(provide_authors_repo)}

            @get(path="/authors")
            async def list_authors(
                self,
                authors_repo: AuthorRepository,
                limit_offset: LimitOffset,
            ) -> OffsetPagination[Author]:
                """List authors with pagination."""
                results, total = await authors_repo.list_and_count(limit_offset)
                type_adapter = TypeAdapter(list[Author])
                return OffsetPagination[Author](
                    items=type_adapter.validate_python(results),
                    total=total,
                    limit=limit_offset.limit,
                    offset=limit_offset.offset,
                )

            @post(path="/authors")
            async def create_author(
                self,
                authors_repo: AuthorRepository,
                data: AuthorCreate,
            ) -> Author:
                """Create a new author."""
                obj = await authors_repo.add(
                    AuthorModel(**data.model_dump(exclude_unset=True, exclude_none=True)),
                )
                await authors_repo.session.commit()
                return Author.model_validate(obj)

            @get(
                path="/authors/{author_id:uuid}",
                dependencies={"authors_repo": Provide(provide_author_details_repo)}
            )
            async def get_author(
                self,
                authors_repo: AuthorRepository,
                author_id: UUID = Parameter(title="Author ID", description="The author to retrieve."),
            ) -> Author:
                """Get an existing author with details."""
                obj = await authors_repo.get(author_id)
                return Author.model_validate(obj)

            @patch(
                path="/authors/{author_id:uuid}",
                dependencies={"authors_repo": Provide(provide_author_details_repo)},
            )
            async def update_author(
                self,
                authors_repo: AuthorRepository,
                data: AuthorUpdate,
                author_id: UUID = Parameter(title="Author ID", description="The author to update."),
            ) -> Author:
                """Update an author."""
                raw_obj = data.model_dump(exclude_unset=True, exclude_none=True)
                raw_obj.update({"id": author_id})
                obj = await authors_repo.update(AuthorModel(**raw_obj))
                await authors_repo.session.commit()
                return Author.model_validate(obj)

            @delete(path="/authors/{author_id:uuid}")
            async def delete_author(
                self,
                authors_repo: AuthorRepository,
                author_id: UUID = Parameter(title="Author ID", description="The author to delete."),
            ) -> None:
                """Delete an author from the system."""
                _ = await authors_repo.delete(author_id)
                await authors_repo.session.commit()

        # Application setup
        session_config = AsyncSessionConfig(expire_on_commit=False)
        alchemy_config = SQLAlchemyAsyncConfig(
            connection_string="sqlite+aiosqlite:///test.sqlite",
            session_config=session_config,
            create_all=True,
        )
        sqlalchemy_plugin = SQLAlchemyPlugin(config=alchemy_config)

        app = Litestar(
            route_handlers=[AuthorController],
            plugins=[sqlalchemy_plugin],
            dependencies={"limit_offset": Provide(provide_limit_offset_pagination, sync_to_thread=False)},
        )

    This pattern is useful when you:

    - Need direct control over database transactions
    - Want to avoid the service layer abstraction
    - Have complex repository logic that doesn't fit the service pattern
    - Are building a smaller application with simpler data access patterns
