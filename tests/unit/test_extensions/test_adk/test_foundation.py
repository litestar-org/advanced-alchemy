import importlib
import sys
from pathlib import Path

import pytest
from sqlalchemy import Column, MetaData, Table
from sqlalchemy.dialects import mysql
from sqlalchemy.schema import CreateTable

from tests.helpers import purge_module


@pytest.mark.skipif(sys.version_info < (3, 10), reason="google-adk v2 requires Python 3.10+")
def test_adk_extension_imports_on_supported_python() -> None:
    adk = importlib.import_module("advanced_alchemy.extensions.adk")

    assert adk.DEFAULT_MAX_KEY_LENGTH == 128
    assert adk.DEFAULT_MAX_VARCHAR_LENGTH == 256
    assert adk.MIN_GOOGLE_ADK_VERSION == "2.0.0"
    assert adk.ADKSessionModelMixin.__abstract__ is True
    assert issubclass(adk.StaleSessionError, ValueError)


def test_adk_extension_rejects_python_before_adk_supported_floor(monkeypatch: pytest.MonkeyPatch) -> None:
    purge_module(["advanced_alchemy.extensions.adk"], __file__)
    monkeypatch.setattr(sys, "version_info", (3, 9, 0, "final", 0))

    with pytest.raises(RuntimeError, match=r"requires Python 3\.10 or later"):
        importlib.import_module("advanced_alchemy.extensions.adk")

    purge_module(["advanced_alchemy.extensions.adk"], __file__)


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
