# AGENTS.md

This file provides guidance to Gemini, Claude Code, Codex, and other agents when working with code in the Advanced Alchemy project..

## Essential Commands

### Development Setup

```bash
# Install with all extras for development
uv sync --all-extras --dev

# Clean rebuild of environment
make destroy && make install

# Install uv (if not installed)
make install-uv
```

### Testing

```bash
# Run all tests with parallel execution
make test
# Equivalent: uv run pytest --dist "loadgroup" -m "" tests -n 2 --quiet

# Run specific test file
uv run pytest tests/unit/test_repository.py -v

# Run specific test with markers (recommended for faster feedback)
uv run pytest tests/integration/test_filters.py -m "sqlite or aiosqlite" -v

# Run with coverage report
make coverage
# Equivalent: uv run pytest tests --dist "loadgroup" -m "" --cov=advanced_alchemy --cov-report=xml -n 2 --quiet

# Run integration tests (requires database)
uv run pytest tests/integration/ -v

# Run single test method
uv run pytest tests/unit/test_repository.py::TestRepository::test_create -v

# Run tests with timeout (for long-running tests)
timeout 180 uv run pytest tests/integration/test_operations.py -v
```

**IMPORTANT**: When testing code, always call specific test files with appropriate markers. The full test suite takes over 20 minutes, so use markers to limit scope (e.g., `sqlite`, `asyncpg`, `oracle18c`, `spanner`).

### Quality Checks

```bash
# Run all linting and type checking
make lint
# Includes: pre-commit, type-check (mypy + pyright), slotscheck

# Fix code formatting issues
make fix
# Equivalent: uv run ruff check --fix --unsafe-fixes

# Type checking with both mypy and pyright
make type-check

# Pre-commit hooks
make pre-commit

# Slotscheck for runtime validation
make slotscheck
```

### Documentation

```bash
# Build documentation
make docs

# Serve documentation locally with auto-rebuild
make docs-serve

# Check documentation links
make docs-linkcheck
```

### Database Operations

```bash
# Generate new Alembic migration
uv run alembic revision --autogenerate -m "description"

# Apply migrations
uv run alembic upgrade head

# Downgrade migration
uv run alembic downgrade -1

# Use Advanced Alchemy CLI
uv run alchemy --help
```

### Dependency Management

```bash
# Upgrade all dependencies
make upgrade

# Rebuild lockfiles
make lock

# Build package
make build

# Add new dependency
uv add <package>
```

## Project Structure & Architecture

### Key Components

- **`advanced_alchemy/base.py`**: Base model classes (UUIDBase, BigIntBase, AuditBase variants)
- **`advanced_alchemy/repository/`**: Async/sync repository implementations with CRUD operations
    - `_async.py`: Async repository implementation (source of truth)
    - `_sync.py`: Sync repository (auto-generated from async using `unasyncd`)
    - `memory/`: In-memory mock repositories for testing
- **`advanced_alchemy/service/`**: Service layer wrapping repositories with business logic
    - `_async.py`: Async service implementation (source of truth)
    - `_sync.py`: Sync service (auto-generated from async using `unasyncd`)
- **`advanced_alchemy/config/`**: Database configuration classes for async/sync SQLAlchemy
    - `asyncio.py`: Async configuration
    - `sync.py`: Sync configuration
    - `common.py`: Shared configuration
- **`advanced_alchemy/types/`**: Custom SQLAlchemy data types (GUID, JSON, FileObject, etc.)
- **`advanced_alchemy/mixins/`**: Reusable model mixins (audit columns, UUIDs, BigInt IDs, etc.)
- **`advanced_alchemy/extensions/`**: Framework integrations (Litestar, FastAPI, Flask, Sanic, Starlette)
- **`advanced_alchemy/alembic/`**: Enhanced Alembic configuration and templates
- **`advanced_alchemy/filters.py`**: Advanced filtering capabilities for repositories
- **`advanced_alchemy/operations.py`**: Custom SQLAlchemy operations (upserts, bulk operations)
- **`advanced_alchemy/exceptions.py`**: Custom exception hierarchy

### Base Model Hierarchy

