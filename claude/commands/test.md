Invoke the Testing agent to create comprehensive test suites.

**What this does:**
- Reads implementation from `requirements/{slug}/recovery.md`
- Creates unit and integration tests
- Tests all 8+ database backends with pytest markers
- Validates async and sync variants
- Covers edge cases and performance

**Usage:**
```
/test vector-search-support
```

**Or for current active requirement:**
```
/test
```

**The Testing agent will:**
1. Read PRD for acceptance criteria
2. Review implementation in recovery.md
3. Create unit tests for core logic
4. Create integration tests with database markers:
   - `@pytest.mark.asyncpg` (PostgreSQL async)
   - `@pytest.mark.oracle18c` / `@pytest.mark.oracle23ai` (Oracle)
   - `@pytest.mark.aiosqlite` (SQLite async)
   - `@pytest.mark.asyncmy` (MySQL)
   - `@pytest.mark.spanner` (Google Cloud Spanner)
   - `@pytest.mark.duckdb` (DuckDB)
   - `@pytest.mark.cockroachdb_async` (CockroachDB)
   - `@pytest.mark.mssql_async` (Microsoft SQL Server)
5. Test both async and sync variants
6. Create fixtures following naming conventions:
   - `sample_user` (single instance)
   - `users_batch` (multiple instances)
7. Cover edge cases:
   - Empty results
   - Bulk operations (1000+ records)
   - Concurrent updates
   - Error conditions
8. Validate performance (no N+1 queries)
9. Update workspace and hand off to Docs & Vision

**Testing Commands Used:**
```bash
# Fast targeted testing
uv run pytest tests/integration/test_{feature}.py -m "sqlite or aiosqlite" -v

# Specific backend
uv run pytest tests/integration/test_{feature}.py -m asyncpg -v

# All Oracle versions
uv run pytest tests/integration/test_{feature}.py -m "oracle18c or oracle23ai" -v
```

**After testing, run:**
- `/review` for quality gate and documentation
- Or invoke Docs & Vision agent directly
