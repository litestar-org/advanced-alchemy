# Testing Integration Guide

Advanced Alchemy testing patterns with pytest-databases. For pytest docs, see [docs.pytest.org](https://docs.pytest.org). For Docker, see [docs.docker.com](https://docs.docker.com).

**CRITICAL**: Full test suite takes 20+ minutes. Always use database markers during development.

## pytest-databases Integration

Advanced Alchemy uses [pytest-databases](https://github.com/litestar-org/pytest-databases) for Docker-based database fixtures.

### Installation

```bash
uv sync --all-extras --dev
```

### Connection URL Fixtures

```python
# PostgreSQL
postgres_asyncpg_url      # postgresql+asyncpg://...
postgres_psycopg_url      # postgresql+psycopg://...

# MySQL
mysql_asyncmy_url         # mysql+asyncmy://...

# Oracle
oracle18c_url             # oracle+oracledb://...
oracle23ai_url            # oracle+oracledb://...

# SQL Server
mssql_pyodbc_url          # mssql+pyodbc://...
mssql_aioodbc_url         # mssql+aioodbc://...

# CockroachDB
cockroachdb_asyncpg_url   # cockroachdb+asyncpg://...
cockroachdb_psycopg_url   # cockroachdb+psycopg://...

# Spanner
spanner_url               # spanner+spanner://...
```

## Database Markers

Markers defined in `pyproject.toml`:

```python
# Async drivers
pytest.mark.asyncpg           # PostgreSQL (asyncpg)
pytest.mark.psycopg_async     # PostgreSQL (psycopg async)
pytest.mark.asyncmy           # MySQL (asyncmy)
pytest.mark.aiosqlite         # SQLite (aiosqlite)
pytest.mark.oracledb_async    # Oracle (oracledb async)
pytest.mark.mssql_async       # SQL Server (aioodbc)
pytest.mark.cockroachdb_async # CockroachDB (asyncpg)

# Sync drivers
pytest.mark.sqlite            # SQLite (sqlite3)
pytest.mark.psycopg_sync      # PostgreSQL (psycopg sync)
pytest.mark.oracledb_sync     # Oracle (oracledb sync)
pytest.mark.mssql_sync        # SQL Server (pyodbc)
pytest.mark.cockroachdb_sync  # CockroachDB (psycopg)
pytest.mark.duckdb            # DuckDB
pytest.mark.spanner           # Google Cloud Spanner

# Special
pytest.mark.mock_async        # Mock async engine (fast)
pytest.mark.mock_sync         # Mock sync engine (fast)
pytest.mark.integration       # All integration tests
pytest.mark.unit              # Unit tests only
```

### Using Markers

```bash
# SQLite only (fast, no Docker)
uv run pytest tests/integration/test_repository.py -m "sqlite or aiosqlite" -v

# PostgreSQL only
uv run pytest tests/integration/ -m "asyncpg" -v

# Multiple databases
uv run pytest tests/integration/ -m "sqlite or asyncpg or oracle18c" -v

# Unit tests only
uv run pytest tests/unit/ -m "unit" -v

# Skip slow databases
uv run pytest tests/integration/ -m "not (spanner or cockroachdb or mssql)" -v
```

### Mark Tests

```python
import pytest


@pytest.mark.asyncpg
async def test_postgres_feature(asyncpg_engine):
    """PostgreSQL-specific test."""
    pass


@pytest.mark.sqlite
def test_sqlite_compat(sqlite_engine):
    """SQLite compatibility test."""
    pass
```

## Fixture Naming Conventions

### Data Fixtures

```python
@pytest.fixture
async def sample_user(user_repository: "UserRepository") -> "User":
    """Single sample user."""
    return await user_repository.create({"email": "test@example.com", "name": "Test User"})


@pytest.fixture
async def users_batch(user_repository: "UserRepository") -> "list[User]":
    """Multiple users."""
    return await user_repository.create_many([
        {"email": "user1@example.com", "name": "User 1"},
        {"email": "user2@example.com", "name": "User 2"},
        {"email": "user3@example.com", "name": "User 3"},
    ])


@pytest.fixture
async def sample_post(post_repository: "PostRepository", sample_user: "User") -> "Post":
    """Single sample post."""
    return await post_repository.create({
        "title": "Test Post",
        "content": "Test content",
        "author_id": sample_user.id,
    })
```

**DON'T use:** `test_user`, `user_list`, `test_post`

### Repository Fixtures

```python
from typing import TYPE_CHECKING
from sqlalchemy.ext.asyncio import AsyncSession
from advanced_alchemy.repository import SQLAlchemyAsyncRepository

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class UserRepository(SQLAlchemyAsyncRepository["User"]):
    model_type = User


@pytest.fixture
async def user_repository(async_session: "AsyncSession") -> "UserRepository":
    return UserRepository(session=async_session)


@pytest.fixture
async def sample_user(user_repository: "UserRepository") -> "User":
    return await user_repository.create({
        "email": "test@example.com",
        "name": "Test User",
    })


async def test_user_creation(sample_user: "User"):
    assert sample_user.email == "test@example.com"
    assert sample_user.id is not None
```

## In-Memory vs Real Database

### In-Memory Mock Repositories

Fast unit tests without database:

```python
from advanced_alchemy.repository.memory import (
    SQLAlchemyAsyncMockRepository,
    SQLAlchemySyncMockRepository,
)


class UserMockRepository(SQLAlchemyAsyncMockRepository["User"]):
    model_type = User


async def test_with_mock():
    repository = UserMockRepository()
    user = await repository.create({"email": "test@example.com"})
    assert user.id is not None

    found = await repository.get_one(User.id == user.id)
    assert found.email == "test@example.com"
```

**Use for:**
- ✅ Unit tests for service layer
- ✅ Fast feedback during development
- ✅ CI/CD without database access
- ✅ Testing business logic

### Real Database Testing

Integration tests with actual databases:

```python
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from advanced_alchemy.repository import SQLAlchemyAsyncRepository


class UserRepository(SQLAlchemyAsyncRepository["User"]):
    model_type = User


@pytest.mark.asyncpg
async def test_real_database(async_session: "AsyncSession"):
    repository = UserRepository(session=async_session)
    user = await repository.create({"email": "test@example.com"})
    # Session auto-rollback after test
```

**Use for:**
- ✅ Integration tests for repositories
- ✅ Database-specific features (JSONB, arrays)
- ✅ Migration testing
- ✅ Performance testing
- ✅ Transaction/concurrency testing

### Hybrid Approach

```python
# Unit tests (fast)
class TestUserService:
    async def test_business_logic(self):
        repository = UserMockRepository()
        service = UserService(repository=repository)
        user = await service.create_user({"email": "test@example.com"})
        assert user.email == "test@example.com"


# Integration tests
class TestUserRepository:
    @pytest.mark.asyncpg
    async def test_database_ops(self, async_session):
        repository = UserRepository(session=async_session)
        user = await repository.create({"email": "test@example.com"})
        assert user.id is not None

        with pytest.raises(IntegrityError):
            await repository.create({"email": "test@example.com"})
```

## Docker-Based Testing

### Prerequisites

```bash
# Verify Docker
docker --version
docker ps
```

### Automatic Management

`pytest-databases` manages containers automatically:

```python
@pytest.mark.asyncpg
async def test_postgres(postgres_service, asyncpg_engine):
    """PostgreSQL container starts automatically."""
    async with asyncpg_engine.connect() as conn:
        result = await conn.execute(text("SELECT 1"))
        assert result.scalar() == 1
```

### Database Cleanup

Automatic rollback via transaction-based fixtures:

```python
# tests/integration/conftest.py

@pytest.fixture()
async def async_session(async_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """Isolated session with automatic rollback."""
    connection = await async_engine.connect()
    transaction = await connection.begin()
    session = AsyncSession(bind=connection, expire_on_commit=False)

    try:
        yield session
    finally:
        await session.rollback()
        await transaction.rollback()
        await connection.close()
```

**No manual cleanup needed!**

## Testing Across Databases

### Parametrized Testing

`async_engine` and `engine` fixtures parametrize across all databases:

```python
async def test_repository_ops(async_session: "AsyncSession"):
    """Runs on ALL async backends: SQLite, PostgreSQL, MySQL, Oracle, SQL Server, CockroachDB."""
    repository = UserRepository(session=async_session)
    user = await repository.create({"email": "test@example.com"})
    assert user.id is not None

    found = await repository.get_one(User.id == user.id)
    assert found.email == "test@example.com"
```

### Database-Specific Tests

```python
@pytest.mark.asyncpg
async def test_postgres_jsonb(async_session):
    """PostgreSQL JSONB test."""
    pass


@pytest.mark.asyncmy
async def test_mysql_specific(async_session):
    """MySQL-specific test."""
    pass


@pytest.mark.sqlite
def test_sqlite_limitations(session):
    """SQLite limitations test."""
    pass
```

### Cross-Database Testing

```python
@pytest.mark.parametrize("db_fixture", [
    pytest.param("aiosqlite_engine", marks=pytest.mark.aiosqlite),
    pytest.param("asyncpg_engine", marks=pytest.mark.asyncpg),
    pytest.param("asyncmy_engine", marks=pytest.mark.asyncmy),
])
async def test_cross_database(db_fixture, request):
    """Test across SQLite, PostgreSQL, MySQL."""
    engine = request.getfixturevalue(db_fixture)

    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT 1"))
        assert result.scalar() == 1
```

### Dialect Detection

```python
async def test_dialect_detection(async_engine):
    dialect_name = async_engine.dialect.name

    if dialect_name == "postgresql":
        # PostgreSQL features
        pass
    elif dialect_name == "sqlite":
        # SQLite limitations
        pass
    elif dialect_name.startswith("oracle"):
        # Oracle-specific
        pass
```

## Coverage

### Targets

- **Repository layer**: 80%+
- **Service layer**: 80%+
- **Core modules**: 90%+
- **Overall**: 75%+

### Running Coverage

```bash
# Coverage report
make coverage

# Equivalent:
uv run pytest tests --dist "loadgroup" -m "" --cov=advanced_alchemy --cov-report=xml -n 2 --quiet

# HTML report
uv run coverage html
open htmlcov/index.html
```

### Configuration

From `pyproject.toml`:

```toml
[tool.coverage.run]
branch = true
concurrency = ["multiprocessing"]
omit = [
    "*/tests/*",
    "advanced_alchemy/alembic/templates/*/env.py",
    "advanced_alchemy/extensions/litestar/cli.py",
]
parallel = true
relative_files = true

[tool.coverage.report]
exclude_lines = [
    'pragma: no cover',
    'if TYPE_CHECKING:',
    'except ImportError:',
    '\.\.\.',
    'raise NotImplementedError',
]
```

### Best Practices

**DO:**
- ✅ Test success and error paths
- ✅ Cover edge cases and boundaries
- ✅ Test multiple database backends
- ✅ Include integration tests for critical paths

**DON'T:**
- ❌ Test private implementation details
- ❌ Write tests just for coverage %
- ❌ Skip error handling tests
- ❌ Ignore database-specific edge cases

### Example

```python
class TestUserRepository:
    async def test_create_success(self, user_repository):
        user = await user_repository.create({"email": "test@example.com"})
        assert user.id is not None

    async def test_create_duplicate_raises(self, user_repository, sample_user):
        with pytest.raises(ConflictError):
            await user_repository.create({"email": sample_user.email})

    async def test_get_one_not_found_raises(self, user_repository):
        with pytest.raises(NotFoundError):
            await user_repository.get_one(User.id == 999999)

    async def test_list_with_filters(self, user_repository, users_batch):
        results = await user_repository.list(
            User.email.contains("user1"),
            limit=10,
        )
        assert len(results) == 1

    async def test_update_success(self, user_repository, sample_user):
        updated = await user_repository.update(
            sample_user,
            {"name": "Updated Name"},
        )
        assert updated.name == "Updated Name"

    async def test_delete_success(self, user_repository, sample_user):
        await user_repository.delete(sample_user)
        with pytest.raises(NotFoundError):
            await user_repository.get_one(User.id == sample_user.id)
```

## CI/CD Integration

### GitHub Actions Architecture

Two workflows:
1. **`.github/workflows/ci.yml`** - Main CI orchestration
2. **`.github/workflows/test.yml`** - Reusable test workflow

### Main CI Workflow

```yaml
# .github/workflows/ci.yml
name: Tests And Linting

on:
  pull_request:
  push:
    branches: [main]

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      - uses: astral-sh/setup-uv@v7
      - run: uv python install 3.12
      - run: uv sync --all-extras --dev
      - run: uv run pre-commit run --all-files

  mypy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      - uses: astral-sh/setup-uv@v7
      - run: uv python install 3.13
      - run: uv sync --all-extras --dev
      - run: uv run mypy

  pyright:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      - uses: astral-sh/setup-uv@v7
      - run: uv python install 3.13
      - run: uv sync --all-extras --dev
      - run: uv run pyright

  test:
    name: "test (${{ matrix.python-version }})"
    strategy:
      fail-fast: true
      matrix:
        python-version: ["3.9", "3.10", "3.11", "3.12", "3.13"]
    uses: ./.github/workflows/test.yml
    with:
      coverage: ${{ matrix.python-version == '3.13' }}
      python-version: ${{ matrix.python-version }}

  codecov:
    needs: [test, validate]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      - uses: actions/download-artifact@v5
        with:
          name: coverage-xml
      - uses: codecov/codecov-action@v5
        with:
          files: coverage.xml
```

### Reusable Test Workflow

```yaml
# .github/workflows/test.yml
name: Test

on:
  workflow_call:
    inputs:
      python-version:
        required: true
        type: string
      coverage:
        required: false
        type: boolean
        default: false
      timeout:
        required: false
        type: number
        default: 60

jobs:
  test:
    runs-on: ubuntu-latest
    timeout-minutes: ${{ inputs.timeout }}

    steps:
      - uses: actions/checkout@v5

      - name: Install Microsoft ODBC Drivers
        run: sudo ACCEPT_EULA=Y apt-get install msodbcsql18 -y

      - uses: astral-sh/setup-uv@v7

      - name: Set up Python
        run: uv python install ${{ inputs.python-version }}

      - name: Install dependencies
        run: uv sync --all-extras --dev

      - name: Test
        if: ${{ !inputs.coverage }}
        run: uv run pytest --dist "loadgroup" -m "" tests -n 2

      - name: Test with coverage
        if: ${{ inputs.coverage }}
        run: uv run pytest tests --dist "loadgroup" -m "" --cov=advanced_alchemy --cov-report=xml -n 2

      - uses: actions/upload-artifact@v4
        if: ${{ inputs.coverage }}
        with:
          name: coverage-xml
          path: coverage.xml
```

### Key CI Characteristics

**Python Matrix:**
- Tests on Python 3.9, 3.10, 3.11, 3.12, 3.13
- Coverage collected on Python 3.13 only

**Test Execution:**
- **CI runs ALL tests** with `-m ""` (no marker filtering)
- Uses `pytest-xdist`: `-n 2` (2 workers)
- Uses loadgroup: `--dist "loadgroup"`
- Timeout: 60 minutes per test job

**Dependencies:**
- Uses `uv` for fast dependency management
- Installs MSSQL ODBC drivers for SQL Server
- Syncs all extras: `uv sync --all-extras --dev`

**Parallel Jobs:**
- `validate`: Pre-commit hooks
- `mypy`: Type checking
- `pyright`: Type checking
- `slotscheck`: Runtime validation
- `test`: Full test suite (5 Python versions)

### Parallel Execution

```bash
# Default (2 workers)
make test

# More workers
uv run pytest tests -n 4

# Loadgroup for database tests
uv run pytest tests --dist "loadgroup" -n 2
```

**IMPORTANT**: Use `--dist "loadgroup"` for database tests.

### Test Isolation with xdist

```python
# tests/integration/conftest.py

@pytest.fixture(
    scope="session",
    name="async_engine",
    params=[
        pytest.param(
            "aiosqlite_engine",
            marks=[
                pytest.mark.aiosqlite,
                pytest.mark.integration,
                pytest.mark.xdist_group("sqlite"),  # Isolated
            ],
        ),
        pytest.param(
            "asyncpg_engine",
            marks=[
                pytest.mark.asyncpg,
                pytest.mark.integration,
                pytest.mark.xdist_group("postgres"),  # Isolated
            ],
        ),
    ],
)
def async_engine(request):
    return request.getfixturevalue(request.param)
```

### CI vs Local

**CI (GitHub Actions):**
- ✅ ALL tests, ALL databases (no filtering)
- ✅ Python 3.9-3.13
- ✅ Coverage on 3.13 only
- ✅ 2 workers
- ✅ 60-minute timeout
- ✅ ODBC drivers installed

**Local Development:**
- ✅ **Use database markers** to avoid 20+ min runs
- ✅ SQLite first (2-3 minutes)
- ✅ Specific markers: `-m "sqlite or aiosqlite"`
- ✅ Test your Python version only
- ✅ Skip slow databases

### Best Practices

1. **CI runs ALL tests** - no marker filtering
2. **Use markers locally** - filter by database
3. **Python version matrix** - ensures 3.9-3.13 compat
4. **Parallel execution** - multiple jobs + workers
5. **Upload coverage** - collect on 3.13, upload to Codecov
6. **Reusable workflows** - `workflow_call` pattern
7. **Install drivers** - ODBC for SQL Server
8. **Set timeouts** - 60-minute limit

## Fast Testing Strategies

### Strategy 1: Database Markers

```bash
# SQLite only (2-3 min)
uv run pytest tests/integration/ -m "sqlite or aiosqlite" -v

# PostgreSQL only
uv run pytest tests/integration/ -m "asyncpg" -v

# Skip slow
uv run pytest tests/integration/ -m "not (spanner or oracle or mssql)" -v
```

### Strategy 2: Specific Files

```bash
# Single file
uv run pytest tests/integration/test_repository.py -v

# Single class
uv run pytest tests/integration/test_repository.py::TestUserRepository -v

# Single method
uv run pytest tests/integration/test_repository.py::TestUserRepository::test_create -v

# With markers
uv run pytest tests/integration/test_repository.py -m "sqlite" -v
```

### Strategy 3: Mock Repositories

```python
from advanced_alchemy.repository.memory import SQLAlchemyAsyncMockRepository


class TestUserServiceUnit:
    async def test_validation(self):
        repository = UserMockRepository()
        service = UserService(repository=repository)

        with pytest.raises(ValidationError):
            await service.create_user({"email": "invalid"})
```

### Strategy 4: Parallel Execution

```bash
# Unit tests (4 workers)
uv run pytest tests/unit -n 4

# Integration tests (2 workers)
uv run pytest tests/integration -n 2

# Loadgroup for databases
uv run pytest tests/integration --dist "loadgroup" -n 2
```

### Strategy 5: Timeouts

```bash
# Set timeout
timeout 180 uv run pytest tests/integration/test_operations.py -v

# pytest-timeout
uv run pytest tests/integration/ --timeout=300 -v
```

### Strategy 6: Fail Fast

```bash
# Stop on first failure
uv run pytest tests/integration/ -x -m "sqlite"

# Stop after N failures
uv run pytest tests/integration/ --maxfail=3 -m "sqlite"
```

### Strategy 7: Pre-commit

```bash
# All quality checks
make lint

# Includes: ruff, mypy, pyright, slotscheck
```

### Recommended Workflow

```bash
# 1. Unit tests (fast)
uv run pytest tests/unit -n 4 -v

# 2. SQLite integration (fast)
uv run pytest tests/integration/ -m "sqlite or aiosqlite" -v

# 3. Linting
make lint

# 4. Multiple databases (before PR)
uv run pytest tests/integration/ -m "sqlite or asyncpg or asyncmy" -v

# 5. Full suite (optional, CI does this)
make test
```

### Time Estimates

| Strategy | Time |
|----------|------|
| Unit tests only | 30s - 1min |
| SQLite integration | 2-3min |
| Single database (PostgreSQL) | 3-5min |
| Multiple databases (3-4) | 8-12min |
| Full suite (all databases) | 20-25min |

## Common Commands

```bash
# Fast development testing
uv run pytest tests/integration/ -m "sqlite or aiosqlite" -v

# Coverage report
make coverage

# Full test suite
make test

# Linting
make lint
```

## See Also

- [pytest-databases](https://github.com/litestar-org/pytest-databases)
- [pytest-xdist](https://pytest-xdist.readthedocs.io/)
- [Repository Pattern](../patterns/repository-service.md)
- [SQLAlchemy Testing](https://docs.sqlalchemy.org/en/20/orm/session_transaction.html)
