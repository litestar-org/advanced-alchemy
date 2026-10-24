"""Litestar extension for Advanced Alchemy."""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

from advanced_alchemy.alembic.commands import AlembicCommands
from advanced_alchemy.config import AlembicAsyncConfig, AlembicSyncConfig, AsyncSessionConfig, SyncSessionConfig
from advanced_alchemy.extensions.litestar import providers, session, store
from advanced_alchemy.extensions.litestar.cli import get_database_migration_plugin
from advanced_alchemy.extensions.litestar.dto import SQLAlchemyDTO, SQLAlchemyDTOConfig
from advanced_alchemy.extensions.litestar.plugins import (
    EngineConfig,
    SQLAlchemyAsyncConfig,
    SQLAlchemyInitPlugin,
    SQLAlchemyPlugin,
    SQLAlchemySerializationPlugin,
    SQLAlchemySyncConfig,
)
from advanced_alchemy.extensions.litestar.plugins.init.config.asyncio import (
    autocommit_before_send_handler as async_autocommit_before_send_handler,
)
from advanced_alchemy.extensions.litestar.plugins.init.config.asyncio import (
    autocommit_handler_maker as async_autocommit_handler_maker,
)
from advanced_alchemy.extensions.litestar.plugins.init.config.asyncio import (
    default_before_send_handler as async_default_before_send_handler,
)
from advanced_alchemy.extensions.litestar.plugins.init.config.asyncio import (
    default_handler_maker as async_default_handler_maker,
)
from advanced_alchemy.extensions.litestar.plugins.init.config.sync import (
    autocommit_before_send_handler as sync_autocommit_before_send_handler,
)
from advanced_alchemy.extensions.litestar.plugins.init.config.sync import (
    autocommit_handler_maker as sync_autocommit_handler_maker,
)
from advanced_alchemy.extensions.litestar.plugins.init.config.sync import (
    default_before_send_handler as sync_default_before_send_handler,
)
from advanced_alchemy.extensions.litestar.plugins.init.config.sync import (
    default_handler_maker as sync_default_handler_maker,
)

if TYPE_CHECKING:
    from advanced_alchemy.extensions.litestar import (
        base,
        exceptions,
        filters,
        mixins,
        operations,
        repository,
        service,
        types,
        utils,
    )

_LAZY_SUBMODULES = frozenset(
    {
        "base",
        "exceptions",
        "filters",
        "mixins",
        "operations",
        "repository",
        "service",
        "types",
        "utils",
    }
)

__all__ = (
    "AlembicAsyncConfig",
    "AlembicCommands",
    "AlembicSyncConfig",
    "AsyncSessionConfig",
    "EngineConfig",
    "SQLAlchemyAsyncConfig",
    "SQLAlchemyDTO",
    "SQLAlchemyDTOConfig",
    "SQLAlchemyInitPlugin",
    "SQLAlchemyPlugin",
    "SQLAlchemySerializationPlugin",
    "SQLAlchemySyncConfig",
    "SyncSessionConfig",
    "async_autocommit_before_send_handler",
    "async_autocommit_handler_maker",
    "async_default_before_send_handler",
    "async_default_handler_maker",
    "base",
    "exceptions",
    "filters",
    "get_database_migration_plugin",
    "mixins",
    "operations",
    "providers",
    "repository",
    "service",
    "session",
    "store",
    "sync_autocommit_before_send_handler",
    "sync_autocommit_handler_maker",
    "sync_default_before_send_handler",
    "sync_default_handler_maker",
    "types",
    "utils",
)


def __getattr__(attr_name: str) -> object:
    """Lazily import Litestar extension submodules."""
    if attr_name in _LAZY_SUBMODULES:
        module = importlib.import_module(f"advanced_alchemy.extensions.litestar.{attr_name}")
        globals()[attr_name] = module
        return module
    msg = f"module {__name__!r} has no attribute {attr_name!r}"
    raise AttributeError(msg)


def __dir__() -> list[str]:
    """Return package attributes including lazily re-exported submodules."""
    return sorted(set(globals()).union(__all__))