```python
# Available base classes (choose based on primary key preference):
from advanced_alchemy.base import (
    UUIDBase,           # UUID primary key
    UUIDAuditBase,      # UUID + created/updated timestamps
    BigIntBase,         # BigInt primary key
    BigIntAuditBase,    # BigInt + audit columns
    UUIDv6Base,         # UUID v6 primary key
    UUIDv7Base,         # UUID v7 primary key (time-ordered)
    NanoIDBase,         # NanoID primary key (requires nanoid extra)
)

# Example usage:
class User(UUIDAuditBase):
    __tablename__ = "users"
    name: "Mapped[str]"
    email: "Mapped[str]" = mapped_column(unique=True)
```

## Core Architecture Patterns

### Layer Separation

**Always follow: Service → Repository → Model pattern**

```python
# ✅ Correct flow
class UserService:
    def __init__(self, repository: UserRepository):
        self.repository = repository

    async def create_user(self, data: dict[str, Any]) -> User:
        # Business logic here
        return await self.repository.create(data)

class UserRepository(SQLAlchemyAsyncRepository[User]):
    model_type = User

    async def get_by_email(self, email: str) -> Optional[User]:
        return await self.get_one_or_none(User.email == email.lower())

# ❌ Never bypass layers
class UserService:
    async def create_user(self, session: AsyncSession) -> User:
        # Don't use session directly in service
        return session.add(User(...))
```

## Type Hints - Python 3.9+ Style

### String Literal Type Hints

**Always stringify all type hints - never use `from __future__ import annotations`**

```python
# ✅ Correct - stringified hints
from typing import Optional, Union

async def get_user(self, user_id: int) -> "Optional[User]":
    return await self.get_one_or_none(User.id == user_id)

def process_items(self, items: "list[User]") -> "dict[str, Any]":
    return {"count": len(items)}

# ❌ Wrong - modern union syntax
async def get_user(self, user_id: int) -> User | None:  # Don't use |
    pass

# ❌ Wrong - future annotations
from __future__ import annotations  # Never import this
```

### Use Legacy Union/Optional Syntax

```python
# ✅ Correct
from typing import Optional, Union

value: "Optional[str]" = None
result: "Union[User, str, None]" = get_result()

# ❌ Wrong
value: "str | None" = None
result: "User | str | None" = get_result()
```

### Use Built-in Collection Types

```python
# ✅ Correct - use built-in types
users: "list[User]" = []
mapping: "dict[str, Any]" = {}
coordinates: "tuple[int, int]" = (0, 0)

# ❌ Wrong - capitalized imports
from typing import List, Dict, Tuple
users: "List[User]" = []  # Don't use capitalized
```

## SQLAlchemy 2.0 Patterns

### Always Use SQLAlchemy 2.0 Syntax

```python
# ✅ Correct - SQLAlchemy 2.0
from sqlalchemy import select, update, delete
from sqlalchemy.orm import selectinload, joinedload

async def get_users_with_posts(self) -> "list[User]":
    stmt = select(User).options(selectinload(User.posts))
    result = await self.session.execute(stmt)
    return list(result.scalars())

# ❌ Wrong - SQLAlchemy 1.x patterns
async def get_users_with_posts(self):
    return await self.session.query(User).options(selectinload(User.posts)).all()
```

### Model Definitions

```python
# ✅ Correct - Modern declarative with Mapped
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"

    id: "Mapped[int]" = mapped_column(primary_key=True)
    email: "Mapped[str]" = mapped_column(String(255), unique=True)
    name: "Mapped[Optional[str]]" = mapped_column(String(100), default=None)
    posts: "Mapped[list[Post]]" = relationship("Post", back_populates="author")
```

## Repository Patterns

### Method Naming Conventions

```python
# ✅ Use these method names
await repository.get_one(User.id == user_id)           # Single result, raises if not found
await repository.get_one_or_none(User.id == user_id)   # Single result or None
await repository.list(User.is_active == True)          # Multiple results
await repository.create(user_data)                     # Create single
await repository.create_many(users_data)               # Create multiple
await repository.update(user, update_data)             # Update instance
await repository.upsert(user_data)                     # Insert or update
await repository.upsert_many(users_data)               # Bulk upsert
await repository.delete(user)                          # Delete instance
await repository.delete_many([id1, id2])               # Delete multiple
await repository.list_and_count(...)                   # Get results + total count

# ❌ Don't use these patterns
await repository.get_by_id(user_id)        # Use get_one_or_none instead
await repository.find_all()                # Use list instead
await repository.save(user)                # Use create/update instead
```

