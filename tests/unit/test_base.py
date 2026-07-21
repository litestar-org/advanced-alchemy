# pyright: reportUnusedImport=false
from __future__ import annotations

import importlib
import sys
import types
import uuid as uuid_module
import warnings
from typing import cast

import pytest
from sqlalchemy import Table, create_engine
from sqlalchemy.dialects import mssql, oracle, postgresql
from sqlalchemy.orm import declarative_mixin
from sqlalchemy.schema import CreateTable

from tests.helpers import purge_module

_MISSING = object()


def _reload_uuid_mixin(
    monkeypatch: pytest.MonkeyPatch,
    *,
    uuid_utils_installed: bool,
    fake_uuid_utils_compat: types.ModuleType | None = None,
    version_info: tuple[int, int, int, str, int] = (3, 14, 0, "final", 0),
) -> types.ModuleType:
    import advanced_alchemy.types as alchemy_types

    module_names = ("advanced_alchemy.mixins.uuid", "uuid_utils.compat", "uuid_utils")
    previous_modules = {name: sys.modules.get(name, _MISSING) for name in module_names}
    mixins_package = sys.modules.get("advanced_alchemy.mixins")
    previous_uuid_attr = getattr(mixins_package, "uuid", _MISSING) if mixins_package is not None else _MISSING

    monkeypatch.setattr(sys, "version_info", version_info)
    monkeypatch.setattr(alchemy_types, "UUID_UTILS_INSTALLED", object() if uuid_utils_installed else None)

    try:
        for name in module_names:
            sys.modules.pop(name, None)
        if mixins_package is not None and hasattr(mixins_package, "uuid"):
            delattr(mixins_package, "uuid")
        if fake_uuid_utils_compat is not None:
            fake_uuid_utils = types.ModuleType("uuid_utils")
            fake_uuid_utils.__path__ = []  # type: ignore[attr-defined]
            sys.modules["uuid_utils"] = fake_uuid_utils
            sys.modules["uuid_utils.compat"] = fake_uuid_utils_compat
        return importlib.import_module("advanced_alchemy.mixins.uuid")
    finally:
        for name, previous_module in previous_modules.items():
            if previous_module is _MISSING:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = cast(types.ModuleType, previous_module)
        if mixins_package is not None:
            if previous_uuid_attr is _MISSING:
                if hasattr(mixins_package, "uuid"):
                    delattr(mixins_package, "uuid")
            else:
                setattr(mixins_package, "uuid", previous_uuid_attr)


def test_deprecated_classes_functionality() -> None:
    """Test that mixins classes maintain have base functionality."""
    purge_module(["advanced_alchemy.base", "advanced_alchemy.mixins"], __file__)

    warnings.filterwarnings("ignore", category=DeprecationWarning)
    from sqlalchemy import exc as sa_exc

    warnings.filterwarnings("ignore", category=sa_exc.SAWarning)

    # Test instantiation and basic attributes
    from advanced_alchemy.mixins import (
        AuditColumns,
        NanoIDPrimaryKey,
        UUIDPrimaryKey,
        UUIDv6PrimaryKey,
        UUIDv7PrimaryKey,
    )

    uuidv7_pk = UUIDv7PrimaryKey()
    uuidv6_pk = UUIDv6PrimaryKey()
    uuid_pk = UUIDPrimaryKey()
    nanoid_pk = NanoIDPrimaryKey()
    audit = AuditColumns()

    # Verify the classes have the expected attributes
    assert hasattr(uuidv7_pk, "id")
    assert hasattr(uuidv7_pk, "_sentinel")
    assert hasattr(uuidv6_pk, "id")
    assert hasattr(uuidv6_pk, "_sentinel")
    assert hasattr(uuid_pk, "id")
    assert hasattr(uuid_pk, "_sentinel")
    assert hasattr(nanoid_pk, "id")
    assert hasattr(nanoid_pk, "_sentinel")
    assert hasattr(audit, "created_at")
    assert hasattr(audit, "updated_at")


