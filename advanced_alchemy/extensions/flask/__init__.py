"""Flask extension for Advanced Alchemy.

This module provides Flask integration for Advanced Alchemy, including session management,
database migrations, and service utilities.

Example:
    Basic usage with synchronous SQLAlchemy:

    ```python
    from flask import Flask
    from advanced_alchemy.extensions.flask import (
        AdvancedAlchemy,
        SQLAlchemySyncConfig,
        EngineConfig,
    )

    app = Flask(__name__)

    db_config = SQLAlchemySyncConfig(
        engine_config=EngineConfig(url="sqlite:///db.sqlite3"),
        create_all=True,  # Create tables on startup
    )

    db = AdvancedAlchemy(config=db_config)
    db.init_app(app)


    # Get a session in your route
    @app.route("/")
    def index():
        session = db.get_session()
        # Use session...
    ```

    Using async SQLAlchemy:

    ```python
    from advanced_alchemy.extensions.flask import (
        AdvancedAlchemy,
        SQLAlchemyAsyncConfig,
    )

    app = Flask(__name__)

    db_config = SQLAlchemyAsyncConfig(
        engine_config=EngineConfig(
            url="postgresql+asyncpg://user:pass@localhost/db"
        ),
        create_all=True,
    )

    db = AdvancedAlchemy(config=db_config)
    db.init_app(app)
    ```
"""

from advanced_alchemy import base, exceptions, filters, mixins, operations, repository, service, types, utils
from advanced_alchemy.alembic.commands import AlembicCommands
from advanced_alchemy.config import AlembicAsyncConfig, AlembicSyncConfig, AsyncSessionConfig, SyncSessionConfig
from advanced_alchemy.extensions.flask.cli import get_database_migration_plugin
from advanced_alchemy.extensions.flask.config import EngineConfig, SQLAlchemyAsyncConfig, SQLAlchemySyncConfig
from advanced_alchemy.extensions.flask.extension import AdvancedAlchemy
from advanced_alchemy.extensions.flask.service import FlaskServiceMixin

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
