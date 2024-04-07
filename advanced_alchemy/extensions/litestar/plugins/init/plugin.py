from __future__ import annotations

import contextlib
from datetime import date, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from litestar.di import Provide
from litestar.dto import DTOData
from litestar.params import Dependency, Parameter
from litestar.plugins import CLIPluginProtocol, InitPluginProtocol

from advanced_alchemy.extensions.litestar.plugins import _slots_base
from advanced_alchemy.filters import (
    BeforeAfter,
    CollectionFilter,
    FilterTypes,
    LimitOffset,
    NotInCollectionFilter,
    NotInSearchFilter,
    OnBeforeAfter,
    OrderBy,
    SearchFilter,
)
from advanced_alchemy.service import OffsetPagination

if TYPE_CHECKING:
    from click import Group
    from litestar.config.app import AppConfig

    from advanced_alchemy.extensions.litestar.plugins.init.config import SQLAlchemyAsyncConfig, SQLAlchemySyncConfig

__all__ = ("SQLAlchemyInitPlugin",)

signature_namespace_values = {
    "BeforeAfter": BeforeAfter,
    "OnBeforeAfter": OnBeforeAfter,
    "CollectionFilter": CollectionFilter,
    "LimitOffset": LimitOffset,
    "OrderBy": OrderBy,
    "SearchFilter": SearchFilter,
    "NotInCollectionFilter": NotInCollectionFilter,
    "NotInSearchFilter": NotInSearchFilter,
    "FilterTypes": FilterTypes,
    "OffsetPagination": OffsetPagination,
    "Parameter": Parameter,
    "Dependency": Dependency,
    "DTOData": DTOData,
    "UUID": UUID,
    "date": date,
    "datetime": datetime,
}


class SQLAlchemyInitPlugin(InitPluginProtocol, CLIPluginProtocol, _slots_base.SlotsBase):
    """SQLAlchemy application lifecycle configuration."""

    def __init__(self, config: SQLAlchemyAsyncConfig | SQLAlchemySyncConfig) -> None:
        """Initialize ``SQLAlchemyPlugin``.

        Args:
            config: configure DB connection and hook handlers and dependencies.
        """
        self._config = config
        self._alembic_config = config.alembic_config

    def on_cli_init(self, cli: Group) -> None:
        from advanced_alchemy.extensions.litestar.cli import database_group

        cli.add_command(database_group)
        return super().on_cli_init(cli)

    def on_app_init(self, app_config: AppConfig) -> AppConfig:
        """Configure application for use with SQLAlchemy.

        Args:
            app_config: The :class:`AppConfig <.config.app.AppConfig>` instance.
        """
        with contextlib.suppress(ImportError):
            from asyncpg.pgproto import pgproto  # pyright: ignore[reportMissingImports]

            signature_namespace_values.update({"pgproto.UUID": pgproto.UUID})
            app_config.type_encoders = {pgproto.UUID: str, **(app_config.type_encoders or {})}
        with contextlib.suppress(ImportError):
            import uuid_utils  # pyright: ignore[reportMissingImports]

            signature_namespace_values.update({"uuid_utils.UUID": uuid_utils.UUID})
            app_config.type_encoders = {uuid_utils.UUID: str, **(app_config.type_encoders or {})}
            app_config.type_decoders = [
                (lambda x: x is uuid_utils.UUID, lambda t, v: t(str(v))),
                *(app_config.type_decoders or []),
            ]
        app_config.signature_namespace.update(self._config.signature_namespace)
        app_config.signature_namespace.update(signature_namespace_values)
        app_config.lifespan.append(self._config.lifespan)
        app_config.dependencies.update(
            {
                self._config.engine_dependency_key: Provide(self._config.provide_engine, sync_to_thread=False),
                self._config.session_dependency_key: Provide(self._config.provide_session, sync_to_thread=False),
            },
        )
        app_config.before_send.append(self._config.before_send_handler)
        return app_config
