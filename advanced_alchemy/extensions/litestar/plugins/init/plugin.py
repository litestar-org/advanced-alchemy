from __future__ import annotations

import contextlib
from datetime import date, datetime
from typing import TYPE_CHECKING, Any, Sequence, cast
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
    from litestar.types import BeforeMessageSendHookHandler

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

    def __init__(
        self,
        config: SQLAlchemyAsyncConfig | SQLAlchemySyncConfig | Sequence[SQLAlchemyAsyncConfig | SQLAlchemySyncConfig],
    ) -> None:
        """Initialize ``SQLAlchemyPlugin``.

        Args:
            config: configure DB connection and hook handlers and dependencies.
        """
        self._config = config

    @property
    def config(
        self,
    ) -> SQLAlchemyAsyncConfig | SQLAlchemySyncConfig | Sequence[SQLAlchemyAsyncConfig | SQLAlchemySyncConfig]:
        return self.config

    def on_cli_init(self, cli: Group) -> None:
        from advanced_alchemy.extensions.litestar.cli import database_group

        cli.add_command(database_group)

    def on_app_init(self, app_config: AppConfig) -> AppConfig:
        """Configure application for use with SQLAlchemy.

        Args:
            app_config: The :class:`AppConfig <.config.app.AppConfig>` instance.
        """
        signature_namespace_values: dict[str, Any] = {}
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
        if isinstance(self._config, Sequence):
            for config in self._config:
                signature_namespace_values.update(config.signature_namespace)
                app_config.lifespan.append(config.lifespan)  # pyright: ignore[reportUnknownMemberType]

                app_config.dependencies.update(
                    {
                        config.engine_dependency_key: Provide(config.provide_engine, sync_to_thread=False),
                        config.session_dependency_key: Provide(config.provide_session, sync_to_thread=False),
                    },
                )
                app_config.before_send.append(cast("BeforeMessageSendHookHandler", config.before_send_handler))
        else:
            signature_namespace_values.update(self._config.signature_namespace)
            app_config.lifespan.append(self._config.lifespan)  # pyright: ignore[reportUnknownMemberType]
            app_config.dependencies.update(
                {
                    self._config.engine_dependency_key: Provide(self._config.provide_engine, sync_to_thread=False),
                    self._config.session_dependency_key: Provide(self._config.provide_session, sync_to_thread=False),
                },
            )
            app_config.before_send.append(cast("BeforeMessageSendHookHandler", self._config.before_send_handler))
        app_config.signature_namespace.update(signature_namespace_values)

        return app_config
