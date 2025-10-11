# Advanced Alchemy Development Guides

Comprehensive guides for developing with and contributing to Advanced Alchemy.

## Database Backends

Database-specific guides covering features, drivers, and compatibility:

- [**PostgreSQL**](database-backends/postgresql.md) - asyncpg, psycopg, JSONB, arrays, full-text search
- [**Oracle**](database-backends/oracle.md) - Oracle 18c/23c patterns and features
- [**MySQL**](database-backends/mysql.md) - MySQL/MariaDB with asyncmy
- [**SQLite**](database-backends/sqlite.md) - SQLite and aiosqlite patterns
- [**Microsoft SQL Server**](database-backends/mssql.md) - MSSQL with aioodbc/pyodbc
- [**CockroachDB**](database-backends/cockroachdb.md) - CockroachDB patterns
- [**Google Cloud Spanner**](database-backends/spanner.md) - Spanner integration
- [**DuckDB**](database-backends/duckdb.md) - DuckDB for analytics

## Patterns

Core architecture patterns and best practices:

- [**Repository-Service Pattern**](patterns/repository-service.md) - Layer separation and dependency flow

## Storage

File storage guides covering different backend implementations:

- [**FSSpec Storage**](storage/fsspec.md) - Flexible file storage with fsspec (S3, GCS, Azure, local, etc.)
- [**Obstore Storage**](storage/obstore.md) - High-performance Rust-based storage backend

## Testing

Testing strategies and patterns:

- [**Integration Testing**](testing/integration.md) - Multi-database testing and CI/CD

## Quick Reference

- [**Quick Reference**](quick-reference/quick-reference.md) - Common patterns and code snippets
- [**Litestar Playbook**](quick-reference/litestar-playbook.md) - Fast-start guide for Litestar integration

## Usage

These guides are referenced by AI agents and are the **canonical source of truth** for Advanced Alchemy development patterns. When working with AI coding assistants:

1. **Agents read these guides first** before making implementation decisions
2. **Guides are verified and updated** to reflect current best practices
3. **Cross-AI compatible** - works with Claude, Gemini, Codex, and other AI assistants

## Contributing

When adding new patterns or updating guides:

1. Update the relevant guide in this directory
2. Run tests and linting to ensure accuracy
3. Update this README if adding new guide categories
4. Commit guides with descriptive messages

## Guide Organization

```
docs/guides/
├── README.md                           # This file
├── database-backends/                  # Database-specific guides
│   ├── cockroachdb.md
│   ├── duckdb.md
│   ├── mssql.md
│   ├── mysql.md
│   ├── oracle.md
│   ├── postgresql.md
│   ├── spanner.md
│   └── sqlite.md
├── patterns/                           # Core patterns
│   └── repository-service.md
├── storage/                            # File storage guides
│   ├── fsspec.md
│   └── obstore.md
├── testing/                            # Testing strategies
│   └── integration.md
└── quick-reference/                    # Quick references
    ├── litestar-playbook.md
    └── quick-reference.md
```

## See Also

- [AGENTS.md](../../AGENTS.md) - Core quality standards and development patterns
- [CLAUDE.md](../../CLAUDE.md) - Project configuration for Claude Code
