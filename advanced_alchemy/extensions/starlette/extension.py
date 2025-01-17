from typing import overload

from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware

from advanced_alchemy.extensions.starlette.config import SQLAlchemyAsyncConfig, SQLAlchemySyncConfig

__all__ = ("AdvancedAlchemy",)


class AdvancedAlchemy:
    """AdvancedAlchemy integration for Starlette/FastAPI applications.

    This class manages SQLAlchemy sessions and engine lifecycle within a Starlette/FastAPI application.
    It provides middleware for handling transactions based on commit strategies.
    """

    @overload
    def __init__(
        self,
        config: SQLAlchemyAsyncConfig | list[SQLAlchemyAsyncConfig],
        app: Starlette | None = None,
    ) -> None: ...

    @overload
    def __init__(
        self,
        config: SQLAlchemySyncConfig | list[SQLAlchemySyncConfig],
        app: Starlette | None = None,
    ) -> None: ...

    def __init__(
        self,
        config: SQLAlchemyAsyncConfig | SQLAlchemySyncConfig | list[SQLAlchemyAsyncConfig | SQLAlchemySyncConfig],
        app: Starlette | None = None,
    ) -> None:
        self.configs: list[SQLAlchemyAsyncConfig | SQLAlchemySyncConfig] = (
            [config] if not isinstance(config, list) else config
        )
        self._app: Starlette
        self.engine_keys: list[str] = []
        self.sessionmaker_keys: list[str] = []
        self.session_keys: list[str] = []
        if app is not None:
            self.init_app(app)

    def init_app(self, app: Starlette) -> None:
        """Initializes the Starlette/FastAPI application with SQLAlchemy engine and sessionmaker.

        Sets up middleware and shutdown handlers for managing the database engine.

        Args:
            app (starlette.applications.Starlette): The Starlette/FastAPI application instance.
        """
        for config in self.configs:
            engine = config.get_engine()
            engine_key = self._make_unique_state_key(app, f"sqla_engine_{engine.name}")
            sessionmaker_key = self._make_unique_state_key(app, f"sqla_sessionmaker_{engine.name}")
            session_key = f"sqla_session_{sessionmaker_key}"

            self.engine_keys.append(engine_key)
            self.sessionmaker_keys.append(sessionmaker_key)
            self.session_keys.append(session_key)

            setattr(app.state, engine_key, engine)
            setattr(app.state, sessionmaker_key, config.create_session_maker())

        app.add_middleware(BaseHTTPMiddleware, dispatch=self.middleware_dispatch)
        app.add_event_handler("shutdown", self.on_shutdown)  # pyright: ignore[reportUnknownMemberType]

        self._app = app

    # ... (rest of the class methods will be adapted)
