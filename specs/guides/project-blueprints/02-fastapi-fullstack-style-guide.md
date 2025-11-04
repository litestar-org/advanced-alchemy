# Guide: FastAPI Full-Stack Style Guide

This guide provides a comprehensive overview of the architectural patterns and development practices for building a full-stack application with FastAPI and `advanced-alchemy`. It mirrors the "true north" principles of the `litestar-fullstack` project, adapting them to FastAPI's idioms and patterns. An AI agent should be able to use this guide to scaffold a new project that adheres to these established best practices.

## 1. Project Philosophy

The core philosophy is to create a clean, scalable, and feature-first architecture. This is achieved through:
-   **Strong Typing:** Leveraging Python's type system for robust and self-documenting code.
-   **Dependency Injection:** Using DI to decouple components and facilitate testing.
-   **Domain-Driven Structure:** Organizing code by feature/domain to keep related logic together.
-   **Centralized Configuration:** Using a main application factory to manage setup.
-   **Declarative Tooling:** Defining all dependencies, linting, and formatting rules in `pyproject.toml`.

## 2. Dependency Management with `uv`

The project uses `uv` for Python package and environment management. It's fast, reliable, and integrates seamlessly with `pyproject.toml`.

-   **Installation:** All dependencies, including optional groups for `docs`, `linting`, and `test`, are defined in `pyproject.toml`. A fresh environment is created by running `uv sync`.
-   **Locking:** A `uv.lock` file is used to pin exact dependency versions, ensuring reproducible builds.
-   **Execution:** All commands and scripts are run within the virtual environment using `uv run`.

**Example `pyproject.toml` dependencies:**
```toml
[project]
dependencies = [
  "fastapi",
  "uvicorn",
  "advanced-alchemy[uuid,obstore]",
  "psycopg[pool,binary]",
  "python-dotenv",
  "pwdlib[argon2]",
  # ... other dependencies
]

[dependency-groups]
dev = [{ include-group = "docs" }, { include-group = "linting" }, { include-group = "test" }]
# ... other groups
```

## 3. Tooling and Quality Assurance

All tooling is configured declaratively in `pyproject.toml` and executed via a `Makefile` for convenience. This setup is identical to the Litestar style guide.

### `Makefile`

The `Makefile` provides a simple, consistent interface for common development tasks (`install`, `lint`, `fix`, `test`, etc.).

### `ruff`, `mypy`, and `pyright`

These tools are configured in `pyproject.toml` to enforce a consistent, high standard of code quality, formatting, and type safety.

## 4. Configuration Management

Application configuration is managed through environment variables, loaded into strongly-typed dataclasses.

### Environment Settings (`lib/settings.py`)

-   **Pattern:** A `Settings` dataclass aggregates multiple domain-specific settings dataclasses (e.g., `DatabaseSettings`, `ServerSettings`).
-   **Environment Loading:** A helper function (`get_env`) reads values from environment variables, with type casting and default values. The `Settings.from_env()` class method loads these from a `.env` file for local development.
-   **Usage:** A cached function `get_settings()` provides a singleton `Settings` instance to the rest of the application. This pattern is framework-agnostic.

## 5. Application Architecture

The application follows a clean, procedural setup centered around a main application factory and the `AdvancedAlchemy` extension.

### Entrypoint (`main.py` or `app.py`)

The main entrypoint creates the `FastAPI` instance, configures the `AdvancedAlchemy` extension, and includes all the domain-specific routers.

```python
# In your main.py

from fastapi import FastAPI
from advanced_alchemy.extensions.fastapi import AdvancedAlchemy
from .lib.settings import get_settings
from .domain.accounts.controllers import router as accounts_router
from .domain.teams.controllers import router as teams_router

settings = get_settings()

# The AdvancedAlchemy instance acts as the integration point
alchemy = AdvancedAlchemy(
    config=settings.db.alchemy_config, # An SQLAlchemyAsyncConfig instance
)

# The main application factory
def create_app() -> FastAPI:
    app = FastAPI()
    
    # Initialize the AdvancedAlchemy extension
    alchemy.init_app(app=app)
    
    # Include domain routers
    app.include_router(accounts_router)
    app.include_router(teams_router)
    
    return app

app = create_app()
```

### CLI Entrypoint (`manage.py`)

FastAPI does not have a built-in CLI. A common pattern is to use `Typer` or `Click` to create a management script. `advanced-alchemy` provides a helper to register database migration commands.

```python
# In your manage.py

import typer
from fastapi import FastAPI
from advanced_alchemy.extensions.fastapi import register_database_commands

from .main import create_app # Your app factory

cli = typer.Typer()

# Add the 'db' command group from advanced-alchemy
cli.add_typer(register_database_commands(app=create_app()), name="db")

@cli.command()
def create_user(email: str):
    """A custom CLI command."""
    # ... logic to create a user ...
    print(f"User {email} created.")

if __name__ == "__main__":
    cli()
```
**Usage:**
```bash
python manage.py db make-migrations -m "Initial migration"
python manage.py db upgrade head
python manage.py create-user "user@example.com"
```

## 6. Domain-Driven Structure

