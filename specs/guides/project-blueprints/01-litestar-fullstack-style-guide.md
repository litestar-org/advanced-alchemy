# Guide: Litestar Full-Stack Style Guide

This guide provides a comprehensive overview of the architectural patterns and development practices used in the `litestar-fullstack` reference project. It is intended to be a "true north" for building scalable, maintainable, and robust applications with Litestar and `advanced-alchemy`. An AI agent should be able to use this guide to scaffold a new project that adheres to these established best practices.

## 1. Project Philosophy

The core philosophy is to create a clean, scalable, and feature-first architecture. This is achieved through:

- **Strong Typing:** Leveraging Python's type system for robust and self-documenting code.
- **Dependency Injection:** Using DI to decouple components and facilitate testing.
- **Domain-Driven Structure:** Organizing code by feature/domain to keep related logic together.
- **Centralized Configuration:** Using a central plugin (`ApplicationCore`) to manage application setup.
- **Declarative Tooling:** Defining all dependencies, linting, and formatting rules in `pyproject.toml`.

## 2. Dependency Management with `uv`

The project uses `uv` for Python package and environment management. It's fast, reliable, and integrates seamlessly with `pyproject.toml`.

- **Installation:** All dependencies, including optional groups for `docs`, `linting`, and `test`, are defined in `pyproject.toml`. A fresh environment is created by running `uv sync`.
- **Locking:** A `uv.lock` file is used to pin exact dependency versions, ensuring reproducible builds.
- **Execution:** All commands and scripts are run within the virtual environment using `uv run`.

**Example `pyproject.toml` dependencies:**

```toml
[project]
dependencies = [
  "litestar[jinja,jwt,structlog]",
  "advanced-alchemy[uuid,obstore]",
  "psycopg[pool,binary]",
  "python-dotenv",
  "pwdlib[argon2]",
  "litestar-saq",
  "litestar-vite",
  "litestar-granian[uvloop]",
  "httpx-oauth",
]

[dependency-groups]
dev = [{ include-group = "docs" }, { include-group = "linting" }, { include-group = "test" }]
docs = [
  "sphinx",
  # ... other docs dependencies
]
linting = [
  "pre-commit>=3.4.0",
  "mypy>=1.5.1",
  "ruff>=0.0.287",
  # ... other linting dependencies
]
test = [
  "pytest",
  # ... other test dependencies
]
```

## 3. Tooling and Quality Assurance

All tooling is configured declaratively in `pyproject.toml` and executed via a `Makefile` for convenience.

### `Makefile`

The `Makefile` provides a simple, consistent interface for common development tasks.

- `make install`: Sets up the complete development environment.
- `make lint`: Runs all linters and type checkers.
- `make fix`: Applies automatic formatting fixes.
- `make test`: Runs the test suite.
- `make coverage`: Runs tests and generates a coverage report.
- `make docs`: Builds the project documentation.

### `ruff` for Linting and Formatting

`ruff` is used for all linting and formatting, providing a fast and unified experience.

- **Configuration:** All rules, target version, and file exclusions are defined in the `[tool.ruff]` section of `pyproject.toml`.
- **Imports:** `ruff` is configured to enforce absolute imports (`ban-relative-imports = "all"`) and sort them, with first-party modules explicitly defined.

### `mypy` and `pyright` for Type Checking

Both `mypy` and `pyright` are used for static type checking, catching potential errors before runtime.

- **Configuration:** Both are configured in their respective `[tool.mypy]` and `[tool.pyright]` sections of `pyproject.toml`.
- **Strictness:** The configuration is set to be strict, enforcing complete and correct type annotations.

## 4. Configuration Management

Application configuration is split into two parts: environment-based settings and static application configuration.

### Environment Settings (`lib/settings.py`)

- **Pattern:** A `Settings` dataclass aggregates multiple domain-specific settings dataclasses (e.g., `DatabaseSettings`, `ServerSettings`).
- **Environment Loading:** A helper function (`get_env`) reads values from environment variables, with type casting and default values. The `Settings.from_env()` class method loads these from a `.env` file for local development.
- **Usage:** A cached function `get_settings()` provides a singleton `Settings` instance to the rest of the application.

**Example `lib/settings.py`:**

```python
from dataclasses import dataclass, field
from functools import lru_cache

# ... other imports

@dataclass
class DatabaseSettings:
    URL: str = field(default_factory=get_env("DATABASE_URL", ...))
    # ... other database settings

@dataclass
class AppSettings:
    NAME: str = "My App"
    SECRET_KEY: str = field(default_factory=get_env("SECRET_KEY", ...))
    # ... other app settings

@dataclass
class Settings:
    app: AppSettings = field(default_factory=AppSettings)
    db: DatabaseSettings = field(default_factory=DatabaseSettings)

    @classmethod
    @lru_cache(maxsize=1, typed=True)
    def from_env(cls, dotenv_filename: str = ".env") -> "Settings":
        # ... logic to load .env file ...
        return Settings(...)

def get_settings() -> Settings:
    return Settings.from_env()
```

## 5. Application Architecture

The application follows a clean, plugin-driven architecture centered around a core configuration plugin.

