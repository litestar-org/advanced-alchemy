from __future__ import annotations

from advanced_alchemy.config import SQLAlchemyAsyncConfig, SQLAlchemySyncConfig

# Keep the original sync configs for backward compatibility
configs = [SQLAlchemySyncConfig(connection_string="sqlite:///:memory:")]

# Add async configs for new external config loading tests
async_configs = [
    SQLAlchemyAsyncConfig(
        connection_string="sqlite+aiosqlite:///:memory:",
        bind_key="default",
    ),
    SQLAlchemyAsyncConfig(
        connection_string="sqlite+aiosqlite:///:memory:",
        bind_key="secondary",
    ),
]

# Single config for basic tests
config = SQLAlchemyAsyncConfig(
    connection_string="sqlite+aiosqlite:///:memory:",
    bind_key="default",
)
