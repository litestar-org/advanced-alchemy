"""Round-trip the Oracle JSON types through sync and async connections."""

from __future__ import annotations

import platform
from typing import TYPE_CHECKING, cast
from unittest.mock import Mock
from uuid import uuid4

import pytest
from sqlalchemy import Column, Integer, MetaData, NullPool, Table, select
from sqlalchemy.dialects import oracle
from sqlalchemy.exc import IntegrityError
from sqlalchemy.schema import CreateTable

from advanced_alchemy.config import EngineConfig, SQLAlchemyAsyncConfig, SQLAlchemySyncConfig
from advanced_alchemy.types import ORA_JSONB, FileObject, JsonB, StoredObject, storages
from advanced_alchemy.types.file_object.backends.fsspec import FSSpecBackend
from advanced_alchemy.utils.serialization import decode_json, encode_json

if TYPE_CHECKING:
    from collections.abc import Iterator

    from sqlalchemy import Connection

pytestmark = [
    pytest.mark.skipif(platform.machine() != "x86_64", reason="oracle not available on this platform"),
    pytest.mark.integration,
]


@pytest.fixture(
    params=[
        pytest.param("oracle18c_url", id="oracle18c", marks=pytest.mark.xdist_group("oracle18")),
        pytest.param("oracle23ai_url", id="oracle26ai", marks=pytest.mark.xdist_group("oracle23")),
    ]
)
def oracle_json_url(request: pytest.FixtureRequest) -> str:
    return cast("str", request.getfixturevalue(request.param))


@pytest.fixture
def json_columns() -> Table:
    table_name = f"aa_json_{uuid4().hex[:8]}"
    return Table(
        table_name,
        MetaData(),
        Column("id", Integer, primary_key=True, autoincrement=False),
        Column("native_data", JsonB),
        Column("legacy_data", ORA_JSONB(use_blob=True)),
        Column("stored_file", StoredObject(backend="oracle_json_test")),
    )


@pytest.fixture
def stored_file() -> Iterator[FileObject]:
    backend = FSSpecBackend(key="oracle_json_test", fs="memory")
    storages.register_backend(backend)
    try:
        yield FileObject(backend=backend, filename="sample.txt", metadata={"count": 7})
    finally:
        storages.unregister_backend(backend.key)


def _assert_json_round_trip(
    connection: Connection, table: Table, stored_file: FileObject, serializer: Mock, deserializer: Mock
) -> None:
    server_version = connection.dialect.server_version_info
    assert server_version is not None
    modern_oracle = server_version >= (21,)
    supports_native_json = modern_oracle and hasattr(oracle, "JSON")
    ddl = str(CreateTable(table).compile(dialect=connection.dialect))
    assert f"native_data {'JSON' if supports_native_json else 'BLOB'}" in ddl
    assert "legacy_data BLOB" in ddl
    assert ("native_data_is_json" in ddl) is not supports_native_json
    assert "legacy_data_is_json" in ddl

    table.create(connection)
    try:
        document = {"string": "é" * (65_536 + 1), "numbers": [7, 1.25]}
        columns = (table.c.native_data, table.c.legacy_data, table.c.stored_file)
        row = connection.execute(
            table.insert()
            .values(id=1, native_data=document, legacy_data=document, stored_file=stored_file)
            .returning(*columns)
        ).one()
        assert row.native_data == row.legacy_data == document
        assert row.stored_file.to_dict() == stored_file.to_dict()
        if hasattr(oracle, "JSON"):
            assert serializer.call_count == deserializer.call_count == 3

        row = connection.execute(select(*columns).where(table.c.id == 1)).one()
        assert row.native_data == row.legacy_data == document
        assert type(row.native_data["numbers"][0]) is int
        assert type(row.native_data["numbers"][1]) is float
        assert row.stored_file.to_dict() == stored_file.to_dict()
        if hasattr(oracle, "JSON"):
            assert serializer.call_count == 3
            assert deserializer.call_count == 6

        value = ["string", 7, 1.25]
        row = connection.execute(
            table.update().where(table.c.id == 1).values(native_data=value).returning(table.c.native_data)
        ).scalar_one()
        assert row == value
        if modern_oracle:
            for scalar in ('{"looks":"like JSON"}', "123", 7, 1.25, True):
                connection.execute(table.update().where(table.c.id == 1).values(native_data=scalar))
                result = connection.scalar(select(table.c.native_data).where(table.c.id == 1))
                assert result == scalar
                assert type(result) is type(scalar)
        else:
            with pytest.raises(IntegrityError):
                connection.execute(table.update().where(table.c.id == 1).values(native_data="scalar"))

        assert (
            connection.execute(
                table.update().where(table.c.id == 1).values(native_data=None).returning(table.c.native_data)
            ).scalar_one()
            is None
        )
        assert connection.scalar(select(table.c.id).where(table.c.native_data.is_(None))) == 1
    finally:
        table.drop(connection)


@pytest.mark.oracledb_sync
def test_oracle_json_sync(oracle_json_url: str, json_columns: Table, stored_file: FileObject) -> None:
    serializer, deserializer = Mock(wraps=encode_json), Mock(wraps=decode_json)
    config = SQLAlchemySyncConfig(
        connection_string=oracle_json_url,
        engine_config=EngineConfig(poolclass=NullPool, json_serializer=serializer, json_deserializer=deserializer),
    )
    engine = config.get_engine()
    try:
        with engine.begin() as connection:
            _assert_json_round_trip(connection, json_columns, stored_file, serializer, deserializer)
    finally:
        engine.dispose()


@pytest.mark.oracledb_async
@pytest.mark.asyncio
async def test_oracle_json_async(oracle_json_url: str, json_columns: Table, stored_file: FileObject) -> None:
    serializer, deserializer = Mock(wraps=encode_json), Mock(wraps=decode_json)
    config = SQLAlchemyAsyncConfig(
        connection_string=oracle_json_url,
        engine_config=EngineConfig(poolclass=NullPool, json_serializer=serializer, json_deserializer=deserializer),
    )
    engine = config.get_engine()
    try:
        async with engine.begin() as connection:
            await connection.run_sync(_assert_json_round_trip, json_columns, stored_file, serializer, deserializer)
    finally:
        await engine.dispose()
