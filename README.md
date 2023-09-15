# Advanced Alchemy

<!-- markdownlint-disable -->
<p align="center">
  <!-- github-banner-start -->
  <img src="https://raw.githubusercontent.com/jolt-org/meta/2901c9c5c5895a83fbfa56944c33bca287f88d42/branding/SVG%20-%20Transparent/logo-full-wide.svg" alt="Litestar Logo - Light" width="20%" height="auto" />
  <br>A <a href="https://github.com/jolt-org">Jolt Organization</a> Project
  <!-- github-banner-end -->
</p>
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
  - Postgres via [asyncpg](https://magicstack.github.io/asyncpg/current/)\_ or [psycopg3 (async or sync)](https://www.psycopg.org/psycopg3/)
  - MySQL via [asyncmy](https://github.com/long2ice/asyncmy)
  - Oracle via [oracledb](https://oracle.github.io/python-oracledb/)
  - Google Spanner via [spanner-sqlalchemy](https://github.com/googleapis/python-spanner-sqlalchemy/)
  - DuckDB via [duckdb_engine](https://github.com/Mause/duckdb_engine>)

## Usage

> [!NOTE]\
> This section has not been completed (yet!)

## Contributing

> [!NOTE]\
> This section has not been completed (yet!)