### Filter Patterns

```python
# ✅ Correct - pass filters as separate arguments
users = await repository.list(
    User.is_active == True,
    User.created_at > some_date,
    limit=10,
)

# ✅ Correct - with loading
user = await repository.get_one(
    User.id == user_id,
    load=[selectinload(User.posts)],
)

# ✅ Using filter objects
from advanced_alchemy.filters import LimitOffset, BeforeAfter, SearchFilter

users, count = await repository.list_and_count(
    LimitOffset(limit=20, offset=0),
    BeforeAfter(field_name="created_at", before=end_date, after=start_date),
    SearchFilter(field_name="name", value="john"),
)
```

### Repository Type Annotations

```python
# ✅ Always use these type variables
ModelT = TypeVar("ModelT", bound="Base")

class BaseRepository(SQLAlchemyAsyncRepository["ModelT"], Generic["ModelT"]):
    model_type: "type[ModelT]"

    async def get_by_id(self, item_id: Any) -> "Optional[ModelT]":
        return await self.get_one_or_none(self.model_type.id == item_id)
```

## Service Patterns

### Service Structure

```python
# ✅ Service always wraps repository
class UserService:
    def __init__(self, repository: "UserRepository") -> None:
        self.repository = repository
        self.logger = logging.getLogger(self.__class__.__name__)

    async def create_user(self, data: "dict[str, Any]") -> "User":
        # Validation and business logic
        if not data.get("email"):
            raise ValidationError("Email is required")

        # Use repository for data access
        user = await self.repository.create(data)

        # Log operations
        self.logger.info(f"Created user: {user.id}")
        return user
```

### Error Handling in Services

```python
# ✅ Use specific exceptions from advanced_alchemy.exceptions
from advanced_alchemy.exceptions import NotFoundError, ConflictError

async def get_user(self, user_id: int) -> "User":
    try:
        return await self.repository.get_one(User.id == user_id)
    except NotFoundError:
        raise NotFoundError(f"User not found with id: {user_id}")
```

## Error Messages

### Format Guidelines

```python
# ✅ Correct format: lowercase start, no period, include context
raise NotFoundError(f"user not found with id: {user_id}")
raise ValidationError(f"invalid email format: {email}")
raise ConflictError(f"user already exists with email: {email}")

# ❌ Wrong format
raise NotFoundError(f"User not found.")  # Capitalized, period
raise ValidationError("Invalid input")    # No context
```

## Testing Patterns

### Fixture Naming

```python
# ✅ Use these fixture names
@pytest.fixture
async def sample_user(user_repository: "UserRepository") -> "User":
    return await user_repository.create({"email": "test@example.com"})

@pytest.fixture
async def users_batch(user_repository: "UserRepository") -> "list[User]":
    return await user_repository.create_many([...])

# ❌ Don't use these names
@pytest.fixture
async def test_user(): pass      # Use sample_user

@pytest.fixture
async def user_list(): pass     # Use users_batch
```

### Test Method Naming

```python
# ✅ Descriptive test names
async def test_create_user_success(self, user_service: "UserService") -> None:
    pass

async def test_create_user_duplicate_email_raises_conflict(self) -> None:
    pass

async def test_get_user_not_found_raises_error(self) -> None:
    pass
```

### Database-Specific Testing

```python
# Use pytest-databases fixtures and markers
@pytest.mark.asyncpg
async def test_postgres_specific_feature(asyncpg_engine):
    """Test PostgreSQL-specific functionality"""
    pass

@pytest.mark.aiosqlite
async def test_sqlite_specific_feature(aiosqlite_engine):
    """Test SQLite-specific functionality"""
    pass

# Test across all supported dialects
@pytest.mark.parametrize("dialect", ["sqlite", "postgres", "mysql", "oracle"])
async def test_cross_dialect_feature(dialect, engine_factory):
    """Ensure feature works across database backends"""
    pass
```

## Import Patterns

### Always Import These

```python
# Standard typing imports
from typing import Any, Optional, Union, Generic, TypeVar, TYPE_CHECKING

# SQLAlchemy 2.0 imports
from sqlalchemy import select, update, delete, func
from sqlalchemy.orm import selectinload, joinedload, Mapped, mapped_column
from sqlalchemy.ext.asyncio import AsyncSession

# Advanced Alchemy imports
from advanced_alchemy.repository import SQLAlchemyAsyncRepository
from advanced_alchemy.service import SQLAlchemyAsyncRepositoryService
from advanced_alchemy.exceptions import NotFoundError, ConflictError, ValidationError
```

