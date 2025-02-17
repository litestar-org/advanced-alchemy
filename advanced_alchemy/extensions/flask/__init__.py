"""Flask extension for Advanced Alchemy.

This module provides Flask integration for Advanced Alchemy, including session management,
database migrations, and service utilities.
"""

from advanced_alchemy import base, exceptions, filters, mixins, operations, repository, service, types, utils
from advanced_alchemy.alembic.commands import AlembicCommands
from advanced_alchemy.config import AlembicAsyncConfig, AlembicSyncConfig, AsyncSessionConfig, SyncSessionConfig
from advanced_alchemy.extensions.flask.cli import get_database_migration_plugin
from advanced_alchemy.extensions.flask.config import EngineConfig, SQLAlchemyAsyncConfig, SQLAlchemySyncConfig
from advanced_alchemy.extensions.flask.extension import AdvancedAlchemy
from advanced_alchemy.extensions.flask.utils import FlaskServiceMixin

__all__ = (
    "AdvancedAlchemy",
    "AlembicAsyncConfig",
    "AlembicCommands",
    "AlembicSyncConfig",
    "AsyncSessionConfig",
    "EngineConfig",
    "FlaskServiceMixin",
    "SQLAlchemyAsyncConfig",
    "SQLAlchemySyncConfig",
    "SyncSessionConfig",
    "base",
    "exceptions",
    "filters",
    "get_database_migration_plugin",
    "mixins",
    "operations",
    "repository",
    "service",
    "types",
    "utils",
)
