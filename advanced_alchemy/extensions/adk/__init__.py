"""Google Agent Development Kit integration for Advanced Alchemy."""

import sys
from typing import Any

if sys.version_info < (3, 10):
    msg = "advanced_alchemy.extensions.adk requires Python 3.10 or later"
    raise RuntimeError(msg)

from advanced_alchemy.extensions.adk._constants import (
    DEFAULT_MAX_KEY_LENGTH,
    DEFAULT_MAX_VARCHAR_LENGTH,
    LATEST_SCHEMA_VERSION,
)
from advanced_alchemy.extensions.adk._types import ADKSchemaVersion, SchemaModels, get_models, register_schema
from advanced_alchemy.extensions.adk.service import ADKAsyncSessionService, ADKSyncSessionService
from advanced_alchemy.extensions.adk.v1 import ADKAppState, ADKEvent, ADKMetadata, ADKSession, ADKUserState


def __getattr__(name: str) -> Any:
    """Lazily expose optional ADK extension tables without mutating v1 metadata on base import."""
    if name in {"ADKArtifact", "ADKAsyncArtifactService"}:
        from advanced_alchemy.extensions.adk.artifacts import ADKArtifact, ADKAsyncArtifactService

        return {"ADKArtifact": ADKArtifact, "ADKAsyncArtifactService": ADKAsyncArtifactService}[name]
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)


__all__ = (
    "DEFAULT_MAX_KEY_LENGTH",
    "DEFAULT_MAX_VARCHAR_LENGTH",
    "LATEST_SCHEMA_VERSION",
    "ADKAppState",
    "ADKArtifact",
    "ADKAsyncArtifactService",
    "ADKAsyncSessionService",
    "ADKEvent",
    "ADKMetadata",
    "ADKSchemaVersion",
    "ADKSession",
    "ADKSyncSessionService",
    "ADKUserState",
    "SchemaModels",
    "get_models",
    "register_schema",
)
