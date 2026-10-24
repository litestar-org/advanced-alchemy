"""Google Agent Development Kit v2+ integration for Advanced Alchemy."""

import sys

if sys.version_info < (3, 10):
    msg = "advanced_alchemy.extensions.adk requires Python 3.10 or later"
    raise RuntimeError(msg)

from advanced_alchemy.extensions.adk._constants import (
    DEFAULT_MAX_KEY_LENGTH,
    DEFAULT_MAX_VARCHAR_LENGTH,
    MIN_GOOGLE_ADK_VERSION,
)
from advanced_alchemy.extensions.adk._exceptions import StaleSessionError
from advanced_alchemy.extensions.adk.models import (
    DEFAULT_ARTIFACT_BACKEND_KEY,
    USER_SCOPE_SESSION_ID,
    ADKAppStateModelMixin,
    ADKArtifactModelMixin,
    ADKEventModelMixin,
    ADKMemoryModelMixin,
    ADKSessionModelConfig,
    ADKSessionModelMixin,
    ADKUserStateModelMixin,
)
from advanced_alchemy.extensions.adk.plugins import ADKServiceConfig
from advanced_alchemy.extensions.adk.service import ADKAsyncSessionService, ADKSyncSessionService

__all__ = (
    "DEFAULT_ARTIFACT_BACKEND_KEY",
    "DEFAULT_MAX_KEY_LENGTH",
    "DEFAULT_MAX_VARCHAR_LENGTH",
    "MIN_GOOGLE_ADK_VERSION",
    "USER_SCOPE_SESSION_ID",
    "ADKAppStateModelMixin",
    "ADKArtifactModelMixin",
    "ADKAsyncSessionService",
    "ADKEventModelMixin",
    "ADKMemoryModelMixin",
    "ADKServiceConfig",
    "ADKSessionModelConfig",
    "ADKSessionModelMixin",
    "ADKSyncSessionService",
    "ADKUserStateModelMixin",
    "StaleSessionError",
)