def test_uuid_utils_generators_are_preferred_when_installed_on_python_314(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that installing uuid-utils keeps uuid generation on uuid-utils."""

    def native_uuid6() -> uuid_module.UUID:
        return uuid_module.uuid4()

    def native_uuid7() -> uuid_module.UUID:
        return uuid_module.uuid4()

    def uuid_utils_uuid4() -> uuid_module.UUID:
        return uuid_module.uuid4()

    def uuid_utils_uuid6() -> uuid_module.UUID:
        return uuid_module.uuid4()

    def uuid_utils_uuid7() -> uuid_module.UUID:
        return uuid_module.uuid4()

    monkeypatch.setattr(uuid_module, "uuid6", native_uuid6, raising=False)
    monkeypatch.setattr(uuid_module, "uuid7", native_uuid7, raising=False)

    fake_compat = types.ModuleType("uuid_utils.compat")
    fake_compat.uuid4 = uuid_utils_uuid4  # type: ignore[attr-defined]
    fake_compat.uuid6 = uuid_utils_uuid6  # type: ignore[attr-defined]
    fake_compat.uuid7 = uuid_utils_uuid7  # type: ignore[attr-defined]

    uuid_mixin = _reload_uuid_mixin(
        monkeypatch,
        uuid_utils_installed=True,
        fake_uuid_utils_compat=fake_compat,
    )

    assert uuid_mixin.uuid4 is uuid_utils_uuid4
    assert uuid_mixin.uuid6 is uuid_utils_uuid6
    assert uuid_mixin.uuid7 is uuid_utils_uuid7


def test_native_uuid_generators_are_used_on_python_314_without_uuid_utils(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that Python 3.14 native UUID generators are used without uuid-utils."""

    def native_uuid6() -> uuid_module.UUID:
        return uuid_module.uuid4()

    def native_uuid7() -> uuid_module.UUID:
        return uuid_module.uuid4()

    monkeypatch.setattr(uuid_module, "uuid6", native_uuid6, raising=False)
    monkeypatch.setattr(uuid_module, "uuid7", native_uuid7, raising=False)

    uuid_mixin = _reload_uuid_mixin(monkeypatch, uuid_utils_installed=False)

    assert uuid_mixin.uuid6 is native_uuid6
    assert uuid_mixin.uuid7 is native_uuid7


def test_uuid_generators_fall_back_to_uuid4_before_python_314_without_uuid_utils(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that UUID6/7 generators fall back to UUID4 before Python 3.14."""

    uuid_mixin = _reload_uuid_mixin(
        monkeypatch,
        uuid_utils_installed=False,
        version_info=(3, 13, 0, "final", 0),
    )

    assert uuid_mixin.uuid6 is uuid_mixin.uuid4
    assert uuid_mixin.uuid7 is uuid_mixin.uuid4


def test_identity_primary_key_generates_identity_ddl() -> None:
    """Test that IdentityPrimaryKey generates proper IDENTITY DDL for PostgreSQL."""
    from advanced_alchemy.base import BigIntBase
    from advanced_alchemy.mixins.bigint import IdentityPrimaryKey

    @declarative_mixin
    class TestMixin(IdentityPrimaryKey):
        pass

    class IdentityPrimaryKeyModel(TestMixin, BigIntBase):
        __tablename__ = "test_identity"

    # Get the CREATE TABLE statement
    create_stmt = CreateTable(cast(Table, IdentityPrimaryKeyModel.__table__))

    # Test with PostgreSQL dialect
    pg_ddl = str(create_stmt.compile(dialect=postgresql.dialect()))  # type: ignore[no-untyped-call,unused-ignore]

    # Should contain GENERATED BY DEFAULT AS IDENTITY
    assert "GENERATED BY DEFAULT AS IDENTITY" in pg_ddl
    assert "BIGSERIAL" not in pg_ddl.upper()
    assert "START WITH 1" in pg_ddl
    assert "INCREMENT BY 1" in pg_ddl


def test_identity_audit_base_generates_identity_ddl() -> None:
    """Test that IdentityAuditBase generates proper IDENTITY DDL for PostgreSQL."""
    from advanced_alchemy.base import IdentityAuditBase

    class IdentityAuditBaseModel(IdentityAuditBase):
        __tablename__ = "test_identity_audit"

    # Get the CREATE TABLE statement
    create_stmt = CreateTable(cast(Table, IdentityAuditBaseModel.__table__))

    # Test with PostgreSQL dialect
    pg_ddl = str(create_stmt.compile(dialect=postgresql.dialect()))  # type: ignore[no-untyped-call,unused-ignore]

    # Should contain GENERATED BY DEFAULT AS IDENTITY
    assert "GENERATED BY DEFAULT AS IDENTITY" in pg_ddl
    assert "BIGSERIAL" not in pg_ddl.upper()


def test_bigint_primary_key_still_uses_sequence() -> None:
    """Test that BigIntPrimaryKey still uses sequences as before."""
    from advanced_alchemy.base import BigIntBase
    from advanced_alchemy.mixins.bigint import BigIntPrimaryKey

    @declarative_mixin
    class TestMixin(BigIntPrimaryKey):
        pass

    class BigIntPrimaryKeyModel(TestMixin, BigIntBase):
        __tablename__ = "test_bigint"

    # Get the CREATE TABLE statement
    create_stmt = CreateTable(cast(Table, BigIntPrimaryKeyModel.__table__))

    # Test with PostgreSQL dialect
    pg_ddl = str(create_stmt.compile(dialect=postgresql.dialect()))  # type: ignore[no-untyped-call,unused-ignore]

    # BigIntPrimaryKey should use a Sequence (not IDENTITY)
    assert "GENERATED" not in pg_ddl
    assert "IDENTITY" not in pg_ddl.upper()
    # The sequence is defined on the column but rendered separately
    assert BigIntPrimaryKeyModel.__table__.c.id.default is not None
    assert BigIntPrimaryKeyModel.__table__.c.id.default.name == "test_bigint_id_seq"


def test_identity_ddl_for_oracle() -> None:
    """Test Identity DDL generation for Oracle."""
    from advanced_alchemy.base import IdentityAuditBase

    class OracleIdentityAuditBaseModel(IdentityAuditBase):
        __tablename__ = "test_oracle"

    create_stmt = CreateTable(cast(Table, OracleIdentityAuditBaseModel.__table__))
    oracle_ddl = str(create_stmt.compile(dialect=oracle.dialect()))  # type: ignore[no-untyped-call,unused-ignore]

    # Oracle should generate IDENTITY
    assert "GENERATED BY DEFAULT AS IDENTITY" in oracle_ddl


def test_identity_ddl_for_mssql() -> None:
    """Test Identity DDL generation for SQL Server."""
    from advanced_alchemy.base import IdentityAuditBase

    class MSSQLIdentityAuditBaseModel(IdentityAuditBase):
        __tablename__ = "test_mssql"

    create_stmt = CreateTable(cast(Table, MSSQLIdentityAuditBaseModel.__table__))
    mssql_ddl = str(create_stmt.compile(dialect=mssql.dialect()))  # type: ignore[no-untyped-call,unused-ignore]

    # SQL Server should generate IDENTITY
    assert "IDENTITY(1,1)" in mssql_ddl


def test_identity_works_with_sqlite() -> None:
    """Test that Identity columns work with SQLite (fallback to autoincrement)."""
    from advanced_alchemy.base import IdentityAuditBase

    class SQLiteIdentityAuditBaseModel(IdentityAuditBase):
        __tablename__ = "test_sqlite"

    # Create an in-memory SQLite engine
    engine = create_engine("sqlite:///:memory:")
    cast(Table, SQLiteIdentityAuditBaseModel.__table__).create(engine)

    # Should not raise any errors
    assert True  # If we get here, it worked


def test_registry_type_annotation_map_has_no_protocol_keys() -> None:
    """Regression test for https://github.com/litestar-org/advanced-alchemy/issues/477.

    ``type_annotation_map`` is resolved by SQLAlchemy through an exact/``__mro__``
    dictionary lookup that rejects supertype matches. A ``Protocol`` (such as the
    now-removed ``DataclassProtocol`` entry) is never present in the ``__mro__`` of
    a class that structurally satisfies it, so a Protocol key can never match and
    is misleading dead configuration. Guard against reintroducing one.
    """
    from advanced_alchemy.base import orm_registry

    protocol_keys = [key for key in orm_registry.type_annotation_map if getattr(key, "_is_protocol", False)]
    assert protocol_keys == []


def test_dataclass_column_resolves_via_custom_annotation_map() -> None:
    """A concrete dataclass resolves only when registered explicitly.

    This is the supported replacement for the removed ``DataclassProtocol`` entry:
    users map their own concrete dataclass type, which lands in the registry as an
    exact key and therefore resolves.
    """
    from dataclasses import dataclass

    from advanced_alchemy.base import create_registry
    from advanced_alchemy.types import JsonB

    @dataclass
    class ExtraData:
        before: int

    registry = create_registry(custom_annotation_map={ExtraData: JsonB})

    resolved = registry._resolve_type(ExtraData)  # pyright: ignore[reportPrivateUsage]
    assert resolved is not None