### Entrypoint (`server/asgi.py`)

The ASGI entrypoint is a simple factory function `create_app()` that instantiates the `Litestar` application and registers the main `ApplicationCore` plugin.

```python
from litestar import Litestar
from app.server.core import ApplicationCore

def create_app() -> Litestar:
    """Create ASGI application."""
    return Litestar(plugins=[ApplicationCore()])
```

### CLI Entrypoint (`pyproject.toml`)

The `pyproject.toml` file defines the entrypoint for the application's command-line interface.

```toml
[project.scripts]
app = "app.__main__:run_cli"
```

### Core Configuration (`server/core.py`)

The `ApplicationCore` class inherits from Litestar's `InitPluginProtocol` and `CLIPluginProtocol`. It acts as the central hub for configuring the entire application.

- **`on_app_init`:** This method is where all major components are wired together:
    - Plugins are registered.
    - Route handlers (controllers) are added.
    - Global dependencies are defined.
    - Exception handlers are set.
    - OpenAPI configuration is created.
    - The `signature_namespace` is populated with common types and services for DI.
- **`on_cli_init`:** This method registers custom CLI command groups, including the `database_group` from `advanced-alchemy`.

### Plugin Organization (`server/plugins.py`)

To keep the `ApplicationCore` clean, all plugin instances are configured and instantiated in a dedicated `plugins.py` file.

```python
# In server/plugins.py
from advanced_alchemy.extensions.litestar import SQLAlchemyPlugin
from litestar_vite import VitePlugin
# ... other plugin imports

from app import config # The static config module

vite = VitePlugin(config=config.vite)
alchemy = SQLAlchemyPlugin(config=config.alchemy)
# ... other plugin instances
```

This modular approach creates a highly organized and scalable application structure that is easy to understand and extend.

## 6. Domain-Driven Structure

The application's source code is organized by domain or feature. Each feature (e.g., `accounts`, `teams`, `tags`) is a self-contained module that includes its own models, schemas, services, and controllers. This keeps related logic colocated, making the codebase easier to navigate and maintain.

### Models (`db/models/`)

- **Responsibility:** Define the database table structure and relationships using SQLAlchemy's declarative ORM.
- **Pattern:** Models inherit from `advanced-alchemy`'s `UUIDAuditBase`, which provides primary key, audit columns (`created_at`, `updated_at`), and `BIGINT` support out of the box. Relationships are defined with `lazy="selectin"` loading to prevent N+1 query issues.

**Example: `db/models/user.py`**

```python
from advanced_alchemy.base import UUIDAuditBase
from sqlalchemy.orm import Mapped, mapped_column, relationship

class User(UUIDAuditBase):
    __tablename__ = "user_account"
    
    email: Mapped[str] = mapped_column(unique=True, index=True)
    name: Mapped[str | None]
    hashed_password: Mapped[str | None]
    is_active: Mapped[bool] = mapped_column(default=True)
    
    roles: Mapped[list["UserRole"]] = relationship(
        back_populates="user",
        lazy="selectin",
    )
```

### Schemas (`schemas/`)

- **Responsibility:** Define the data contracts for your API. They are used for request body validation and serialization of response data.
- **Pattern:** Schemas are defined using `msgspec.Struct` for high performance. A `CamelizedBaseStruct` is used as a base to automatically convert between Python's `snake_case` and JSON's `camelCase`. Validation logic is placed in the `__post_init__` method.

**Example: `schemas/accounts.py`**

```python
import msgspec
from app.lib.validation import validate_email, validate_password
from app.schemas.base import CamelizedBaseStruct

class AccountRegister(CamelizedBaseStruct):
    email: str
    password: str
    name: str | None = None

    def __post_init__(self) -> None:
        """Validate fields."""
        self.email = validate_email(self.email)
        self.password = validate_password(self.password)
```

### Services (`services/`)



-   **Responsibility:** Contain the core business logic of the application. They orchestrate data access operations and interact with the repository layer.

-   **Pattern:** Services inherit from `advanced-alchemy`'s `SQLAlchemyAsyncRepositoryService`. The inline repository pattern is used for simplicity. Custom methods are added to encapsulate business logic (e.g., `authenticate`, `verify_email`).



**Example: `services/_users.py`**

```python

from litestar.exceptions import PermissionDeniedException

from advanced_alchemy import repository, service

from app.db import models as m

from app.lib import crypt



class UserService(service.SQLAlchemyAsyncRepositoryService[m.User]):

    """Handles database operations for users."""

    class Repo(repository.SQLAlchemyAsyncRepository[m.User]):

        model_type = m.User

    repository_type = Repo



    async def authenticate(self, username: str, password: str) -> m.User:

        """Authenticate a user."""

        db_obj = await self.get_one_or_none(email=username)

        if not db_obj or not await crypt.verify_password(password, db_obj.hashed_password):

            raise PermissionDeniedException("Invalid credentials")

        return db_obj

```



### Dependency Injection Providers (`services/providers.py`)



-   **Responsibility:** Create functions that instantiate services with a framework-managed database session. This is the crucial link between the framework's session management and your application's services.

