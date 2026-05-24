"""Google Agent Development Kit integration for Advanced Alchemy."""

import sys

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

__all__ = (
    "DEFAULT_MAX_KEY_LENGTH",
    "DEFAULT_MAX_VARCHAR_LENGTH",
    "LATEST_SCHEMA_VERSION",
    "ADKAppState",
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
