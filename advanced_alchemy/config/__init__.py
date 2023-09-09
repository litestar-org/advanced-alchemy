from __future__ import annotations

from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Mapping,
    Type,
    final,
)

from advanced_alchemy.config.asyncio import AlembicAsyncConfig, AsyncSessionConfig, SQLAlchemyAsyncConfig
from advanced_alchemy.config.common import GenericAlembicConfig, GenericSessionConfig, GenericSQLAlchemyConfig
from advanced_alchemy.config.engine import EngineConfig
from advanced_alchemy.config.sync import AlembicSyncConfig, SQLAlchemySyncConfig, SyncSessionConfig

if TYPE_CHECKING:
    from typing_extensions import TypeAlias


__all__ = (
    "AsyncSessionConfig",
    "AlembicAsyncConfig",
    "AlembicSyncConfig",
    "EngineConfig",
    "GenericSQLAlchemyConfig",
    "GenericSessionConfig",
    "GenericAlembicConfig",
    "SQLAlchemyAsyncConfig",
    "SQLAlchemySyncConfig",
    "SyncSessionConfig",
)


@final
class Empty:
    """A sentinel class used as placeholder."""


EmptyType: TypeAlias = Type[Empty]
TypeEncodersMap: TypeAlias = "Mapping[Any, Callable[[Any], Any]]"
