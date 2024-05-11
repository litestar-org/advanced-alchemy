<!-- markdownlint-disable -->
<p align="center">
  <!-- github-banner-start -->
  <img src="https://raw.githubusercontent.com/litestar-org/branding/main/assets/Branding%20-%20SVG%20-%20Transparent/AA%20-%20Banner%20-%20Inline%20-%20Light.svg#gh-light-mode-only" alt="Litestar Logo - Light" width="100%" height="auto" />
  <img src="https://raw.githubusercontent.com/litestar-org/branding/main/assets/Branding%20-%20SVG%20-%20Transparent/AA%20-%20Banner%20-%20Inline%20-%20Dark.svg#gh-dark-mode-only" alt="Litestar Logo - Dark" width="100%" height="auto" />
  <!-- github-banner-end -->
</p>
<!-- markdownlint-restore -->

<div align="center">

<!-- prettier-ignore-start -->

| Project   |     | Status                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
|-----------|:----|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| CI/CD     |     | [![Latest Release](https://github.com/litestar-org/advanced-alchemy/actions/workflows/publish.yml/badge.svg)](https://github.com/litestar-org/advanced-alchemy/actions/workflows/publish.yml) [![ci](https://github.com/litestar-org/advanced-alchemy/actions/workflows/ci.yml/badge.svg)](https://github.com/litestar-org/advanced-alchemy/actions/workflows/ci.yml) [![Documentation Building](https://github.com/litestar-org/advanced-alchemy/actions/workflows/docs.yml/badge.svg?branch=main)](https://github.com/litestar-org/advanced-alchemy/actions/workflows/docs.yml)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| Quality   |     | [![Coverage](https://codecov.io/github/litestar-org/advanced-alchemy/graph/badge.svg?token=vKez4Pycrc)](https://codecov.io/github/litestar-org/advanced-alchemy) [![Quality Gate Status](https://sonarcloud.io/api/project_badges/measure?project=litestar-org_advanced-alchemy&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=litestar-org_advanced-alchemy) [![Maintainability Rating](https://sonarcloud.io/api/project_badges/measure?project=litestar-org_advanced-alchemy&metric=sqale_rating)](https://sonarcloud.io/summary/new_code?id=litestar-org_advanced-alchemy) [![Reliability Rating](https://sonarcloud.io/api/project_badges/measure?project=litestar-org_advanced-alchemy&metric=reliability_rating)](https://sonarcloud.io/summary/new_code?id=litestar-org_advanced-alchemy) [![Security Rating](https://sonarcloud.io/api/project_badges/measure?project=litestar-org_advanced-alchemy&metric=security_rating)](https://sonarcloud.io/summary/new_code?id=litestar-org_advanced-alchemy)                                                                                                    |
| Package   |     | [![PyPI - Version](https://img.shields.io/pypi/v/advanced-alchemy?labelColor=202235&color=edb641&logo=python&logoColor=edb641)](https://badge.fury.io/py/litestar) ![PyPI - Support Python Versions](https://img.shields.io/pypi/pyversions/litestar?labelColor=202235&color=edb641&logo=python&logoColor=edb641) ![Advanced Alchemy PyPI - Downloads](https://img.shields.io/pypi/dm/advanced-alchemy?logo=python&label=package%20downloads&labelColor=202235&color=edb641&logoColor=edb641)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| Community |     | [![Reddit](https://img.shields.io/reddit/subreddit-subscribers/litestarapi?label=r%2FLitestar&logo=reddit&labelColor=202235&color=edb641&logoColor=edb641)](https://reddit.com/r/litestarapi) [![Discord](https://img.shields.io/discord/919193495116337154?labelColor=202235&color=edb641&label=chat%20on%20discord&logo=discord&logoColor=edb641)](https://discord.gg/litestar) [![Matrix](https://img.shields.io/badge/chat%20on%20Matrix-bridged-202235?labelColor=202235&color=edb641&logo=matrix&logoColor=edb641)](https://matrix.to/#/#litestar:matrix.org) [![Medium](https://img.shields.io/badge/Medium-202235?labelColor=202235&color=edb641&logo=medium&logoColor=edb641)](https://blog.litestar.dev) [![Twitter](https://img.shields.io/twitter/follow/LitestarAPI?labelColor=202235&color=edb641&logo=twitter&logoColor=edb641&style=flat)](https://twitter.com/LitestarAPI) [![Blog](https://img.shields.io/badge/Blog-litestar.dev-202235?logo=blogger&labelColor=202235&color=edb641&logoColor=edb641)](https://blog.litestar.dev)                                                             |
| Meta      |     | [![Litestar Project](https://img.shields.io/badge/Litestar%20Org-%E2%AD%90%20Advanced%20Alchemy-202235.svg?logo=python&labelColor=202235&color=edb641&logoColor=edb641)](https://github.com/litestar-org/advanced-alchemy) [![types - Mypy](https://img.shields.io/badge/types-Mypy-202235.svg?logo=python&labelColor=202235&color=edb641&logoColor=edb641)](https://github.com/python/mypy) [![License - MIT](https://img.shields.io/badge/license-MIT-202235.svg?logo=python&labelColor=202235&color=edb641&logoColor=edb641)](https://spdx.org/licenses/) [![Litestar Sponsors](https://img.shields.io/badge/Sponsor-%E2%9D%A4-%23edb641.svg?&logo=github&logoColor=edb641&labelColor=202235)](https://github.com/sponsors/litestar-org) [![linting - Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/charliermarsh/ruff/main/assets/badge/v2.json&labelColor=202235)](https://github.com/astral-sh/ruff) [![code style - Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/format.json&labelColor=202235)](https://github.com/psf/black) |

</div>

# Advanced Alchemy

Check out the [project documentation][project-docs] 📚 for more information.

## About

A carefully crafted, thoroughly tested, optimized companion library for SQLAlchemy,
offering:

- Sync and async repositories, featuring common CRUD and highly optimized bulk operations
- Integration with major web frameworks including Litestar, Starlette, FastAPI, Sanic
- Custom-built alembic configuration and CLI with optional framework integration
- Utility base classes with audit columns, primary keys and utility functions
- Optimized JSON types including a custom JSON type for Oracle
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
- ...and much more

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
        {"email": 'cody@litestar.dev', 'name': 'Cody'},
        {"email": 'janek@litestar.dev', 'name': 'Janek'},
        {"email": 'peter@litestar.dev', 'name': 'Peter'},
        {"email": 'jacob@litestar.dev', 'name': 'Jacob'}
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
        {"email": 'cody@litestar.dev', 'name': 'Cody'},
        {"email": 'janek@litestar.dev', 'name': 'Janek'},
        {"email": 'peter@litestar.dev', 'name': 'Peter'},
        {"email": 'jacob@litestar.dev', 'name': 'Jacob'}
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

All [Litestar Organization][litestar-org] projects will always be a community-centered, available for contributions of any size.

Before contributing, please review the [contribution guide][contributing].

If you have any questions, reach out to us on [Discord][discord], our org-wide [GitHub discussions][litestar-discussions] page,
or the [project-specific GitHub discussions page][project-discussions].

<hr>

<!-- markdownlint-disable -->
<p align="center">
  <!-- github-banner-start -->
  <img src="https://raw.githubusercontent.com/litestar-org/branding/main/assets/Branding%20-%20SVG%20-%20Transparent/Organization%20Project%20-%20Banner%20-%20Inline%20-%20Dark.svg" alt="Litestar Logo - Light" width="40%" height="auto" />
  <br>An official <a href="https://github.com/litestar-org">Litestar Organization</a> Project
  <!-- github-banner-end -->
</p>

[litestar-org]: https://github.com/litestar-org
[contributing]: https://docs.advanced-alchemy.litestar.dev/latest/contribution-guide.html
[discord]: https://discord.gg/litestar
[litestar-discussions]: https://github.com/orgs/litestar-org/discussions
[project-discussions]: https://github.com/litestar-org/advanced-alchemy/discussions
[project-docs]: https://docs.advanced-alchemy.litestar.dev
[install-guide]: https://docs.advanced-alchemy.litestar.dev/latest/#installation
[fastapi-example]: https://github.com/litestar-org/advanced-alchemy/blob/main/examples/fastapi.py
[litestar-example]: https://github.com/litestar-org/advanced-alchemy/blob/main/examples/litestar.py
[standalone-example]: https://github.com/litestar-org/advanced-alchemy/blob/main/examples/standalone.py