### Import Organization

```python
# ✅ Group imports in this order
# 1. Standard library
import logging
from datetime import datetime
from typing import Any, Optional

# 2. Third-party
from sqlalchemy import select
from sqlalchemy.orm import Mapped

# 3. Local imports
from advanced_alchemy.repository import SQLAlchemyAsyncRepository
from myapp.models import User
```

## Database Patterns

### Session Management

```python
# ✅ Always use context managers
async with session.begin():
    user = await repository.create(user_data)
    # Auto-commit on success, rollback on exception

# ✅ Repository should not manage sessions
class UserRepository(SQLAlchemyAsyncRepository["User"]):
    # Session passed in constructor, don't create new ones
    pass
```

### Query Building

```python
# ✅ Use select() for queries
stmt = select(User).where(User.is_active == True).limit(10)
result = await session.execute(stmt)
users = list(result.scalars())

# ✅ Complex queries with joins
stmt = (
    select(User)
    .join(User.posts)
    .where(Post.published == True)
    .options(selectinload(User.posts))
)
```

## Database Backend Support

Advanced Alchemy supports multiple database backends with comprehensive testing:

- **SQLite**: `aiosqlite` (async) or `sqlite3` (sync)
- **PostgreSQL**: `asyncpg` (async) or `psycopg[binary,pool]` (sync/async)
- **MySQL**: `asyncmy` (async)
- **Oracle**: `oracledb` (sync/async) - tested on 18c and 23c
- **Microsoft SQL Server**: `aioodbc` (async) or `pyodbc` (sync)
- **CockroachDB**: `sqlalchemy-cockroachdb` (sync/async)
- **Google Cloud Spanner**: `sqlalchemy-spanner`
- **DuckDB**: `duckdb-engine`

**IMPORTANT**: When adding new functionality to repositories or services, ensure compatibility with ALL supported database backends. Use dialect-specific implementations when necessary (see `operations.py` for examples).

## Async/Sync Code Generation

**CRITICAL: Advanced Alchemy uses `unasyncd` to automatically generate sync code from async implementations**

### Mandatory Workflow for Repository and Service Files

1. **ONLY edit async files** (`_async.py`) - sync files (`_sync.py`) are auto-generated
2. **NEVER edit sync files** - any edits will be overwritten when `make lint` runs
3. Sync files have a comment at the top: `# DO NOT EDIT - This file is auto-generated`
4. After editing async files, run `make lint` to regenerate sync versions
5. Configuration in `pyproject.toml` under `[tool.unasyncd]`

### Files Affected by unasyncd

- `advanced_alchemy/repository/_async.py` → `advanced_alchemy/repository/_sync.py`
- `advanced_alchemy/repository/memory/_async.py` → `advanced_alchemy/repository/memory/_sync.py`
- `advanced_alchemy/service/_async.py` → `advanced_alchemy/service/_sync.py`

```bash
# After editing async files, regenerate sync versions with:
make lint

# Or manually run:
uv run unasyncd
```

**WARNING**: If you edit a `_sync.py` file directly, your changes will be lost the next time `make lint` or pre-commit hooks run!

## Async/Sync Utilities

**IMPORTANT: Always use Advanced Alchemy's sync_tools utilities for async/sync conversions**

Advanced Alchemy provides utilities in `advanced_alchemy.utils.sync_tools` for converting between async and sync code:

### Converting Sync to Async

```python
from advanced_alchemy.utils.sync_tools import async_

# ✅ Convert sync function to async
def sync_operation(data: dict) -> str:
    # Blocking operation
    return process_data(data)

# Convert to async (runs in thread pool)
async_operation = async_(sync_operation)

# Use in async context
result = await async_operation(data)
```

**Use cases:**

- Working with sync-only libraries (e.g., DuckDB, some Oracle operations)
- Integrating blocking I/O in async frameworks
- Converting sync repository operations for async frameworks

### Converting Async to Sync

```python
from advanced_alchemy.utils.sync_tools import run_

# ✅ Convert async function to sync
async def async_operation(data: dict) -> str:
    return await process_data_async(data)

# Convert to sync (uses asyncio.run)
sync_operation = run_(async_operation)

# Use in sync context
result = sync_operation(data)
```