The application's source code is organized by domain or feature (e.g., `accounts`, `teams`). Each feature module contains its own models, schemas, services, and controllers (routers).

### Models (`db/models/`)

-   **Responsibility:** Define the database table structure.
-   **Pattern:** Identical to the Litestar style guide. Models inherit from `advanced-alchemy`'s `UUIDAuditBase`.

### Schemas (`schemas/`)

-   **Responsibility:** Define the data contracts for your API.
-   **Pattern:** Identical to the Litestar style guide. `msgspec.Struct` is recommended for performance, with a base struct for camel-casing.

### Services (`services/`)

-   **Responsibility:** Contain the core business logic.
-   **Pattern:** Identical to the Litestar style guide. Services inherit from `advanced-alchemy`'s `SQLAlchemyAsyncRepositoryService` and are framework-agnostic.

### Controllers (`domain/.../controllers.py`)

-   **Responsibility:** Define the API endpoints using `APIRouter`.
-   **Pattern:** Controllers are kept lean. Dependencies (services, filters) are injected directly into the route handler signature using `Depends()`. The `AdvancedAlchemy` instance (`alchemy`) provides the dependency factories.

**Example: `domain/accounts/controllers.py`**
```python
from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends
from advanced_alchemy.filters import FilterTypes

from app.main import alchemy # The central AdvancedAlchemy instance
from app import schemas as s
from app.services import UserService

router = APIRouter(prefix="/users", tags=["Users"])

@router.get("/")
async def list_users(
    # Inject the UserService
    users_service: Annotated[
        UserService,
        Depends(alchemy.provide_service(UserService))
    ],
    # Inject the generated filters
    filters: Annotated[
        list[FilterTypes],
        Depends(alchemy.provide_filters({"id_filter": UUID, "search": "name,email"}))
    ],
) -> list[s.User]:
    """List users."""
    results, _ = await users_service.list_and_count(*filters)
    return users_service.to_schema(results, schema_type=s.User)

@router.get("/{user_id:uuid}")
async def get_user(
    user_id: UUID,
    users_service: Annotated[
        UserService,
        Depends(alchemy.provide_service(UserService))
    ],
) -> s.User:
    """Get a user by ID."""
    db_obj = await users_service.get(user_id)
    return users_service.to_schema(db_obj, schema_type=s.User)

## 7. Practical Example: Authentication Flow

To make these patterns concrete, let's walk through a complete authentication and registration flow adapted for FastAPI.

### The `UserService` with Business Logic (Framework-Agnostic)

The `UserService` is extended with an `authenticate` method and a `to_model_on_create` hook for password hashing. This service is identical to the one used in the Litestar example, demonstrating its framework-agnostic nature.

```python
# In services/user_service.py

from advanced_alchemy import service, repository
from app.db import models as m
from app.lib import crypt  # Your password hashing utility
from fastapi import HTTPException, status

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
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        
        if not db_obj.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account is inactive")
            
        return db_obj
```

### The `AccessController` for API Endpoints

The `APIRouter` handles the HTTP requests for login and registration, delegating all logic to the `UserService` via `Depends`.

```python
# In domain/access/controllers.py

from typing import Annotated
from fastapi import APIRouter, Depends
from app import schemas as s, security
from app.main import alchemy
from app.services import UserService, RoleService

router = APIRouter(prefix="/access", tags=["Access"])

@router.post("/login")
async def login(
    users_service: Annotated[UserService, Depends(alchemy.provide_service(UserService))],
    data: s.UserLogin,
) -> s.Token:
    """Authenticate a user and return a JWT token."""
    user = await users_service.authenticate(data.username, data.password)
    return security.auth.login(user.email) # Assumes a security module to create the token

@router.post("/signup")
async def signup(
    users_service: Annotated[UserService, Depends(alchemy.provide_service(UserService))],
    roles_service: Annotated[RoleService, Depends(alchemy.provide_service(RoleService))],
    data: s.UserSignup,
) -> s.User:
    """Register a new account."""
    user_data = data.model_dump()
    
    # Assign a default role
    role_obj = await roles_service.get_one_or_none(name="Application Access")
    if role_obj:
        user_data["role_id"] = role_obj.id
        
    user = await users_service.create(user_data)
    return users_service.to_schema(user, schema_type=s.User)
```

### The User Provider for Authenticated Requests

This dependency provider is used by FastAPI's security utilities. It takes a decoded JWT token, uses the `UserService` to fetch the user from the database, and returns the user object.

```python
# In security.py or a similar module

from typing import Annotated
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from app.main import alchemy
from app.services import UserService
from app.db import models as m
from app import schemas as s

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/access/login")

async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    users_service: Annotated[UserService, Depends(alchemy.provide_service(UserService))],
) -> m.User:
    """Decode JWT token and retrieve the current user."""
    try:
        payload = jwt.decode(token, "SECRET_KEY", algorithms=["HS256"])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        token_data = s.TokenPayload(username=username)
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    
    user = await users_service.get_one_or_none(email=token_data.username)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")
        
    return user
```
This guide provides a complete template for building robust, scalable, and maintainable FastAPI applications that leverage the full power of `advanced-alchemy`.

