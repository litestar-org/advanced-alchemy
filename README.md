# Advanced Alchemy

<div align="center">

| Project   |     | Status                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| --------- | :-- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| CI/CD     |     | [![Latest Release](https://github.com/jolt-org/advanced-alchemy/actions/workflows/publish.yaml/badge.svg)](https://github.com/jolt-org/advanced-alchemy/actions/workflows/publish.yaml) [![Tests And Linting](https://github.com/jolt-org/advanced-alchemy/actions/workflows/ci.yaml/badge.svg)](https://github.com/jolt-org/advanced-alchemy/actions/workflows/ci.yaml) [![Documentation Building](https://github.com/jolt-org/advanced-alchemy/actions/workflows/docs.yaml/badge.svg)](https://github.com/jolt-org/advanced-alchemy/actions/workflows/docs.yaml)                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| Quality   |     | [![Coverage](https://sonarcloud.io/api/project_badges/measure?project=jolt-org_advanced-alchemy&metric=coverage)](https://sonarcloud.io/summary/new_code?id=jolt-org_advanced-alchemy) [![Quality Gate Status](https://sonarcloud.io/api/project_badges/measure?project=jolt-org_advanced-alchemy&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=jolt-org_advanced-alchemy) [![Maintainability Rating](https://sonarcloud.io/api/project_badges/measure?project=jolt-org_advanced-alchemy&metric=sqale_rating)](https://sonarcloud.io/summary/new_code?id=jolt-org_advanced-alchemy) [![Reliability Rating](https://sonarcloud.io/api/project_badges/measure?project=jolt-org_advanced-alchemy&metric=reliability_rating)](https://sonarcloud.io/summary/new_code?id=jolt-org_advanced-alchemy) [![Security Rating](https://sonarcloud.io/api/project_badges/measure?project=jolt-org_advanced-alchemy&metric=security_rating)](https://sonarcloud.io/summary/new_code?id=jolt-org_advanced-alchemy)                            |
| Community |     | [![Discord](https://img.shields.io/discord/1149784127659319356?labelColor=F50057&color=202020&label=chat%20on%20discord&logo=discord&logoColor=202020)](https://discord.gg/XpFNTjjtTK)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| Meta      |     | [![Jolt Project](https://img.shields.io/badge/Jolt%20Org-%E2%AD%90-F50057.svg?logo=python&labelColor=F50057&color=202020&logoColor=202020)](https://github.com/jolt-org/) [![types - Mypy](https://img.shields.io/badge/types-Mypy-F50057.svg?logo=python&labelColor=F50057&color=202020&logoColor=202020)](https://github.com/python/mypy) [![License - MIT](https://img.shields.io/badge/license-MIT-F50057.svg?logo=python&labelColor=F50057&color=202020&logoColor=202020)](https://spdx.org/licenses/) [![Jolt Sponsors](https://img.shields.io/badge/Sponsor-%E2%9D%A4-%23202020.svg?&logo=github&logoColor=202020&labelColor=F50057)](https://github.com/sponsors/jolt-org) [![linting - Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/charliermarsh/ruff/main/assets/badge/v2.json&labelColor=F50057)](https://github.com/astral-sh/ruff) [![code style - Black](https://img.shields.io/badge/code%20style-black-000000.svg?logo=python&labelColor=F50057&logoColor=202020)](https://github.com/psf/black) |

</div>

Check out the [project documentation][project-docs] 📚 for more information.

## About

A carefully crafted, thoroughly tested, optimized companion library for SQLAlchemy,
offering features such as:

- Sync and async repositories, featuring common CRUD and highly optimized bulk operations
- Integration with major web frameworks including Litestar, Starlette, FastAPI, Sanic.
- Custom-built alembic configuration and CLI with optional framework integration
- Utility base classes with audit columns, primary keys and utility functions
- Optimized JSON types including a custom JSON type for Oracle.
- Integrated support for UUID6 and UUID7 using [`uuid-utils`](https://github.com/aminalaee/uuid-utils) (install with the `uuid` extra)

- Pre-configured base classes with audit columns UUID or Big Integer primary keys and
  a [sentinel column](https://docs.sqlalchemy.org/en/20/core/connections.html#configuring-sentinel-columns).
- Synchronous and asynchronous repositories featuring:
  - Common CRUD operations for SQLAlchemy models
  - Bulk inserts, updates, upserts, and deletes with dialect-specific enhancements
  - [lambda_stmt](https://docs.sqlalchemy.org/en/20/core/sqlelement.html#sqlalchemy.sql.expression.lambda_stmt) when possible
    for improved query building performance
  - Integrated counts, pagination, sorting, filtering with `LIKE`, `IN`, and dates before and/or after.
- Tested support for multiple database backends including:

  - SQLite via [aiosqlite](https://aiosqlite.omnilib.dev/en/stable/) or [sqlite](https://docs.python.org/3/library/sqlite3.html)
  - Postgres via [asyncpg](https://magicstack.github.io/asyncpg/current/) or [psycopg3 (async or sync)](https://www.psycopg.org/psycopg3/)
  - MySQL via [asyncmy](https://github.com/long2ice/asyncmy)
  - Oracle via [oracledb (async or sync)](https://oracle.github.io/python-oracledb/) (tested on 18c and 23c)
  - Google Spanner via [spanner-sqlalchemy](https://github.com/googleapis/python-spanner-sqlalchemy/)
  - DuckDB via [duckdb_engine](https://github.com/Mause/duckdb_engine)
  - Microsoft SQL Server via [pyodbc](https://github.com/mkleehammer/pyodbc) or [aioodbc](https://github.com/aio-libs/aioodbc)
  - CockroachDB via [sqlalchemy-cockroachdb (async or sync)](https://github.com/cockroachdb/sqlalchemy-cockroachdb)

## Usage

### Installation

```shell
pip install advanced-alchemy
```

> [!IMPORTANT]\
> Check out [the installation guide][install-guide] in our official documentation!

### Repositories

Advanced Alchemy includes a set of asynchronous and synchronous repository classes for easy CRUD
operations on your SQLAlchemy models.

<details>
<summary>Click to expand the example</summary>

```python
from advanced_alchemy.base import UUIDBase
from advanced_alchemy.filters import LimitOffset
from advanced_alchemy.repository import SQLAlchemySyncRepository
from sqlalchemy import create_engine
from sqlalchemy.orm import Mapped, sessionmaker


class User(UUIDBase):
    # you can optionally override the generated table name by manually setting it.
    __tablename__ = "user_account"  # type: ignore[assignment]
    email: Mapped[str]
    name: Mapped[str]


class UserRepository(SQLAlchemySyncRepository[User]):
    """User repository."""

    model_type = User


# use any compatible sqlalchemy engine.
engine = create_engine("duckdb:///:memory:")
session_factory = sessionmaker(engine, expire_on_commit=False)

# Initializes the database.
with engine.begin() as conn:
    User.metadata.create_all(conn)

with session_factory() as db_session:
    repo = UserRepository(session=db_session)
    # 1) Create multiple users with `add_many`
    bulk_users = [
        {"email": 'cody@advanced-alchemy.dev', 'name': 'Cody'},
        {"email": 'janek@advanced-alchemy.dev', 'name': 'Janek'},
        {"email": 'peter@advanced-alchemy.dev', 'name': 'Peter'},
        {"email": 'jacob@advanced-alchemy.dev', 'name': 'Jacob'}
    ]
    objs = repo.add_many([User(**raw_user) for raw_user in bulk_users])
    db_session.commit()
    print(f"Created {len(objs)} new objects.")

    # 2) Select paginated data and total row count.  Pass additional filters as kwargs
    created_objs, total_objs = repo.list_and_count(LimitOffset(limit=10, offset=0), name="Cody")
    print(f"Selected {len(created_objs)} records out of a total of {total_objs}.")

    # 3) Let's remove the batch of records selected.
    deleted_objs = repo.delete_many([new_obj.id for new_obj in created_objs])
    print(f"Removed {len(deleted_objs)} records out of a total of {total_objs}.")

    # 4) Let's count the remaining rows
    remaining_count = repo.count()
    print(f"Found {remaining_count} remaining records after delete.")
```

</details>

For a full standalone example, see the sample [here][standalone-example]

### Services

Advanced Alchemy includes an additional service class to make working with a repository easier.
This class is designed to accept data as a dictionary or SQLAlchemy model,
and it will handle the type conversions for you.

<details>
<summary>Here's the same example from above but using a service to create the data:</summary>

```python
from advanced_alchemy.base import UUIDBase
from advanced_alchemy.filters import LimitOffset
from advanced_alchemy import SQLAlchemySyncRepository, SQLAlchemySyncRepositoryService
from sqlalchemy import create_engine
from sqlalchemy.orm import Mapped, sessionmaker


class User(UUIDBase):
    # you can optionally override the generated table name by manually setting it.
    __tablename__ = "user_account"  # type: ignore[assignment]
    email: Mapped[str]
    name: Mapped[str]


class UserRepository(SQLAlchemySyncRepository[User]):
    """User repository."""

    model_type = User


class UserService(SQLAlchemySyncRepositoryService[User]):
    """User repository."""

    repository_type = UserRepository


# use any compatible sqlalchemy engine.
engine = create_engine("duckdb:///:memory:")
session_factory = sessionmaker(engine, expire_on_commit=False)

# Initializes the database.
with engine.begin() as conn:
    User.metadata.create_all(conn)

with session_factory() as db_session:
    service = UserService(session=db_session)
    # 1) Create multiple users with `add_many`
    objs = service.create_many([
        {"email": 'cody@advanced-alchemy.dev', 'name': 'Cody'},
        {"email": 'janek@advanced-alchemy.dev', 'name': 'Janek'},
        {"email": 'peter@advanced-alchemy.dev', 'name': 'Peter'},
        {"email": 'jacob@advanced-alchemy.dev', 'name': 'Jacob'}
    ])
    print(objs)
    print(f"Created {len(objs)} new objects.")

    # 2) Select paginated data and total row count.  Pass additional filters as kwargs
    created_objs, total_objs = service.list_and_count(LimitOffset(limit=10, offset=0), name="Cody")
    print(f"Selected {len(created_objs)} records out of a total of {total_objs}.")

    # 3) Let's remove the batch of records selected.
    deleted_objs = service.delete_many([new_obj.id for new_obj in created_objs])
    print(f"Removed {len(deleted_objs)} records out of a total of {total_objs}.")

    # 4) Let's count the remaining rows
    remaining_count = service.count()
    print(f"Found {remaining_count} remaining records after delete.")
```

</details>

### Web Frameworks

Advanced Alchemy works with nearly all Python web frameworks.
Several helpers for popular libraries are included, and additional PRs to support others are welcomed.

#### Litestar

Advanced Alchemy is the official SQLAlchemy integration for Litestar.

In addition to installing with `pip install advanced-alchemy`,
it can also be installed as a Litestar extra with `pip install litestar[sqlalchemy]`.

<details>
<summary>Litestar Example</summary>

```python
from litestar import Litestar
from litestar.plugins.sqlalchemy import SQLAlchemyPlugin, SQLAlchemyAsyncConfig
# alternately...
# from advanced_alchemy.extensions.litestar.plugins import SQLAlchemyPlugin
# from advanced_alchemy.extensions.litestar.plugins.init.config import SQLAlchemyAsyncConfig

alchemy = SQLAlchemyPlugin(
  config=SQLAlchemyAsyncConfig(connection_string="sqlite+aiosqlite:///test.sqlite"),
)
app = Litestar(plugins=[alchemy])
```

</details>

For a full Litestar example, check [here][litestar-example]

#### FastAPI

<details>
<summary>FastAPI Example</summary>

```python
from fastapi import FastAPI

from advanced_alchemy.config import SQLAlchemyAsyncConfig
from advanced_alchemy.extensions.starlette import StarletteAdvancedAlchemy

app = FastAPI()
alchemy = StarletteAdvancedAlchemy(
    config=SQLAlchemyAsyncConfig(connection_string="sqlite+aiosqlite:///test.sqlite"), app=app,
)
```

</details>

For a full FastAPI example, see [here][fastapi-example]

#### Starlette

<details>
<summary>Pre-built Example Apps</summary>

```python
from starlette.applications import Starlette

from advanced_alchemy.config import SQLAlchemyAsyncConfig
from advanced_alchemy.extensions.starlette import StarletteAdvancedAlchemy

app = Starlette()
alchemy = StarletteAdvancedAlchemy(
    config=SQLAlchemyAsyncConfig(connection_string="sqlite+aiosqlite:///test.sqlite"), app=app,
)
```

</details>

#### Sanic

<details>
<summary>Pre-built Example Apps</summary>

```python
from sanic import Sanic
from sanic_ext import Extend

from advanced_alchemy.config import SQLAlchemyAsyncConfig
from advanced_alchemy.extensions.sanic import SanicAdvancedAlchemy

app = Sanic("AlchemySanicApp")
alchemy = SanicAdvancedAlchemy(
    sqlalchemy_config=SQLAlchemyAsyncConfig(connection_string="sqlite+aiosqlite:///test.sqlite"),
)
Extend.register(alchemy)
```

</details>

## Contributing

All [Jolt][jolt-org] projects will always be a community-centered, available for contributions of any size.

Before contributing, please review the [contribution guide][contributing].

If you have any questions, reach out to us on [Discord][discord], our org-wide [GitHub discussions][jolt-discussions] page,
or the [project-specific GitHub discussions page][project-discussions].

<hr>

<!-- markdownlint-disable -->
<p align="center">
  <!-- github-banner-start -->
  <img src="https://raw.githubusercontent.com/jolt-org/meta/2901c9c5c5895a83fbfa56944c33bca287f88d42/branding/SVG%20-%20Transparent/logo-full-wide.svg" alt="Litestar Logo - Light" width="20%" height="auto" />
  <br>A <a href="https://github.com/jolt-org">Jolt Organization</a> Project
  <!-- github-banner-end -->
</p>

[jolt-org]: https://github.com/jolt-org
[contributing]: https://docs.advanced-alchemy.jolt.rs/latest/contribution-guide.html
[discord]: https://discord.gg/XpFNTjjtTK
[jolt-discussions]: https://github.com/orgs/jolt-org/discussions
[project-discussions]: https://github.com/jolt-org/advanced-alchemy/discussions
[project-docs]: https://docs.advanced-alchemy.jolt.rs
[install-guide]: https://docs.advanced-alchemy.jolt.rs/latest/#installation
[fastapi-example]: https://github.com/jolt-org/advanced-alchemy/blob/main/examples/fastapi.py
[litestar-example]: https://github.com/jolt-org/advanced-alchemy/blob/main/examples/litestar/litestar_service.py
[standalone-example]: https://github.com/jolt-org/advanced-alchemy/blob/main/examples/standalone.py