**Use cases:**

- Using async repositories in sync frameworks (Flask, older Django)
- Testing async code in sync test runners
- CLI tools that need to call async functions

### Other Utilities

```python
from advanced_alchemy.utils.sync_tools import (
    await_,              # Await async function in running loop
    ensure_async_,       # Ensure function is async (convert if needed)
    with_ensure_async_,  # Convert context manager to async if needed
    CapacityLimiter,     # Limit concurrent operations
)
```

**Best Practices:**

- ✅ Always use `async_()` instead of `asyncio.to_thread()` or manual ThreadPoolExecutor
- ✅ Always use `run_()` instead of `asyncio.run()` for consistent behavior
- ✅ These utilities handle edge cases (running loops, uvloop, thread safety)
- ❌ Don't implement your own async/sync conversion logic
- ❌ Don't suggest users use raw `asyncio.to_thread()` in documentation

**See also:**

- [advanced_alchemy/utils/sync_tools.py](advanced_alchemy/utils/sync_tools.py) - Full implementation
- [DuckDB guide](docs/guides/database-backends/duckdb.md) - Example usage with sync-only database

## Utility Functions

Advanced Alchemy provides several utility modules that agents should be aware of:

### Text Utilities (`advanced_alchemy.utils.text`)

```python
from advanced_alchemy.utils.text import slugify, check_email

# ✅ Create URL-safe slugs
slug = slugify("Hello World! 123")  # "hello-world-123"
slug = slugify("Café Münchën", allow_unicode=True)  # "café-münchën"
slug = slugify("Hello_World", separator="_")  # "hello_world"

# ✅ Simple email validation
email = check_email("user@example.com")  # Returns email if valid
check_email("invalid")  # Raises ValueError
```

**Use cases:**

- Generating URL slugs for models
- Creating SEO-friendly identifiers
- Basic email validation

### Fixture Loading (`advanced_alchemy.utils.fixtures`)

```python
from pathlib import Path
from advanced_alchemy.utils.fixtures import open_fixture, open_fixture_async

# ✅ Load JSON fixtures (supports .json, .json.gz, .json.zip)
fixtures_path = Path("tests/fixtures")

# Sync
data = open_fixture(fixtures_path, "users")  # loads users.json

# Async
data = await open_fixture_async(fixtures_path, "users")
```

**Use cases:**

- Loading test fixtures in tests
- Seeding databases with initial data
- Loading configuration data from JSON files

**Supported formats:**

- `.json` - Plain JSON
- `.json.gz` - Gzipped JSON
- `.json.zip` - Zipped JSON

### Dataclass Utilities (`advanced_alchemy.utils.dataclass`)

```python
from advanced_alchemy.utils.dataclass import (
    simple_asdict,
    is_dataclass_instance,
    extract_dataclass_items,
)

# ✅ Convert dataclass to dict (simpler than dataclasses.asdict)
user_dict = simple_asdict(user_dataclass)

# ✅ Check if object is dataclass instance
if is_dataclass_instance(obj):
    items = extract_dataclass_items(obj)
```

**Use cases:**

- Working with dataclass-based DTOs
- Serialization of dataclass models
- Type-safe dataclass operations

### Module Loading (`advanced_alchemy.utils.module_loader`)

```python
from advanced_alchemy.utils.module_loader import import_string, module_to_os_path

# ✅ Dynamic imports from string paths
UserModel = import_string("myapp.models.User")
config = import_string("myapp.config.settings")

# ✅ Convert module path to OS path
path = module_to_os_path("myapp.models")  # Path("/path/to/myapp/models.py")
```

**Use cases:**

- Dynamic model loading
- Plugin systems
- Configuration loading from string paths

### Best Practices

- ✅ Use `slugify()` instead of custom slug generation logic
- ✅ Use `open_fixture()` for loading test data (handles compression automatically)
- ✅ Use `import_string()` for dynamic imports instead of `__import__`
- ❌ Don't reimplement these utilities in application code
- ❌ Don't use `dataclasses.asdict()` when `simple_asdict()` is sufficient (simpler, faster)

**See also:**

- [advanced_alchemy/utils/](advanced_alchemy/utils/) - All utility modules
- [Testing guide](docs/guides/testing/integration.md) - Examples using fixtures

