from __future__ import annotations

from base64 import b64decode
from importlib.util import find_spec
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy.dialects.mssql import UNIQUEIDENTIFIER as MSSQL_UNIQUEIDENTIFIER
from sqlalchemy.dialects.oracle import RAW as ORA_RAW
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.types import BINARY, CHAR, TypeDecorator

if UUID_UTILS_INSTALLED := find_spec("uuid_utils"):
    import uuid as core_uuid

    import uuid_utils as uuid
else:
    import uuid  # type: ignore[no-redef,unused-ignore]
    import uuid as core_uuid

if TYPE_CHECKING:
    from sqlalchemy.engine import Dialect


class GUID(TypeDecorator):
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
    def python_type(self) -> type[uuid.UUID | core_uuid.UUID]:
        return uuid.UUID

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
        value: bytes | str | uuid.UUID | core_uuid.UUID | None,
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
        value: bytes | str | uuid.UUID | core_uuid.UUID | None,
        dialect: Dialect,
    ) -> uuid.UUID | core_uuid.UUID | None:
        if value is None:
            return value
        if isinstance(value, (uuid.UUID, core_uuid.UUID)):
            return value
        if dialect.name == "spanner+spanner":
            return uuid.UUID(bytes=b64decode(value))
        if self.binary:
            return uuid.UUID(bytes=cast("bytes", value))
        return uuid.UUID(hex=cast("str", value))

    @staticmethod
    def to_uuid(value: Any) -> uuid.UUID | core_uuid.UUID | None:
        if isinstance(value, (uuid.UUID, core_uuid.UUID)) or value is None:
            return value
        try:
            value = uuid.UUID(hex=value)
        except (TypeError, ValueError):
            value = uuid.UUID(bytes=value)
        return cast("uuid.UUID | None", value)

    def compare_values(self, x: Any, y: Any) -> bool:
        """Compare two values for equality."""
        if isinstance(x, (uuid.UUID, core_uuid.UUID)) and isinstance(y, (uuid.UUID, core_uuid.UUID)):
            return x.bytes == y.bytes
        return cast("bool", x == y)
