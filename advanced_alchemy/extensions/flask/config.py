from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Mapping

from sqlalchemy import Engine, create_engine
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

from advanced_alchemy.config.asyncio import SQLAlchemyAsyncConfig as _SQLAlchemyAsyncConfig

if TYPE_CHECKING:
    from flask import Flask


@dataclass
class SQLAlchemyAsyncConfig(_SQLAlchemyAsyncConfig):
    """Flask-specific async SQLAlchemy configuration."""

    app: Flask | None = None
    session_options: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.session_scope_key = self._ensure_unique("_SESSION_SCOPE_KEY_REGISTRY", self.session_scope_key)
        self.engine_app_state_key = self._ensure_unique("_ENGINE_APP_STATE_KEY_REGISTRY", self.engine_app_state_key)
        self.session_maker_app_state_key = self._ensure_unique(
            "_SESSIONMAKER_APP_STATE_KEY_REGISTRY",
            self.session_maker_app_state_key,
        )
        self.__class__._SESSION_SCOPE_KEY_REGISTRY.add(self.session_scope_key)  # noqa: SLF001
        self.__class__._ENGINE_APP_STATE_KEY_REGISTRY.add(self.engine_app_state_key)  # noqa: SLF001
        self.__class__._SESSIONMAKER_APP_STATE_KEY_REGISTRY.add(self.session_maker_app_state_key)  # noqa: SLF001
        if self.before_send_handler is None:
            self.before_send_handler = default_handler_maker(session_scope_key=self.session_scope_key)
        if self.before_send_handler == "autocommit":
            self.before_send_handler = autocommit_handler_maker(session_scope_key=self.session_scope_key)
        if self.before_send_handler == "autocommit_include_redirects":
            self.before_send_handler = autocommit_handler_maker(
                session_scope_key=self.session_scope_key,
                commit_on_redirect=True,
            )
        super().__post_init__()

    def create_engine(self) -> AsyncEngine:
        """Create the SQLAlchemy async engine.

        Returns:
            AsyncEngine: The configured SQLAlchemy async engine
        """
        engine = create_async_engine(self.connection_string, **self.engine_config)
        if self.app is not None:
            self.app.extensions[f"sqlalchemy_engine_{self.bind_key}"] = engine
        return engine

    def create_session_maker(self) -> Callable[[], AsyncSession]:
        """Get a session maker. If none exists yet, create one.

        Returns:
            Session factory used by the plugin.
        """
        if self.session_maker:
            return self.session_maker

        session_kws = self.session_config_dict
        if session_kws.get("bind") is None:
            session_kws["bind"] = self.get_engine()
        return self.session_maker_class(**session_kws)  # pyright: ignore[reportUnknownVariableType,reportUnknownMemberType]

    def create_session_factory(self) -> sessionmaker[AsyncSession]:
        """Create the SQLAlchemy async session factory.

        Returns:
            sessionmaker[AsyncSession]: The configured SQLAlchemy async session factory
        """
        session_factory = sessionmaker(
            bind=self.get_engine(),
            class_=AsyncSession,
            **self.session_options,
        )
        if self.app is not None:
            self.app.extensions[f"sqlalchemy_session_{self.bind_key}"] = session_factory
        return session_factory


@dataclass
class FlaskSQLAlchemySyncConfig(SQLAlchemySyncConfig):
    """Flask-specific sync SQLAlchemy configuration."""

    app: Flask | None = None
    session_options: Mapping[str, Any] = field(default_factory=dict)

    def create_engine(self) -> Engine:
        """Create the SQLAlchemy sync engine.

        Returns:
            Engine: The configured SQLAlchemy sync engine
        """
        engine = create_engine(self.connection_string, **self.engine_config)
        if self.app is not None:
            self.app.extensions[f"sqlalchemy_engine_{self.bind_key}"] = engine
        return engine

    def create_session_factory(self) -> sessionmaker[Session]:
        """Create the SQLAlchemy sync session factory.

        Returns:
            sessionmaker[Session]: The configured SQLAlchemy sync session factory
        """
        session_factory = sessionmaker(
            bind=self.get_engine(),
            **self.session_options,
        )
        if self.app is not None:
            self.app.extensions[f"sqlalchemy_session_{self.bind_key}"] = session_factory
        return session_factory