## Framework Integration Patterns

### Dependency Injection

```python
# ✅ Provide repositories and services via DI
async def provide_user_repository(session: "AsyncSession") -> "UserRepository":
    return UserRepository(session=session)

async def provide_user_service(
    repository: "UserRepository" = Depends(provide_user_repository),
) -> "UserService":
    return UserService(repository=repository)
```

## Performance Patterns

### Bulk Operations

```python
# ✅ Use bulk methods for multiple items
users = await repository.create_many(users_data)
await repository.update_many(updates_data)

# ✅ Stream large datasets
async for batch in repository.stream_large_dataset(chunk_size=1000):
    await process_batch(batch)
```

### Loading Strategies

```python
# ✅ Eager load relationships to prevent N+1
users = await repository.list(
    User.is_active == True,
    load=[selectinload(User.posts), selectinload(User.profile)],
)

# ✅ Use appropriate loading strategy
# selectinload - separate query (good for one-to-many)
# joinedload - single query with JOIN (good for many-to-one)
```

## Framework Integration Patterns

### Litestar Integration

```python
from litestar import Litestar
from advanced_alchemy.extensions.litestar import SQLAlchemyPlugin, SQLAlchemyAsyncConfig

# Use the Advanced Alchemy plugin (recommended)
alchemy = SQLAlchemyPlugin(
    config=SQLAlchemyAsyncConfig(connection_string="sqlite+aiosqlite:///test.sqlite"),
)
app = Litestar(plugins=[alchemy])
```

### FastAPI Integration

```python
from fastapi import FastAPI
from advanced_alchemy.extensions.fastapi import AdvancedAlchemy, SQLAlchemyAsyncConfig

app = FastAPI()
alchemy = AdvancedAlchemy(
    config=SQLAlchemyAsyncConfig(connection_string="sqlite+aiosqlite:///test.sqlite"),
    app=app,
)
```

### Flask Integration

```python
from flask import Flask
from advanced_alchemy.extensions.flask import AdvancedAlchemy, SQLAlchemySyncConfig

app = Flask(__name__)
alchemy = AdvancedAlchemy(
    config=SQLAlchemySyncConfig(connection_string="duckdb:///:memory:"),
    app=app,
)
```

### Configuration Classes

```python
# For async applications
from advanced_alchemy.config import SQLAlchemyAsyncConfig, AsyncSessionConfig

config = SQLAlchemyAsyncConfig(
    connection_string="postgresql+asyncpg://user:pass@localhost/db",
    session_config=AsyncSessionConfig(expire_on_commit=False),
)

# For sync applications
from advanced_alchemy.config import SQLAlchemySyncConfig, SyncSessionConfig

config = SQLAlchemySyncConfig(
    connection_string="postgresql://user:pass@localhost/db",
    session_config=SyncSessionConfig(expire_on_commit=False),
)
```

## Advanced Features

### Custom Types Usage

```python
from advanced_alchemy.types import GUID, DateTimeUTC, JsonB, FileObject

class Document(UUIDAuditBase):
    __tablename__ = "documents"

    # Enhanced JSON type with better performance
    metadata: "Mapped[dict[str, Any]]" = mapped_column(JsonB)

    # File storage with multiple backend support (fsspec or obstore)
    file: "Mapped[Optional[FileObject]]" = mapped_column(FileObject)

    # UTC timezone-aware datetime
    published_at: "Mapped[Optional[datetime]]" = mapped_column(DateTimeUTC)
```

### Filtering Capabilities

```python
from advanced_alchemy.filters import LimitOffset, BeforeAfter, SearchFilter

# Advanced filtering in repositories
users = await repository.list_and_count(
    LimitOffset(limit=20, offset=0),
    BeforeAfter(field_name="created_at", before=end_date, after=start_date),
    SearchFilter(field_name="name", value="john"),
    User.is_active == True,
)
```

### Bulk Operations and Upserts

```python
# Bulk create
users = await repository.create_many([
    {"name": "User 1", "email": "user1@example.com"},
    {"name": "User 2", "email": "user2@example.com"},
])

# Upsert (insert or update)
user = await repository.upsert(
    {"id": user_id, "name": "Updated Name"},
    match_fields=["id"],
)

# Bulk upsert with dialect-specific optimizations
users = await repository.upsert_many(
    users_data,
    match_fields=["email"],
)
```

