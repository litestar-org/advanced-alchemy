from __future__ import annotations

from base64 import b64decode
from importlib.util import find_spec
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

from sqlalchemy.dialects.mssql import UNIQUEIDENTIFIER as MSSQL_UNIQUEIDENTIFIER
from sqlalchemy.dialects.oracle import RAW as ORA_RAW
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.types import BINARY, CHAR, TypeDecorator
from typing_extensions import Buffer

if TYPE_CHECKING:
    from sqlalchemy.engine import Dialect

UUID_UTILS_INSTALLED = find_spec("uuid_utils")


class GUID(TypeDecorator[UUID]):
    """Platform-independent GUID type.

    Uses PostgreSQL's UUID type (Postgres, DuckDB, Cockroach),
    MSSQL's UNIQUEIDENTIFIER type, Oracle's RAW(16) type,
    otherwise uses BINARY(16) or CHAR(32),
    storing as stringified hex values.

    Will accept stringified UUIDs as a hexstring or an actual UUID

    """

    impl = BINARY(16)
    cache_ok = True

    @property
    def python_type(self) -> type[UUID]:
        return UUID

    def __init__(self, *args: Any, binary: bool = True, **kwargs: Any) -> None:
        self.binary = binary

    def load_dialect_impl(self, dialect: Dialect) -> Any:
        if dialect.name in {"postgresql", "duckdb", "cockroachdb"}:
            return dialect.type_descriptor(PG_UUID())
        if dialect.name == "oracle":
            return dialect.type_descriptor(ORA_RAW(16))
        if dialect.name == "mssql":
            return dialect.type_descriptor(MSSQL_UNIQUEIDENTIFIER())
        if self.binary:
            return dialect.type_descriptor(BINARY(16))
        return dialect.type_descriptor(CHAR(32))

    def process_bind_param(
        self,
        value: bytes | str | UUID | None,
        dialect: Dialect,
    ) -> bytes | str | None:
        if value is None:
            return value
        if dialect.name in {"postgresql", "duckdb", "cockroachdb", "mssql"}:
            return str(value)
        value = self.to_uuid(value)
        if value is None:
            return value
        if dialect.name in {"oracle", "spanner+spanner"}:
            return value.bytes
        return value.bytes if self.binary else value.hex

    def process_result_value(
        self,
        value: bytes | str | UUID | None,
        dialect: Dialect,
    ) -> UUID | None:
        if value is None:
            return value
        if value.__class__.__name__ == "UUID":
            return cast("UUID", value)
        if dialect.name == "spanner+spanner":
            return UUID(bytes=b64decode(cast("str | Buffer", value)))
        if self.binary:
            return UUID(bytes=cast("bytes", value))
        return UUID(hex=cast("str", value))

    @staticmethod
    def to_uuid(value: Any) -> UUID | None:
        if value.__class__.__name__ == "UUID" or value is None:
            return cast("UUID | None", value)
        try:
            value = UUID(hex=value)
        except (TypeError, ValueError):
            value = UUID(bytes=value)
        return cast("UUID | None", value)

    def compare_values(self, x: Any, y: Any) -> bool:
        """Compare two values for equality."""
        if x.__class__.__name__ == "UUID" and y.__class__.__name__ == "UUID":
            return cast("bool", x.bytes == y.bytes)
        return cast("bool", x == y)
