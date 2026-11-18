from __future__ import annotations

import functools
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, literal_column, text, util
from sqlalchemy.dialects import oracle
from sqlalchemy.dialects.oracle import BLOB as ORA_BLOB
from sqlalchemy.dialects.postgresql import JSONB as PG_JSONB
from sqlalchemy.types import JSON as _JSON
from sqlalchemy.types import SchemaType, TypeDecorator, UserDefinedType

from advanced_alchemy.utils.serialization import decode_json, encode_json

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.engine import Dialect
    from sqlalchemy.sql.elements import ColumnElement
    from sqlalchemy.types import TypeEngine

__all__ = ("ORA_JSONB",)


_ORACLE_NATIVE_JSON_MIN_VERSION = 21
"""Oracle Database major version that introduced the native ``JSON`` data type."""


def _read_lob(value: Any) -> Any:
    # python-oracledb awaits the return value of async outconverters.
    return value.read()


class _OracleJSONStorage(UserDefinedType[Any]):
    """Use a BLOB for transport regardless of the Oracle column's storage type."""

    cache_ok = True

    def __init__(self, native: bool) -> None:
        self.native = native

    def get_col_spec(self, **kw: Any) -> str:
        return "JSON" if self.native else "BLOB"

    def get_dbapi_type(self, dbapi: Any) -> Any:
        return dbapi.BLOB

    def column_expression(self, colexpr: ColumnElement[Any]) -> ColumnElement[Any]:
        if self.native:
            # SQLAlchemy's JSON-to-VARCHAR fetch is capped at 32767 bytes.
            # Preserve the outer type so composed types still process the result.
            return func.json_serialize(colexpr.op("RETURNING")(literal_column("BLOB")), type_=colexpr.type)
        return colexpr

    def _cx_oracle_var(self, dialect: Dialect, cursor: Any, arraysize: int) -> Any:
        # SQLAlchemy also calls this hook for DML RETURNING output binds.
        return cursor.var(self.get_dbapi_type(dialect.dbapi), arraysize=arraysize, outconverter=_read_lob)

    def _cx_oracle_outputtypehandler(self, dialect: Dialect) -> Callable[..., Any]:
        blob_type = self.get_dbapi_type(dialect.dbapi)

        def handle(cursor: Any, _name: str, default_type: Any, *_metadata: Any) -> Any:
            if default_type is blob_type:
                return self._cx_oracle_var(dialect, cursor, cursor.arraysize)
            return None

        return handle


class ORA_JSONB(TypeDecorator[dict[str, Any]], SchemaType):  # noqa: N801
    """Oracle JSON with native storage when available and BLOB storage for compatibility."""

    impl = ORA_BLOB
    cache_ok = True

    @property
    def python_type(self) -> type[dict[str, Any]]:
        return dict

    def __init__(
        self,
        length: int | None = None,
        use_blob: bool = False,
        *,
        name: str | None = None,
        oracle_strict: bool = True,
    ) -> None:
        """Initialize JSON storage.

        Args:
            length: Length passed to the underlying SQLAlchemy BLOB type.
            use_blob: Store JSON in a BLOB even when native JSON is available.
            name: Optional schema type name.
            oracle_strict: Require strict JSON syntax for BLOB storage.
        """
        self.name = name
        self.oracle_strict = oracle_strict
        self.use_blob = use_blob
        super().__init__(length)

    def __repr__(self) -> str:
        return util.generic_repr(self, additional_kw=(("name", None), ("oracle_strict", True)))

    def coerce_compared_value(self, op: Any, value: Any) -> Any:
        return self.impl.coerce_compared_value(op=op, value=value)  # type: ignore[no-untyped-call, call-arg]

    def _uses_native_json(self, dialect: Dialect) -> bool:
        version = dialect.server_version_info
        return bool(
            not self.use_blob
            and hasattr(oracle, "JSON")
            and version
            and isinstance(version[0], int)
            and version[0] >= _ORACLE_NATIVE_JSON_MIN_VERSION
        )

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[Any]:
        if dialect.name == "oracle":
            return dialect.type_descriptor(_OracleJSONStorage(native=self._uses_native_json(dialect)))
        return dialect.type_descriptor(ORA_BLOB())

    def process_bind_param(self, value: Any, dialect: Dialect) -> bytes | None:
        if value is None:
            return None
        if value is _JSON.NULL:
            value = None
        serializer: Callable[[Any], str] | None = getattr(dialect, "_json_serializer", None)
        if serializer is None or serializer is encode_json:
            return encode_json(value, as_bytes=True)
        return serializer(value).encode("utf-8")

    def process_result_value(self, value: Any, dialect: Dialect) -> Any:
        if not isinstance(value, bytes):
            return value
        deserializer = getattr(dialect, "_json_deserializer", None)
        if deserializer is None or deserializer is decode_json:
            return decode_json(value)
        return deserializer(value.decode("utf-8"))

    def _should_create_constraint(self, compiler: Any, **kw: Any) -> bool:
        return compiler.dialect.name == "oracle" and not self._uses_native_json(compiler.dialect)

    def _variant_mapping_for_set_table(self, column: Any) -> dict[str, Any] | None:
        if column.type._variant_mapping:  # noqa: SLF001
            variant_mapping = dict(column.type._variant_mapping)  # noqa: SLF001
            variant_mapping["_default"] = column.type
        else:
            variant_mapping = None
        return variant_mapping

    @util.preload_module("sqlalchemy.sql.schema")
    def _set_table(self, column: Any, table: Any) -> None:
        schema = util.preloaded.sql_schema
        variant_mapping = self._variant_mapping_for_set_table(column)
        constraint_options = "(strict)" if self.oracle_strict else ""
        sqltext = text(f"{column.name} is json {constraint_options}")
        e = schema.CheckConstraint(
            sqltext,
            name=f"{column.name}_is_json",
            _create_rule=functools.partial(
                self._should_create_constraint,
                variant_mapping=variant_mapping,
            ),
            _type_bound=True,
        )
        table.append_constraint(e)


JsonB = (
    _JSON().with_variant(PG_JSONB, "postgresql").with_variant(ORA_JSONB, "oracle").with_variant(PG_JSONB, "cockroachdb")
)
"""A JSON type that uses  native ``JSONB`` where possible and ``Binary`` or ``Blob`` as
an alternative.
"""
