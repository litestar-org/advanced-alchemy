from dataclasses import dataclass, field
from typing import Literal

from litestar.types import BeforeMessageSendHookHandler

from advanced_alchemy.config.asyncio import SQLAlchemyAsyncConfig as _SQLAlchemyAsyncConfig
from advanced_alchemy.config.sync import SQLAlchemySyncConfig as _SQLAlchemySyncConfig
from advanced_alchemy.extensions.litestar.plugins.init.config.common import SESSION_SCOPE_KEY
from advanced_alchemy.extensions.litestar.plugins.init.config.engine import EngineConfig


@dataclass
class SQLAlchemyAsyncConfig(_SQLAlchemyAsyncConfig):
    """SQLAlchemy Async config for FastAPI."""

    # ... (add FastAPI-specific config options)
    before_send_handler: BeforeMessageSendHookHandler | None | Literal["autocommit", "autocommit_include_redirects"] = (
        None
    )
    """Handler to call before the ASGI message is sent.

    The handler should handle closing the session stored in the ASGI scope, if it's still open, and committing and
    uncommitted data.
    """
    engine_dependency_key: str = "db_engine"
    """Key to use for the dependency injection of database engines."""
    session_dependency_key: str = "db_session"
    """Key to use for the dependency injection of database sessions."""
    engine_app_state_key: str = "db_engine"
    """Key under which to store the SQLAlchemy engine in the application :class:`State <litestar.datastructures.State>`
    instance.
    """
    session_maker_app_state_key: str = "session_maker_class"
    """Key under which to store the SQLAlchemy :class:`sessionmaker <sqlalchemy.orm.sessionmaker>` in the application
    :class:`State <litestar.datastructures.State>` instance.
    """
    session_scope_key: str = SESSION_SCOPE_KEY
    """Key under which to store the SQLAlchemy scope in the application."""
    engine_config: EngineConfig = field(default_factory=EngineConfig)  # pyright: ignore[reportIncompatibleVariableOverride]
    """Configuration for the SQLAlchemy engine.

    The configuration options are documented in the SQLAlchemy documentation.
    """
    set_default_exception_handler: bool = True
    """Sets the default exception handler on application start."""


@dataclass
class SQLAlchemySyncConfig(_SQLAlchemySyncConfig):
    """SQLAlchemy Sync config for FastAPI."""

    # ... (add FastAPI-specific config options)
    before_send_handler: BeforeMessageSendHookHandler | None | Literal["autocommit", "autocommit_include_redirects"] = (
        None
    )
    """Handler to call before the ASGI message is sent.

    The handler should handle closing the session stored in the ASGI scope, if it's still open, and committing and
    uncommitted data.
    """
    engine_dependency_key: str = "db_engine"
    """Key to use for the dependency injection of database engines."""
    session_dependency_key: str = "db_session"
    """Key to use for the dependency injection of database sessions."""
    engine_app_state_key: str = "db_engine"
    """Key under which to store the SQLAlchemy engine in the application :class:`State <litestar.datastructures.State>`
    instance.
    """
    session_maker_app_state_key: str = "session_maker_class"
    """Key under which to store the SQLAlchemy :class:`sessionmaker <sqlalchemy.orm.sessionmaker>` in the application
    :class:`State <litestar.datastructures.State>` instance.
    """
    session_scope_key: str = SESSION_SCOPE_KEY
    """Key under which to store the SQLAlchemy scope in the application."""
    engine_config: EngineConfig = field(default_factory=EngineConfig)  # pyright: ignore[reportIncompatibleVariableOverride]
    """Configuration for the SQLAlchemy engine.

    The configuration options are documented in the SQLAlchemy documentation.
    """
    set_default_exception_handler: bool = True
    """Sets the default exception handler on application start."""
