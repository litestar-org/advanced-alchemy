from collections.abc import Sequence
from typing import (
    TYPE_CHECKING,
    Any,
    Optional,
    Union,
    overload,
)

from advanced_alchemy.extensions.fastapi.cli import register_database_commands
from advanced_alchemy.extensions.fastapi.config import SQLAlchemyAsyncConfig, SQLAlchemySyncConfig
from advanced_alchemy.extensions.starlette import AdvancedAlchemy as StarletteAdvancedAlchemy
from advanced_alchemy.service import (
    Empty,
    EmptyType,
    ErrorMessages,
    LoadSpec,
    ModelT,
)

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Callable, Generator, Sequence

    from fastapi import FastAPI
    from sqlalchemy import Select

    from advanced_alchemy import filters
    from advanced_alchemy.extensions.fastapi.config import SQLAlchemyAsyncConfig, SQLAlchemySyncConfig
    from advanced_alchemy.extensions.fastapi.providers import (
        AsyncServiceT_co,
        DependencyDefaults,
        FilterConfig,
        SyncServiceT_co,
    )

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

    @overload
    def provide_service(
        self,
        service_class: type["AsyncServiceT_co"],  # pyright: ignore
        /,
        key: "Optional[str]" = None,
        statement: "Optional[Select[tuple[ModelT]]]" = None,
        error_messages: "Optional[Union[ErrorMessages, EmptyType]]" = Empty,
        load: "Optional[LoadSpec]" = None,
        execution_options: "Optional[dict[str, Any]]" = None,
        uniquify: Optional[bool] = None,
        count_with_window_function: Optional[bool] = None,
    ) -> "Callable[..., AsyncGenerator[AsyncServiceT_co, None]]": ...

    @overload
    def provide_service(
        self,
        service_class: type["SyncServiceT_co"],  # pyright: ignore
        /,
        key: "Optional[str]" = None,
        statement: "Optional[Select[tuple[ModelT]]]" = None,
        error_messages: "Optional[Union[ErrorMessages, EmptyType]]" = Empty,
        load: "Optional[LoadSpec]" = None,
        execution_options: "Optional[dict[str, Any]]" = None,
        uniquify: Optional[bool] = None,
        count_with_window_function: Optional[bool] = None,
    ) -> "Callable[..., Generator[SyncServiceT_co, None, None]]": ...

    def provide_service(  # pragma: no cover
        self,
        service_class: type[Union["AsyncServiceT_co", "SyncServiceT_co"]],
        /,
        key: "Optional[str]" = None,
        statement: "Optional[Select[tuple[ModelT]]]" = None,
        error_messages: "Optional[Union[ErrorMessages, EmptyType]]" = Empty,
        load: "Optional[LoadSpec]" = None,
        execution_options: "Optional[dict[str, Any]]" = None,
        uniquify: Optional[bool] = None,
        count_with_window_function: Optional[bool] = None,
    ) -> "Callable[..., Union[AsyncGenerator[AsyncServiceT_co, None], Generator[SyncServiceT_co, None, None]]]":
        """Provides a service instance for dependency injection.

        Args:
            service_class: The service class to provide.
            key: Optional key for the service.
            statement: Optional SQLAlchemy statement.
            error_messages: Optional error messages.
            load: Optional load specification.
            execution_options: Optional execution options.
            uniquify: Optional flag to uniquify the service.
            count_with_window_function: Optional flag to use window function for counting.

        Returns:
            A callable that returns an async generator for async services or a generator for sync services.
        """
        from advanced_alchemy.extensions.fastapi.providers import provide_service as _provide_service

        return _provide_service(
            service_class,
            extension=self,
            key=key,
            statement=statement,
            error_messages=error_messages,
            load=load,
            execution_options=execution_options,
            uniquify=uniquify,
            count_with_window_function=count_with_window_function,
        )

    @staticmethod
    def provide_filters(  # pragma: no cover
        config: "FilterConfig",
        /,
        dep_defaults: "Optional[DependencyDefaults]" = None,
    ) -> "Callable[..., list[filters.FilterTypes]]":
        """Provides filters for dependency injection.

        Args:
            config: The filters to provide.
            dep_defaults: Optional key for the filters.

        Returns:
            A callable that returns an async generator for async filters or a generator for sync filters.
        """
        from advanced_alchemy.extensions.fastapi.providers import DEPENDENCY_DEFAULTS
        from advanced_alchemy.extensions.fastapi.providers import provide_filters as _provide_filters

        if dep_defaults is None:
            dep_defaults = DEPENDENCY_DEFAULTS

        return _provide_filters(config, dep_defaults=dep_defaults)
