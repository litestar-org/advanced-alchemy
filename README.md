<!-- markdownlint-disable -->
<div align="center">
  <!-- github-banner-start -->
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/_static/banner-inline-dark.svg">
    <source media="(prefers-color-scheme: light)" srcset="docs/_static/banner-inline-light.svg">
    <img alt="Advanced Alchemy" src="docs/_static/banner-inline-light.svg" width="560" />
  </picture>
  <!-- github-banner-end -->

<p><strong>A carefully crafted, thoroughly tested, optimized companion library for SQLAlchemy.</strong></p>

<!-- prettier-ignore-start -->
[![CI](https://github.com/litestar-org/advanced-alchemy/actions/workflows/ci.yml/badge.svg)](https://github.com/litestar-org/advanced-alchemy/actions/workflows/ci.yml)
[![Coverage](https://codecov.io/github/litestar-org/advanced-alchemy/graph/badge.svg?token=vKez4Pycrc)](https://codecov.io/github/litestar-org/advanced-alchemy)
[![PyPI](https://img.shields.io/pypi/v/advanced-alchemy)](https://pypi.org/project/advanced-alchemy/)
[![Python](https://img.shields.io/pypi/pyversions/advanced-alchemy)](https://pypi.org/project/advanced-alchemy/)
[![License](https://img.shields.io/pypi/l/advanced-alchemy)](https://github.com/litestar-org/advanced-alchemy/blob/main/LICENSE)
[![Docs](https://img.shields.io/badge/docs-advanced--alchemy.litestar.dev-1d4ed8)](https://advanced-alchemy.litestar.dev/latest/)

[Documentation](https://advanced-alchemy.litestar.dev/latest/) · [Getting Started](https://advanced-alchemy.litestar.dev/latest/getting-started.html) · [Data Modeling](https://advanced-alchemy.litestar.dev/latest/usage/modeling/index.html) · [Repositories](https://advanced-alchemy.litestar.dev/latest/usage/repositories/index.html) · [Services](https://advanced-alchemy.litestar.dev/latest/usage/services.html) · [Frameworks](https://advanced-alchemy.litestar.dev/latest/usage/frameworks/index.html) · [API Reference](https://advanced-alchemy.litestar.dev/latest/reference/index.html)
<!-- prettier-ignore-end -->

</div>
<!-- markdownlint-restore -->

Advanced Alchemy builds on SQLAlchemy 2.0+ and Alembic 1.12+ with synchronous and asynchronous repositories, typed service layers, declarative bases and mixins, portable custom column types, replica routing, query caching, and web framework plugins. Models stay standard SQLAlchemy declarative classes (including `SQLModel` `table=True` models and composite primary keys) while gaining consistent CRUD, filtering, pagination, and dialect-native bulk upserts.

## Capabilities

| Area | Overview |
| --- | --- |
| **Declarative Bases & Mixins** | Ready-to-use `UUIDBase`, `UUIDv6Base`, `UUIDv7Base`, `NanoIDBase`, and `BigIntBase` models (plus `*AuditBase` variants with `created_at` and `updated_at`), `SlugKey`, `SoftDeleteMixin`, `UniqueMixin`, sentinel columns, and `SQLModel` compatibility. |
| **Repositories & Services** | Sync and `asyncio` repositories with `get_many_and_count`, statement and relationship filters, `FilterSet`, and native bulk upserts (`ON CONFLICT` and `MERGE`), paired with services hydrating `Pydantic`, `msgspec`, `dataclass`, `attrs`, and `SQLModel` schemas. |
| **Custom Column Types** | Dialect-adaptive `GUID`, `DateTimeUTC`, `JsonB` (including Oracle `ORA_JSONB`), `BigIntIdentity`, `Vector`, `EncryptedString` (`pgcrypto` and Fernet), `PasswordHash` (`Argon2`, `Pwdlib`, `Passlib`), `TOTPSecret`, `OneTimeCode`, and `StoredObject` (`fsspec` and `obstore`). |
| **Database Backends** | Tested across PostgreSQL (`asyncpg`, `psycopg`), CockroachDB, SQLite (`sqlite3`, `aiosqlite`), MySQL & MariaDB (`asyncmy`), Oracle `18c`, `23ai`, and `26ai` (`oracledb`), Google Cloud Spanner, DuckDB (`duckdb_engine`), and SQL Server (`pyodbc`, `aioodbc`). |
| **Migrations, CLI & Seeding** | Programmatic Alembic commands and the `alchemy` CLI, read/write replica routing with primary pinning after writes, Dogpile L2 query caching, and streaming `JSON`, `JSONL`, and `CSV` fixture seeding. |
| **Web Frameworks** | First-party plugins, per-request session lifecycle management, dependency injection providers, file-storage lifecycle hooks, and CLI integration for Litestar, FastAPI, Starlette, Flask, and Sanic. |

## Usage

### Installation

```shell
uv add advanced-alchemy
# or
pip install advanced-alchemy
```

> [!NOTE]
> See [the installation guide][install-guide] in the documentation for optional database driver and framework extras.

### Repositories

Advanced Alchemy provides asynchronous and synchronous repository classes for CRUD, filtering, pagination, and bulk operations on SQLAlchemy models.
<!-- markdownlint-disable -->
<details>
<summary>Sync repository CRUD example</summary>
<!-- markdownlint-restore -->

```python
from sqlalchemy.orm import Mapped

from advanced_alchemy import base, config, repository
from advanced_alchemy.filters import LimitOffset


class User(base.UUIDBase):
    __tablename__ = "user_account"
    email: Mapped[str]
    name: Mapped[str]


class UserRepository(repository.SQLAlchemySyncRepository[User]):
    """User repository."""

    model_type = User


db = config.SQLAlchemySyncConfig(
    connection_string="sqlite:///:memory:",
    session_config=config.SyncSessionConfig(expire_on_commit=False),
)

with db.get_engine().begin() as conn:
    User.metadata.create_all(conn)

with db.get_session() as db_session:
    repo = UserRepository(session=db_session)
    # 1) Create multiple users with `add_many`.
    bulk_users = [
        {"email": "cody@litestar.dev", "name": "Cody"},
        {"email": "janek@litestar.dev", "name": "Janek"},
        {"email": "peter@litestar.dev", "name": "Peter"},
        {"email": "jacob@litestar.dev", "name": "Jacob"},
    ]
    objs = repo.add_many([User(**raw_user) for raw_user in bulk_users])
    db_session.commit()
    print(f"Created {len(objs)} new objects.")

    # 2) Select paginated data and total row count, passing equality filters as kwargs.
    created_objs, total_objs = repo.get_many_and_count(LimitOffset(limit=10, offset=0), name="Cody")
    print(f"Selected {len(created_objs)} records out of a total of {total_objs}.")

    # 3) Delete the selected batch of records.
    deleted_objs = repo.delete_many([new_obj.id for new_obj in created_objs])
    print(f"Removed {len(deleted_objs)} records out of a total of {total_objs}.")

    # 4) Count the remaining rows.
    remaining_count = repo.count()
    print(f"Found {remaining_count} remaining records after delete.")
```

</details>

For a full standalone example, see the sample [here][standalone-example].

### Services

Service classes wrap repositories and accept dictionaries, SQLAlchemy models, or typed DTO schemas (`Pydantic`, `msgspec`, `dataclass`, `attrs`, `SQLModel`), handling model hydration and output conversion.
<!-- markdownlint-disable -->
<details>
<summary>Sync service CRUD example</summary>
<!-- markdownlint-restore -->

```python
from sqlalchemy.orm import Mapped

from advanced_alchemy import base, config, repository, service
from advanced_alchemy.filters import LimitOffset


class User(base.UUIDBase):
    __tablename__ = "user_account"
    email: Mapped[str]
    name: Mapped[str]


class UserService(service.SQLAlchemySyncRepositoryService[User]):
    """User service."""

    class Repo(repository.SQLAlchemySyncRepository[User]):
        """User repository."""

        model_type = User

    repository_type = Repo


db = config.SQLAlchemySyncConfig(
    connection_string="sqlite:///:memory:",
    session_config=config.SyncSessionConfig(expire_on_commit=False),
)

with db.get_engine().begin() as conn:
    User.metadata.create_all(conn)

with db.get_session() as db_session:
    user_service = UserService(session=db_session)
    # 1) Create multiple users directly from dictionaries.
    objs = user_service.create_many(
        [
            {"email": "cody@litestar.dev", "name": "Cody"},
            {"email": "janek@litestar.dev", "name": "Janek"},
            {"email": "peter@litestar.dev", "name": "Peter"},
            {"email": "jacob@litestar.dev", "name": "Jacob"},
        ]
    )
    print(f"Created {len(objs)} new objects.")

    # 2) Select paginated data and total row count, passing equality filters as kwargs.
    created_objs, total_objs = user_service.get_many_and_count(LimitOffset(limit=10, offset=0), name="Cody")
    print(f"Selected {len(created_objs)} records out of a total of {total_objs}.")

    # 3) Delete the selected batch of records.
    deleted_objs = user_service.delete_many([new_obj.id for new_obj in created_objs])
    print(f"Removed {len(deleted_objs)} records out of a total of {total_objs}.")

    # 4) Count the remaining rows.
    remaining_count = user_service.count()
    print(f"Found {remaining_count} remaining records after delete.")
```

</details>

### Web Frameworks

Advanced Alchemy integrates with any Python web framework and includes first-party extensions for Litestar, Flask, FastAPI, Starlette, and Sanic.

#### Litestar

Advanced Alchemy is the official SQLAlchemy integration for Litestar (`uv add "litestar[sqlalchemy]"` or `pip install "litestar[sqlalchemy]"`).

<!-- markdownlint-disable -->
<details>
<summary>Litestar example</summary>
<!-- markdownlint-restore -->

```python
from litestar import Litestar
from litestar.plugins.sqlalchemy import SQLAlchemyAsyncConfig, SQLAlchemyPlugin

alchemy = SQLAlchemyPlugin(
    config=SQLAlchemyAsyncConfig(connection_string="sqlite+aiosqlite:///test.sqlite"),
)
app = Litestar(plugins=[alchemy])
```

</details>

For a full Litestar example, see [here][litestar-example].

#### Flask

<!-- markdownlint-disable -->
<details>
<summary>Flask example</summary>
<!-- markdownlint-restore -->

```python
from flask import Flask

from advanced_alchemy.extensions.flask import AdvancedAlchemy, SQLAlchemySyncConfig

app = Flask(__name__)
alchemy = AdvancedAlchemy(
    config=SQLAlchemySyncConfig(connection_string="sqlite:///:memory:"),
    app=app,
)
```

</details>

For a full Flask example, see [here][flask-example].

#### FastAPI

<!-- markdownlint-disable -->
<details>
<summary>FastAPI example</summary>
<!-- markdownlint-restore -->

```python
from fastapi import FastAPI

from advanced_alchemy.extensions.fastapi import AdvancedAlchemy, SQLAlchemyAsyncConfig

app = FastAPI()
alchemy = AdvancedAlchemy(
    config=SQLAlchemyAsyncConfig(connection_string="sqlite+aiosqlite:///test.sqlite"),
    app=app,
)
```

</details>

For a full FastAPI example with optional CLI integration, see [here][fastapi-example].

#### Starlette

<!-- markdownlint-disable -->
<details>
<summary>Starlette example</summary>
<!-- markdownlint-restore -->

```python
from starlette.applications import Starlette

from advanced_alchemy.extensions.starlette import AdvancedAlchemy, SQLAlchemyAsyncConfig

app = Starlette()
alchemy = AdvancedAlchemy(
    config=SQLAlchemyAsyncConfig(connection_string="sqlite+aiosqlite:///test.sqlite"),
    app=app,
)
```

</details>

#### Sanic

<!-- markdownlint-disable -->
<details>
<summary>Sanic example</summary>
<!-- markdownlint-restore -->

```python
from sanic import Sanic
from sanic_ext import Extend

from advanced_alchemy.extensions.sanic import AdvancedAlchemy, SQLAlchemyAsyncConfig

app = Sanic("AlchemySanicApp")
alchemy = AdvancedAlchemy(
    sqlalchemy_config=SQLAlchemyAsyncConfig(connection_string="sqlite+aiosqlite:///test.sqlite"),
)
Extend.register(alchemy)
```

</details>

For a full Sanic example, see [here][sanic-example].

## Contributing

All [Litestar Organization][litestar-org] projects are community-driven and open to contributions of any size.

Before contributing, please review the [contribution guide][contributing].

If you have any questions, reach out to us on [Discord][discord], our org-wide [GitHub discussions][litestar-discussions] page,
or the [project-specific GitHub discussions page][project-discussions].

<!-- markdownlint-disable -->
<hr />
<p align="center">
  <!-- github-banner-start -->
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/litestar-org/branding/main/assets/Branding%20-%20SVG%20-%20Transparent/Organization%20Project%20-%20Banner%20-%20Inline%20-%20Dark.svg">
    <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/litestar-org/branding/main/assets/Branding%20-%20SVG%20-%20Transparent/Organization%20Project%20-%20Banner%20-%20Inline%20-%20Light.svg">
    <img alt="Litestar Organization Project" src="https://raw.githubusercontent.com/litestar-org/branding/main/assets/Branding%20-%20SVG%20-%20Transparent/Organization%20Project%20-%20Banner%20-%20Inline%20-%20Light.svg" width="40%" height="auto" />
  </picture>
  <br>An official <a href="https://github.com/litestar-org">Litestar Organization</a> Project
  <!-- github-banner-end -->
</p>

[litestar-org]: https://github.com/litestar-org
[contributing]: https://advanced-alchemy.litestar.dev/latest/contribution-guide.html
[discord]: https://discord.gg/litestar
[litestar-discussions]: https://github.com/orgs/litestar-org/discussions
[project-discussions]: https://github.com/litestar-org/advanced-alchemy/discussions
[project-docs]: https://advanced-alchemy.litestar.dev
[install-guide]: https://advanced-alchemy.litestar.dev/latest/getting-started.html#installation
[fastapi-example]: https://github.com/litestar-org/advanced-alchemy/blob/main/examples/fastapi/fastapi_service.py
[flask-example]: https://github.com/litestar-org/advanced-alchemy/blob/main/examples/flask/flask_services.py
[litestar-example]: https://github.com/litestar-org/advanced-alchemy/blob/main/examples/litestar/litestar_service.py
[sanic-example]: https://github.com/litestar-org/advanced-alchemy/blob/main/examples/sanic.py
[standalone-example]: https://github.com/litestar-org/advanced-alchemy/blob/main/examples/standalone.py
