"""Schema routing types for the Advanced Alchemy ADK extension."""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Union


class ADKSchemaVersion(str, Enum):
    """Supported ADK persistence schema versions."""

    V1 = "1"


@dataclass
class SchemaModels:
    """Container for model classes and metadata belonging to one ADK schema version."""

    metadata: Any = None
    session_model: Any = None
    event_model: Any = None
    app_state_model: Any = None
    user_state_model: Any = None
    metadata_model: Any = None


_SCHEMA_REGISTRY: dict[ADKSchemaVersion, SchemaModels] = {}


def _coerce_schema_version(version: Union[ADKSchemaVersion, str]) -> ADKSchemaVersion:
    """Return a supported schema enum for user-supplied version values."""
    try:
        return version if isinstance(version, ADKSchemaVersion) else ADKSchemaVersion(version)
    except ValueError as exc:
        msg = f"Unsupported ADK schema version: {version!r}"
        raise ValueError(msg) from exc


def register_schema(version: Union[ADKSchemaVersion, str], models: SchemaModels) -> None:
    """Register the model bundle for an ADK schema version."""
    _SCHEMA_REGISTRY[_coerce_schema_version(version)] = models


def get_models(version: Union[ADKSchemaVersion, str] = ADKSchemaVersion.V1) -> SchemaModels:
    """Return the model bundle for an ADK schema version."""
    schema_version = _coerce_schema_version(version)
    try:
        return _SCHEMA_REGISTRY[schema_version]
    except KeyError as exc:
        msg = f"ADK schema version {schema_version.value!r} is not registered"
        raise LookupError(msg) from exc


__all__ = ("ADKSchemaVersion", "SchemaModels", "get_models", "register_schema")
