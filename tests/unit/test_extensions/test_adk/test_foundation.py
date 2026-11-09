import importlib
import sys
from pathlib import Path

import pytest
from sqlalchemy import Column, MetaData, Table
from sqlalchemy.dialects import mysql
from sqlalchemy.schema import CreateTable

from tests.helpers import purge_module


def test_adk_extension_imports_on_supported_python() -> None:
    adk = importlib.import_module("advanced_alchemy.extensions.adk")

    assert adk.ADKSchemaVersion.V1.value == "1"
    assert adk.DEFAULT_MAX_KEY_LENGTH == 128
    assert adk.DEFAULT_MAX_VARCHAR_LENGTH == 256
    assert adk.LATEST_SCHEMA_VERSION == "1"


def test_adk_extension_rejects_python_before_adk_supported_floor(monkeypatch: pytest.MonkeyPatch) -> None:
    purge_module(["advanced_alchemy.extensions.adk"], __file__)
    monkeypatch.setattr(sys, "version_info", (3, 9, 0, "final", 0))

    with pytest.raises(RuntimeError, match=r"requires Python 3\.10 or later"):
        importlib.import_module("advanced_alchemy.extensions.adk")

    purge_module(["advanced_alchemy.extensions.adk"], __file__)


def test_schema_registry_round_trips_registered_model_bundle() -> None:
    from advanced_alchemy.extensions.adk import ADKSchemaVersion, SchemaModels, get_models, register_schema

    class Marker:
        pass

    models = SchemaModels(
        metadata=Marker,
        session_model=Marker,
        event_model=Marker,
        app_state_model=Marker,
        user_state_model=Marker,
        metadata_model=Marker,
    )

    register_schema(ADKSchemaVersion.V1, models)

    assert get_models(ADKSchemaVersion.V1) is models
    assert get_models("1") is models


def test_register_schema_rejects_unknown_version() -> None:
    from advanced_alchemy.extensions.adk import SchemaModels, register_schema

    with pytest.raises(ValueError, match="Unsupported ADK schema version"):
        register_schema("2", SchemaModels())


def test_adk_optional_dependency_markers_match_current_google_adk_python_floor() -> None:
    pyproject = Path("pyproject.toml").read_text()

    assert "adk = [\"google-adk>=2.0.0; python_version>='3.10'\"]" in pyproject
    assert 'adk-vector = ["advanced-alchemy[adk]", "pgvector>=0.2.5"]' in pyproject


def test_datetime_utc_fsp_compiles_to_mysql_datetime_precision() -> None:
    from advanced_alchemy.types.datetime import DateTimeUTC

    metadata = MetaData()
    table = Table("adk_datetime_test", metadata, Column("created_at", DateTimeUTC(fsp=6)))

    ddl = str(CreateTable(table).compile(dialect=mysql.dialect()))

    assert "created_at DATETIME(6)" in ddl
    assert table.c.created_at.type.fsp == 6


def test_datetime_utc_rejects_invalid_fsp() -> None:
    from advanced_alchemy.types.datetime import DateTimeUTC

    for value in (-1, 7, "6"):
        with pytest.raises(ValueError, match="fsp must be an integer between 0 and 6"):
            DateTimeUTC(fsp=value)  # type: ignore[arg-type]
