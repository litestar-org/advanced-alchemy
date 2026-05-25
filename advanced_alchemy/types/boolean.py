from typing import Any

from sqlalchemy.engine import Dialect
from sqlalchemy.types import Boolean, TypeDecorator, TypeEngine

__all__ = ("BooleanType",)


_ORACLE_NATIVE_BOOLEAN_MIN_VERSION = 23


class _OracleAwareBoolean(TypeDecorator[bool]):
    """Render native BOOLEAN on Oracle 23c+ when SA 2.1+ exposes it.

    Falls back to SA stock Boolean (SMALLINT on Oracle) on SA 2.0.x or
    Oracle servers older than 23c. Non-Oracle dialects always use stock
    Boolean - no behavior change.
    """

    impl = Boolean
    cache_ok = True

    @property
    def python_type(self) -> type[bool]:
        return bool

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[Any]:
        if dialect.name != "oracle":
            return dialect.type_descriptor(Boolean())
        try:
            from sqlalchemy.dialects.oracle import BOOLEAN as ORA_BOOLEAN
        except ImportError:
            return dialect.type_descriptor(Boolean())
        sv = dialect.server_version_info
        if sv and sv[0] >= _ORACLE_NATIVE_BOOLEAN_MIN_VERSION:
            return dialect.type_descriptor(ORA_BOOLEAN())
        return dialect.type_descriptor(Boolean())


BooleanType = _OracleAwareBoolean