-   **Pattern:** Create an `async` function for each service. This function should type-hint `AsyncSession` as a parameter, which Litestar will inject. The function then instantiates and returns the service with that session.



**Example: `services/providers.py`**

```python

from sqlalchemy.ext.asyncio import AsyncSession

from ._users import UserService

from ._roles import RoleService



async def provide_users_service(db_session: AsyncSession) -> UserService:

    """Constructs a UserService with a database session."""

    return UserService(session=db_session)



async def provide_roles_service(db_session: AsyncSession) -> RoleService:

    """Constructs a RoleService with a database session."""

    return RoleService(session=db_session)

```



### Controllers (`server/routes/`)



-   **Responsibility:** Define the API endpoints and handle the HTTP request/response cycle.

-   **Pattern:** Controllers are kept lean. Their primary job is to receive requests, call the appropriate service method with the validated data, and return the result. All business logic is delegated to the service layer. Dependencies (like services) are injected using `Provide` with the correct provider function.



**Example: `server/routes.py` (AccessController)**

```python

from litestar.controller import Controller

from litestar.di import Provide

from litestar.handlers import post

from app import schemas as s

from app.services import UserService, provide_users_service



class AccessController(Controller):

    """Handles login and registration."""

    path = "/access"

    dependencies = {"users_service": Provide(provide_users_service)}



    @post("/register")

    async def signup(self, users_service: UserService, data: s.AccountRegister) -> s.User:

        """Register a new account."""

        user_obj = await users_service.create(data.to_dict())

        return users_service.to_schema(user_obj, s.User)

```
## 7. Practical Example: Authentication Flow

To make these patterns concrete, let's walk through a complete authentication and registration flow.

### The `UserService` with Business Logic

The `UserService` is extended with an `authenticate` method and a `to_model_on_create` hook for password hashing. This encapsulates all user-specific business logic.

```python
# In services/_users.py

from advanced_alchemy import service, repository
from app.db import models as m
from app.lib import crypt  # Your password hashing utility

class UserService(service.SQLAlchemyAsyncRepositoryService[m.User]):
    """Handles database operations for users."""
    class Repo(repository.SQLAlchemyAsyncRepository[m.User]):
        model_type = m.User
    repository_type = Repo

    async def to_model_on_create(self, data: service.ModelDictT[m.User]) -> service.ModelDictT[m.User]:
        """Hash the password before creating the user."""
        if "password" in data and isinstance(data, dict):
            data["hashed_password"] = await crypt.get_password_hash(data.pop("password"))
        return data

    async def authenticate(self, username: str, password: str | bytes) -> m.User:
        """Authenticate a user."""
        db_obj = await self.get_one_or_none(email=username)
        
        if not db_obj or not db_obj.hashed_password or not await crypt.verify_password(password, db_obj.hashed_password):
            raise PermissionDeniedException("User not found or password invalid")
        
        if not db_obj.is_active:
            raise PermissionDeniedException("User account is inactive")
            
        return db_obj
```

### The `AccessController` for API Endpoints

The controller handles the HTTP requests for login and registration, delegating all logic to the `UserService`.

```python
# In server/routes/access.py

from litestar.controller import Controller
from litestar.di import Provide
from litestar.handlers import post
from app import schemas as s, security
from app.services import UserService, RoleService, provide_users_service, provide_roles_service

class AccessController(Controller):
    """Handles the login and registration of the application."""
    path = "/access"
    dependencies = {
        "users_service": Provide(provide_users_service),
        "roles_service": Provide(provide_roles_service),
    }

    @post("/login")
    async def login(self, users_service: UserService, data: s.UserLogin) -> s.Token:
        """Authenticate a user and return a JWT token."""
        user = await users_service.authenticate(data.username, data.password)
        return security.auth.login(user.email)

    @post("/signup")
    async def signup(
        self,
        users_service: UserService,
        roles_service: RoleService,
        data: s.UserSignup,
    ) -> s.User:
        """Register a new account."""
        user_data = data.to_dict()
        
        # Assign a default role
        role_obj = await roles_service.get_one_or_none(name="Application Access")
        if role_obj:
            user_data["role_id"] = role_obj.id
            
        user = await users_service.create(user_data)
        return users_service.to_schema(user, schema_type=s.User)
```

### The User Provider for Authenticated Requests

This dependency provider is used by the authentication middleware. It takes a decoded JWT token, uses the `UserService` to fetch the user from the database, and attaches the user object to the request. This ensures that every authenticated request has a fresh, trusted user object.

```python
# In server/security.py

from sqlalchemy import select
from sqlalchemy.orm import joinedload, load_only
from app import services, models as m, config

async def current_user_from_token(token: s.Token) -> m.User | None:
    """Retrieve the user from the database based on the token."""
    async with services.UserService.new(
        config=config.alchemy,
        statement=select(m.User).options(
            load_only(m.User.id, m.User.email, m.User.is_active),
            joinedload(m.User.roles).joinedload(m.UserRole.role)
        )
    ) as users_service:
        user = await users_service.get_one_or_none(email=token.sub)
        if user and user.is_active:
            return user
    return None
```

```
