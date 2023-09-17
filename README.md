# Advanced Alchemy

<div align="center">


| Project   |     | Status                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
|-----------|:----|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| CI/CD     |     | [![Latest Release](https://github.com/jolt-org/advanced-alchemy/actions/workflows/publish.yaml/badge.svg)](https://github.com/jolt-org/advanced-alchemy/actions/workflows/publish.yaml) [![Tests And Linting](https://github.com/jolt-org/advanced-alchemy/actions/workflows/ci.yaml/badge.svg)](https://github.com/jolt-org/advanced-alchemy/actions/workflows/ci.yaml) [![Documentation Building](https://github.com/jolt-org/advanced-alchemy/actions/workflows/docs.yaml/badge.svg?branch=main)](https://github.com/jolt-org/advanced-alchemy/actions/workflows/docs.yaml)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| Quality   |     | [![Coverage](https://sonarcloud.io/api/project_badges/measure?project=jolt-org_advanced-alchemy&metric=coverage)](https://sonarcloud.io/summary/new_code?id=jolt-org_advanced-alchemy) [![Quality Gate Status](https://sonarcloud.io/api/project_badges/measure?project=jolt-org_advanced-alchemy&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=jolt-org_advanced-alchemy) [![Maintainability Rating](https://sonarcloud.io/api/project_badges/measure?project=jolt-org_advanced-alchemy&metric=sqale_rating)](https://sonarcloud.io/summary/new_code?id=jolt-org_advanced-alchemy) [![Reliability Rating](https://sonarcloud.io/api/project_badges/measure?project=jolt-org_advanced-alchemy&metric=reliability_rating)](https://sonarcloud.io/summary/new_code?id=jolt-org_advanced-alchemy) [![Security Rating](https://sonarcloud.io/api/project_badges/measure?project=jolt-org_advanced-alchemy&metric=security_rating)](https://sonarcloud.io/summary/new_code?id=jolt-org_advanced-alchemy)                                                                                                                                                                                                                                                                        |
| Community |     | [![Discord](https://img.shields.io/discord/1149784127659319356?labelColor=F50057&color=202020&label=chat%20on%20discord&logo=discord&logoColor=202020)](https://discord.gg/XpFNTjjtTK)                                                                                                                                                                                                                                                                                                                                              |
| Meta      |     | [![Jolt Project](https://img.shields.io/badge/Jolt%20Org-%E2%AD%90-F50057.svg?logo=python&labelColor=F50057&color=202020&logoColor=202020)](https://github.com/jolt-org/) [![types - Mypy](https://img.shields.io/badge/types-Mypy-F50057.svg?logo=python&labelColor=F50057&color=202020&logoColor=202020)](https://github.com/python/mypy) [![License - MIT](https://img.shields.io/badge/license-MIT-F50057.svg?logo=python&labelColor=F50057&color=202020&logoColor=202020)](https://spdx.org/licenses/) [![Jolt Sponsors](https://img.shields.io/badge/Sponsor-%E2%9D%A4-%23202020.svg?&logo=github&logoColor=202020&labelColor=F50057)](https://github.com/sponsors/jolt-org) [![linting - Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/charliermarsh/ruff/main/assets/badge/v2.json&labelColor=F50057)](https://github.com/astral-sh/ruff) [![code style - Black](https://img.shields.io/badge/code%20style-black-000000.svg?logo=python&labelColor=F50057&logoColor=202020)](https://github.com/psf/black) |

</div>
<!-- markdownlint-restore -->

## About

A carefully crafted, thoroughly tested, optimized companion library for SQLAlchemy,
offering features such as:

- Sync and async repositories, featuring common CRUD and highly optimized bulk operations
- Integration with major web frameworks including Litestar, Starlette, FastAPI, Sanic.
- Custom-built alembic configuration and CLI with optional framework integration
- Utility base classes with audit columns, primary keys and utility functions
- Optimized JSON types including a custom JSON type for Oracle.

- Pre-configured base classes with audit columns UUID or Big Integer primary keys and
  a [sentinel column](https://docs.sqlalchemy.org/en/20/core/connections.html#configuring-sentinel-columns>).
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
  - Oracle via [oracledb](https://oracle.github.io/python-oracledb/)
  - Google Spanner via [spanner-sqlalchemy](https://github.com/googleapis/python-spanner-sqlalchemy/)
  - DuckDB via [duckdb_engine](https://github.com/Mause/duckdb_engine>)

## Usage

### Litestar

> [!NOTE]\
> This section has not been completed (yet!)

### Starlette/FastAPI

> [!NOTE]\
> This section has not been completed (yet!)

### Sanic

> [!NOTE]\
> This section has not been completed (yet!)

## Contributing

> [!NOTE]\
> This section has not been completed (yet!)

<!-- markdownlint-disable -->
<p align="center">
  <!-- github-banner-start -->
  <img src="https://raw.githubusercontent.com/jolt-org/meta/2901c9c5c5895a83fbfa56944c33bca287f88d42/branding/SVG%20-%20Transparent/logo-full-wide.svg" alt="Litestar Logo - Light" width="20%" height="auto" />
  <br>A <a href="https://github.com/jolt-org">Jolt Organization</a> Project
  <!-- github-banner-end -->
</p>