## Documentation Standards

When updating documentation:

- Use Sphinx-compatible docstrings (Google style)
- Update changelog in `docs/changelog.rst`
- Use `sphinx-paramlinks` for parameter references
- Use `sphinx_design` for visually appealing elements
- Include code examples with `auto-pytabs` for async/sync variants
- Update relevant toctrees in `docs/index.rst`

## Alembic Integration

When creating new custom types, ensure they're added to Alembic templates:

```python
# Location: advanced_alchemy/alembic/templates/
# Update both asyncio/env.py and sync/env.py
```

## MANDATORY Git and Branch Management Rules

**CRITICAL: NEVER CHANGE BRANCHES WITHOUT EXPLICIT USER PERMISSION**

1. **NEVER checkout main branch** - Always stay on the current working branch unless explicitly told otherwise
2. **Use `gh` CLI for all branch exploration** - Use `gh api` commands to explore other branches/commits
3. **Use `gh` CLI for file comparisons** - Use `gh api` to fetch files from other branches for comparison
4. **No unauthorized branch switching** - Switching branches can wipe user's work and cause data loss

### Safe Branch Exploration Commands

```bash
# ✅ View file from main branch
gh api repos/:owner/:repo/contents/path/to/file.py?ref=main

# ✅ Compare current file with main
gh api repos/:owner/:repo/compare/main...HEAD

# ✅ View specific commit
gh api repos/:owner/:repo/contents/path/to/file.py?ref=COMMIT_SHA

# ❌ NEVER do this without permission
git checkout main  # Can wipe user work!
git checkout other-branch  # Can wipe user work!
```

## Remember: Advanced Alchemy Conventions

1. **NEVER change branches without explicit user permission** - Stay on current branch, use `gh` CLI for exploration
2. **Never bypass the repository layer** - Services use repositories, repositories use SQLAlchemy
3. **Always stringify type hints** - Use quotes around all type annotations
4. **Use Python 3.9+ built-ins** - `list`, `dict`, `tuple`, not `List`, `Dict`, `Tuple`
5. **Use legacy union syntax** - `Optional[T]`, `Union[A, B]`, not `T | None`, `A | B`
6. **Follow SQLAlchemy 2.0** - Use `select()`, `Mapped[]`, `mapped_column()`
7. **Consistent naming** - `get_one_or_none()`, `list()`, `create()`, not custom names
8. **Specific exceptions** - Use `NotFoundError`, `ConflictError`, etc.
9. **Log operations** - Services should log important operations (lowercase, no periods)
10. **Context in errors** - Include relevant values in error messages (lowercase, no periods)
11. **Use provided base classes** - Extend `UUIDBase`, `UUIDAuditBase`, etc. rather than raw `DeclarativeBase`
12. **Leverage custom types** - Use `GUID`, `DateTimeUTC`, `JsonB`, `FileObject` for enhanced functionality
13. **Database compatibility** - Ensure code works across all supported database backends
14. **Use markers for testing** - Target specific databases with appropriate pytest markers
15. **Edit async files only** - Sync files are auto-generated via `unasyncd`
16. **Test with markers** - Use database-specific markers to avoid 20+ minute test runs
17. **Use Advanced Alchemy imports for Litestar** - `from advanced_alchemy.extensions.litestar import SQLAlchemyPlugin`, not `litestar.plugins.sqlalchemy`

## AI Agent System

Advanced Alchemy uses a specialized multi-agent system for complex development workflows. For detailed information about agent coordination, workflow phases, and workspace management, see [.claude/AGENTS.md](.claude/AGENTS.md).

**Quick Links:**

- [Agent Coordination Guide](.claude/AGENTS.md) - Full agent system documentation
- [Planner Agent](.claude/agents/planner.md) - Planning and PRD creation
- [Expert Agent](.claude/agents/expert.md) - Implementation and coding
- [Testing Agent](.claude/agents/testing.md) - Test suite creation
- [Docs & Vision Agent](.claude/agents/docs-vision.md) - Documentation and quality gate

**Slash Commands:**

- `/plan {feature}` - Create requirement workspace and PRD
- `/implement {slug}` - Implement feature from PRD
- `/test {slug}` - Create comprehensive test suite
- `/review {slug}` - Quality gate, docs, cleanup, archive
