from typing import TYPE_CHECKING, Optional, Union

from advanced_alchemy.extensions.fastapi.cli import register_database_commands
from advanced_alchemy.extensions.starlette import AdvancedAlchemy as StarletteAdvancedAlchemy

if TYPE_CHECKING:
    from collections.abc import Sequence

    from fastapi import FastAPI

    from advanced_alchemy.extensions.fastapi.config import SQLAlchemyAsyncConfig, SQLAlchemySyncConfig

__all__ = ("AdvancedAlchemy",)


def assign_cli_group(app: "FastAPI") -> None:  # pragma: no cover
    try:
        from fastapi_cli.cli import app as fastapi_cli_app  # pyright: ignore[reportUnknownVariableType]
        from typer.main import get_group
    except ImportError:
        print("FastAPI CLI is not installed.  Skipping CLI registration.")  # noqa: T201
        return
    click_app = get_group(fastapi_cli_app)  # pyright: ignore[reportUnknownArgumentType]
    click_app.add_command(register_database_commands(app))


class AdvancedAlchemy(StarletteAdvancedAlchemy):
    """AdvancedAlchemy integration for FastAPI applications.

    This class manages SQLAlchemy sessions and engine lifecycle within a FastAPI application.
    It provides middleware for handling transactions based on commit strategies.
    """

    def __init__(
        self,
        config: "Union[SQLAlchemyAsyncConfig, SQLAlchemySyncConfig, Sequence[Union[SQLAlchemyAsyncConfig, SQLAlchemySyncConfig]]]",
        app: "Optional[FastAPI]" = None,
    ) -> None:
        super().__init__(config, app)
