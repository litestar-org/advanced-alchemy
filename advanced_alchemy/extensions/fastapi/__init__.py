"""FastAPI extension for Advanced Alchemy.

This module provides FastAPI integration for Advanced Alchemy, including session management,
database migrations, and service utilities.

"""

from advanced_alchemy import base, exceptions, filters, mixins, operations, repository, service, types, utils
from advanced_alchemy.alembic.commands import AlembicCommands
from advanced_alchemy.config import AlembicAsyncConfig, AlembicSyncConfig, AsyncSessionConfig, SyncSessionConfig
from advanced_alchemy.extensions.fastapi import providers
from advanced_alchemy.extensions.fastapi.cli import get_database_migration_plugin
from advanced_alchemy.extensions.fastapi.config import (
    AppStateKeys,
    EngineConfig,
    SQLAlchemyAsyncConfig,
    SQLAlchemySyncConfig,
    StarletteSessionConfig,
)
from advanced_alchemy.extensions.fastapi.extension import AdvancedAlchemy, assign_cli_group

__all__ = (
    "AdvancedAlchemy",
    "AlembicAsyncConfig",
    "AlembicCommands",
    "AlembicSyncConfig",
    "AppStateKeys",
    "AsyncSessionConfig",
    "EngineConfig",
    "SQLAlchemyAsyncConfig",
    "SQLAlchemySyncConfig",
    "StarletteSessionConfig",
    "SyncSessionConfig",
    "assign_cli_group",
    "base",
    "exceptions",
    "filters",
    "get_database_migration_plugin",
    "mixins",
    "operations",
    "providers",
    "repository",
    "service",
    "types",
    "utils",
)
