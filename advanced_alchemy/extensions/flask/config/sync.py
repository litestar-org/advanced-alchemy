"""Flask-specific synchronous SQLAlchemy configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Mapping

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from advanced_alchemy.config.sync import SQLAlchemySyncConfig as _SQLAlchemySyncConfig
from advanced_alchemy.extensions.flask.config.common import SESSION_SCOPE_KEY

if TYPE_CHECKING:
    from flask import Flask


@dataclass
class SQLAlchemySyncConfig(_SQLAlchemySyncConfig):
    """Flask-specific synchronous SQLAlchemy configuration."""

    app: Flask | None = None
    """The Flask application instance."""
    session_options: Mapping[str, Any] = field(default_factory=dict)
    """Additional options to pass to the session maker."""
    session_scope_key: str = SESSION_SCOPE_KEY
    """Key under which to store the SQLAlchemy session in the Flask application context."""

    def _ensure_unique(self, registry_name: str, key: str, new_key: str | None = None, _iter: int = 0) -> str:
        new_key = new_key if new_key is not None else key
        if new_key in getattr(self.__class__, registry_name, {}):
            _iter += 1
            new_key = self._ensure_unique(registry_name, key, f"{key}_{_iter}", _iter)
        return new_key

    def __post_init__(self) -> None:
        self.session_scope_key = self._ensure_unique("_SESSION_SCOPE_KEY_REGISTRY", self.session_scope_key)
        self.__class__._SESSION_SCOPE_KEY_REGISTRY.add(self.session_scope_key)  # noqa: SLF001

    def create_session_maker(self) -> Callable[[], Session]:
        """Get a session maker. If none exists yet, create one.

        Returns:
            Session factory used by the plugin.
        """
        if self.session_maker:
            return self.session_maker

        session_kws = self.session_config_dict
        if session_kws.get("bind") is None:
            session_kws["bind"] = self.get_engine()
        self.session_maker = self.session_maker_class(**session_kws)
        return self.session_maker

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
