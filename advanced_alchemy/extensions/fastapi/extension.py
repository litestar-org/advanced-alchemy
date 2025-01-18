from __future__ import annotations

from typing import TYPE_CHECKING, Sequence

from fastapi_cli.cli import app as fastapi_cli_app

from advanced_alchemy.extensions.fastapi.cli import register_database_commands
from advanced_alchemy.extensions.starlette import AdvancedAlchemy as StarletteAdvancedAlchemy

if TYPE_CHECKING:
    from fastapi import FastAPI

    from advanced_alchemy.extensions.fastapi.config import SQLAlchemyAsyncConfig, SQLAlchemySyncConfig

__all__ = ("AdvancedAlchemy",)


def assign_cli_group(app: FastAPI) -> None:
    from typer.main import get_group

    click_app = get_group(fastapi_cli_app)
    click_app.add_command(register_database_commands(app))


class AdvancedAlchemy(StarletteAdvancedAlchemy):
    """AdvancedAlchemy integration for FastAPI applications.

    This class manages SQLAlchemy sessions and engine lifecycle within a FastAPI application.
    It provides middleware for handling transactions based on commit strategies.
    """

    def __init__(
        self,
        config: SQLAlchemyAsyncConfig | SQLAlchemySyncConfig | Sequence[SQLAlchemyAsyncConfig | SQLAlchemySyncConfig],
        app: FastAPI | None = None,
    ) -> None:
        super().__init__(config, app)

    def init_app(self, app: FastAPI) -> None:  # type: ignore[override]
        """Initializes the FastAPI application with SQLAlchemy engine and sessionmaker.

        Sets up middleware and shutdown handlers for managing the database engine.

        Args:
            app (fastapi.FastAPI): The FastAPI application instance.
        """
        super().init_app(app)
        assign_cli_group(app)
        app.state.advanced_alchemy = self

    async def on_shutdown(self) -> None:
        await super().on_shutdown()
        delattr(self.app.state, "advanced_alchemy")
