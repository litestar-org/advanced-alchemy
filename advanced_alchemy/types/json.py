from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import text, util
from sqlalchemy.dialects.oracle import BLOB as ORA_BLOB
from sqlalchemy.dialects.postgresql import JSONB as PG_JSONB
from sqlalchemy.types import JSON as _JSON
from sqlalchemy.types import SchemaType, TypeDecorator, TypeEngine

from advanced_alchemy._serialization import decode_json, encode_json

if TYPE_CHECKING:
    from sqlalchemy.engine import Dialect


class ORA_JSONB(TypeDecorator, SchemaType):  # type: ignore[misc] # noqa: N801
    """Oracle Binary JSON type.

    JsonB = _JSON().with_variant(PG_JSONB, "postgresql").with_variant(ORA_JSONB, "oracle")

    """

    impl = ORA_BLOB
    cache_ok = True

    @property
    def python_type(self) -> type[dict[str, Any]]:
        return dict

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize JSON type"""
        self.name = kwargs.pop("name", None)
        self.oracle_strict = kwargs.pop("oracle_strict", True)

    def coerce_compared_value(self, op: Any, value: Any) -> Any:
        return self.impl.coerce_compared_value(op=op, value=value)  # type: ignore[no-untyped-call, call-arg]

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[Any]:
        return dialect.type_descriptor(ORA_BLOB())

    def process_bind_param(self, value: Any, dialect: Dialect) -> Any | None:
        return value if value is None else encode_json(value)

    def process_result_value(self, value: bytes | None, dialect: Dialect) -> Any | None:
        if dialect.oracledb_ver < (2,):  # type: ignore[attr-defined]
            return value if value is None else decode_json(value)
        return value

    def _should_create_constraint(self, compiler: Any, **kw: Any) -> bool:
        return cast("bool", compiler.dialect.name == "oracle")

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
            _create_rule=util.portable_instancemethod(  # type: ignore[no-untyped-call]
                self._should_create_constraint,
                {"variant_mapping": variant_mapping},
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
