# DuckDB

DuckDB driver configuration and Advanced Alchemy-specific patterns.

## Driver

```bash
uv add duckdb duckdb-engine
```

**Note:** DuckDB has no native async support. Use sync configurations or `async_()` from `advanced_alchemy.utils.sync_tools` to convert sync operations.

```python
from advanced_alchemy.extensions.flask import SQLAlchemySyncConfig

# In-memory database
config = SQLAlchemySyncConfig(
    connection_string="duckdb:///:memory:"
)

# File-based database
config = SQLAlchemySyncConfig(
    connection_string="duckdb:///analytics.duckdb"
)

# Read-only mode
config = SQLAlchemySyncConfig(
    connection_string="duckdb:///analytics.duckdb?read_only=true"
)
```

## Using with Async Frameworks

Convert sync DuckDB operations to async:

```python
from advanced_alchemy.utils.sync_tools import async_

def run_analytics_query(repository: "AnalyticsRepository") -> "list[Analytics]":
    """Sync DuckDB query."""
    return repository.list()

# Convert to async
run_analytics_query_async = async_(run_analytics_query)

# Use in async context
results = await run_analytics_query_async(repository)
```

## Advanced Alchemy Type Mappings

DuckDB supports most SQLAlchemy types but stores them differently:

```python
from advanced_alchemy.base import BigIntAuditBase
from advanced_alchemy.types import JsonB
from sqlalchemy.orm import Mapped, mapped_column

class SalesEvent(BigIntAuditBase):
    __tablename__ = "sales_events"

    product_id: "Mapped[int]"
    amount: "Mapped[float]"
    metadata: "Mapped[dict]" = mapped_column(JsonB)  # Stored as JSON
```

## pytest Markers

```python
import pytest

@pytest.mark.duckdb
def test_analytics_query(duckdb_engine):
    """Test DuckDB analytical query."""
    pass
```

Run tests:

```bash
# Run only DuckDB tests
uv run pytest tests/ -m duckdb -v
```

## Common Gotchas

### No Native Async

DuckDB is sync-only. Use `async_()` utility for async frameworks:

```python
# ❌ No async support
from advanced_alchemy.extensions.litestar import SQLAlchemyAsyncConfig
config = SQLAlchemyAsyncConfig(
    connection_string="duckdb:///:memory:"  # Won't work!
)

# ✅ Use sync configuration
from advanced_alchemy.extensions.flask import SQLAlchemySyncConfig
config = SQLAlchemySyncConfig(
    connection_string="duckdb:///:memory:"
)
```

### Single-Writer Model

DuckDB uses single-writer model:

```python
# ❌ Concurrent writes will block
async def concurrent_writes():
    await write_batch_1()
    await write_batch_2()  # Must wait

# ✅ Use bulk operations
repository.create_many(all_records)
```

### Connection Pooling

DuckDB doesn't benefit from large pools:

```python
config = SQLAlchemySyncConfig(
    connection_string="duckdb:///analytics.duckdb",
    pool_size=1,  # Single connection is best
)
```

## Direct File Querying

Query Parquet and CSV files without loading:

```python
from sqlalchemy import text

# Query Parquet files
stmt = text("""
    SELECT product_id, SUM(amount) as total_revenue
    FROM read_parquet('sales_data/*.parquet')
    GROUP BY product_id
    ORDER BY total_revenue DESC
    LIMIT 10
""")
results = session.execute(stmt)
```

## See Also

- [PostgreSQL Guide](../database-backends/postgresql.md) - For OLTP workloads
- [Quick Reference](../quick-reference/quick-reference.md) - Common patterns
- [Testing Guide](../testing/integration.md) - pytest-databases usage
- [DuckDB Documentation](https://duckdb.org/docs/) - Official DuckDB docs
- [duckdb-engine Documentation](https://github.com/Mause/duckdb_engine) - SQLAlchemy dialect
