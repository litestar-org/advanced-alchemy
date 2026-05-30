"""Unit tests for the configurable serialization module."""

from __future__ import annotations

import datetime
import importlib
import json
import threading
import time
from decimal import Decimal
from enum import Enum
from ipaddress import IPv4Address, IPv4Interface, IPv4Network, IPv6Address, IPv6Interface, IPv6Network
from pathlib import Path, PurePath
from typing import Any
from uuid import UUID

import pytest

from advanced_alchemy.typing import (
    ATTRS_INSTALLED,
    MSGSPEC_INSTALLED,
    NUMPY_INSTALLED,
    ORJSON_INSTALLED,
    PYDANTIC_INSTALLED,
)
from advanced_alchemy.utils import serialization
from advanced_alchemy.utils.dataclass import Empty
from advanced_alchemy.utils.serialization import (
    DEFAULT_TYPE_ENCODERS,
    JSONSerializer,
    MsgspecSerializer,
    OrjsonSerializer,
    SchemaDumpConfig,
    StandardLibSerializer,
    TypeEncodersMap,
    convert_date_to_iso,
    convert_datetime_to_gmt_iso,
    decode_complex_type,
    decode_json,
    encode_complex_type,
    encode_json,
    get_serializer,
    schema_dump,
)


class MyEnum(Enum):
    """Test enum."""

    VALUE_A = "a"
    VALUE_B = "b"


class CustomType:
    """Custom type for testing type encoders."""

    def __init__(self, value: str) -> None:
        self.value = value


class ChildCustomType(CustomType):
    """Child class to test MRO lookup."""


# ----------------------------------------------------------------------
# Helper functions
# ----------------------------------------------------------------------


def test_convert_datetime_to_gmt_iso_naive() -> None:
    dt = datetime.datetime(2025, 12, 17, 10, 30, 0)
    assert convert_datetime_to_gmt_iso(dt) == "2025-12-17T10:30:00Z"


def test_convert_datetime_to_gmt_iso_aware() -> None:
    dt = datetime.datetime(2025, 12, 17, 10, 30, 0, tzinfo=datetime.timezone.utc)
    assert convert_datetime_to_gmt_iso(dt) == "2025-12-17T10:30:00Z"


def test_convert_date_to_iso() -> None:
    assert convert_date_to_iso(datetime.date(2025, 12, 17)) == "2025-12-17"


# ----------------------------------------------------------------------
# Default type encoders
# ----------------------------------------------------------------------


def test_default_datetime_encoder() -> None:
    encoder = DEFAULT_TYPE_ENCODERS[datetime.datetime]
    assert encoder(datetime.datetime(2025, 12, 17, 10, 30, 0)) == "2025-12-17T10:30:00Z"


def test_default_date_encoder() -> None:
    encoder = DEFAULT_TYPE_ENCODERS[datetime.date]
    assert encoder(datetime.date(2025, 12, 17)) == "2025-12-17"


def test_default_time_encoder() -> None:
    encoder = DEFAULT_TYPE_ENCODERS[datetime.time]
    assert encoder(datetime.time(10, 30, 0)) == "10:30:00"


def test_default_timedelta_encoder() -> None:
    encoder = DEFAULT_TYPE_ENCODERS[datetime.timedelta]
    assert encoder(datetime.timedelta(hours=1, minutes=30)) == 5400.0


def test_default_decimal_encoder() -> None:
    encoder = DEFAULT_TYPE_ENCODERS[Decimal]
    assert encoder(Decimal("123.456")) == "123.456"


def test_default_uuid_encoder() -> None:
    u = UUID("12345678-1234-5678-1234-567812345678")
    encoder = DEFAULT_TYPE_ENCODERS[UUID]
    assert encoder(u) == "12345678-1234-5678-1234-567812345678"


def test_default_path_encoder() -> None:
    encoder = DEFAULT_TYPE_ENCODERS[Path]
    assert encoder(Path("/tmp/test.txt")) == "/tmp/test.txt"


def test_default_pure_path_encoder() -> None:
    encoder = DEFAULT_TYPE_ENCODERS[PurePath]
    assert encoder(PurePath("/tmp/test.txt")) == "/tmp/test.txt"


def test_default_enum_encoder() -> None:
    encoder = DEFAULT_TYPE_ENCODERS[Enum]
    assert encoder(MyEnum.VALUE_A) == "a"
    assert encoder(MyEnum.VALUE_B) == "b"


def test_default_bytes_encoder() -> None:
    encoder = DEFAULT_TYPE_ENCODERS[bytes]
    assert encoder(b"hello") == "hello"


def test_default_set_and_frozenset_encoders() -> None:
    assert DEFAULT_TYPE_ENCODERS[set]({1, 2, 3}) == [1, 2, 3]
    assert DEFAULT_TYPE_ENCODERS[frozenset](frozenset({"a"})) == ["a"]


@pytest.mark.skipif(not PYDANTIC_INSTALLED, reason="Pydantic not installed")
def test_schema_dump_config_pydantic_exclude_unset_false_includes_defaults() -> None:
    """SchemaDumpConfig should pass exclude_unset through to Pydantic model_dump."""
    from pydantic import BaseModel

    class UpdateSchema(BaseModel):
        name: str
        is_admin: bool = False

    result = schema_dump(UpdateSchema(name="Ada"), config=SchemaDumpConfig(exclude_unset=False))

    assert result == {"name": "Ada", "is_admin": False}


@pytest.mark.skipif(not PYDANTIC_INSTALLED, reason="Pydantic not installed")
def test_schema_dump_config_pydantic_missing_sentinel_is_excluded_by_default() -> None:
    """Pydantic MISSING remains sentinel-like under the default dump policy."""
    from pydantic import BaseModel

    missing_module = pytest.importorskip("pydantic.experimental.missing_sentinel")

    class UpdateSchema(BaseModel):
        name: str = "Ada"
        marker: Any = missing_module.MISSING

    result = schema_dump(UpdateSchema(), config=SchemaDumpConfig(exclude_unset=False))

    assert result == {"name": "Ada"}


def test_pydantic_missing_sentinel_is_unavailable_when_pydantic_support_is_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pydantic MISSING lookup should be skipped when Pydantic support is unavailable."""
    monkeypatch.setattr("advanced_alchemy.utils.serialization.PYDANTIC_INSTALLED", False)

    assert serialization._get_pydantic_missing_sentinel() is None


@pytest.mark.skipif(not MSGSPEC_INSTALLED, reason="msgspec not installed")
def test_schema_dump_config_msgspec_exclude_sentinels() -> None:
    """SchemaDumpConfig should control msgspec UNSET sentinel filtering."""
    import msgspec

    class UpdateStruct(msgspec.Struct):
        name: Any = msgspec.UNSET
        is_admin: bool = False
        notes: Any = None

    data = UpdateStruct()

    assert schema_dump(data) == {"is_admin": False, "notes": None}
    assert schema_dump(data, config=SchemaDumpConfig(exclude_sentinels=False)) == {
        "name": msgspec.UNSET,
        "is_admin": False,
        "notes": None,
    }
    assert schema_dump(data, config=SchemaDumpConfig(exclude_defaults=True, exclude_sentinels=False)) == {}
    assert schema_dump(data, config=SchemaDumpConfig(exclude_none=True)) == {"is_admin": False}


def test_msgspec_struct_dump_skips_declared_fields_without_values() -> None:
    """msgspec-style declared fields without values should be skipped."""

    class UpdateStruct:
        __struct_fields__ = ("name",)
        __struct_defaults__ = ()

    data: Any = UpdateStruct()

    assert serialization._dump_msgspec_struct(data, SchemaDumpConfig()) == {}


@pytest.mark.skipif(not MSGSPEC_INSTALLED, reason="msgspec not installed")
def test_schema_dump_exclude_unset_false_includes_msgspec_unset() -> None:
    """exclude_unset=False should include msgspec UNSET values for existing callers."""
    import msgspec

    class UpdateStruct(msgspec.Struct):
        name: Any = msgspec.UNSET

    assert schema_dump(UpdateStruct(), exclude_unset=False) == {"name": msgspec.UNSET}


@pytest.mark.skipif(not PYDANTIC_INSTALLED, reason="Pydantic not installed")
def test_schema_dump_config_exclude_unset_false_filters_pydantic_missing_by_default() -> None:
    """SchemaDumpConfig(exclude_unset=False) should filter sentinels by default."""
    from pydantic import BaseModel

    missing_module = pytest.importorskip("pydantic.experimental.missing_sentinel")

    class UpdateSchema(BaseModel):
        marker: Any = missing_module.MISSING

    assert schema_dump(UpdateSchema(), config=SchemaDumpConfig(exclude_unset=False)) == {}


@pytest.mark.skipif(not PYDANTIC_INSTALLED, reason="Pydantic not installed")
def test_schema_dump_config_pydantic_can_include_missing_sentinel() -> None:
    """SchemaDumpConfig should be able to include Pydantic MISSING when requested."""
    from pydantic import BaseModel

    missing_module = pytest.importorskip("pydantic.experimental.missing_sentinel")

    class UpdateSchema(BaseModel):
        name: str = "Ada"
        marker: Any = missing_module.MISSING

    assert schema_dump(
        UpdateSchema(),
        config=SchemaDumpConfig(exclude_unset=False, exclude_sentinels=False),
    ) == {"name": "Ada", "marker": missing_module.MISSING}


def test_schema_dump_config_dataclass_exclude_sentinels() -> None:
    """SchemaDumpConfig should apply Advanced Alchemy Empty filtering to dataclasses."""
    from dataclasses import dataclass

    @dataclass
    class UpdateDataclass:
        name: str
        is_admin: bool = False
        notes: Any = None
        marker: Any = Empty

    data = UpdateDataclass(name="Ada")

    assert schema_dump(data) == {"name": "Ada", "is_admin": False, "notes": None}
    assert schema_dump(data, config=SchemaDumpConfig(exclude_sentinels=False)) == {
        "name": "Ada",
        "is_admin": False,
        "notes": None,
        "marker": Empty,
    }
    assert schema_dump(data, config=SchemaDumpConfig(exclude_defaults=True, exclude_sentinels=False)) == {"name": "Ada"}
    assert schema_dump(data, config=SchemaDumpConfig(exclude_none=True)) == {"name": "Ada", "is_admin": False}


def test_schema_dump_config_dataclass_nested_instances() -> None:
    """Nested dataclass instances should be dumped recursively."""
    from dataclasses import dataclass

    @dataclass
    class ChildDataclass:
        name: str

    @dataclass
    class ParentDataclass:
        child: ChildDataclass
        is_admin: bool = False

    assert schema_dump(ParentDataclass(child=ChildDataclass(name="Ada"))) == {
        "child": {"name": "Ada"},
        "is_admin": False,
    }


@pytest.mark.skipif(not ATTRS_INSTALLED, reason="attrs not installed")
def test_schema_dump_config_attrs_exclude_defaults_and_none() -> None:
    """SchemaDumpConfig should apply default and None filtering to attrs instances."""
    from attrs import define

    @define
    class UpdateAttrs:
        name: str
        is_admin: bool = False
        notes: Any = None

    data = UpdateAttrs(name="Ada")

    assert schema_dump(data, config=SchemaDumpConfig(exclude_defaults=True)) == {"name": "Ada"}
    assert schema_dump(data, config=SchemaDumpConfig(exclude_none=True)) == {"name": "Ada", "is_admin": False}


@pytest.mark.skipif(not ATTRS_INSTALLED, reason="attrs not installed")
def test_schema_dump_config_attrs_exclude_sentinels() -> None:
    """SchemaDumpConfig should filter attrs NOTHING sentinel values."""
    from attrs import NOTHING, define

    @define
    class UpdateAttrs:
        name: str
        marker: Any

    data = UpdateAttrs(name="Ada", marker=NOTHING)

    assert schema_dump(data) == {"name": "Ada"}
    assert schema_dump(data, config=SchemaDumpConfig(exclude_sentinels=False, exclude_none=True)) == {
        "name": "Ada",
        "marker": NOTHING,
    }


@pytest.mark.skipif(
    not ATTRS_INSTALLED or not serialization.CATTRS_INSTALLED,
    reason="attrs and cattrs are not installed",
)
def test_schema_dump_config_attrs_without_filtering_uses_cattrs() -> None:
    """attrs instances without active filters should use cattrs when it is available."""
    from attrs import define

    @define
    class UpdateAttrs:
        name: str
        is_admin: bool = False

    assert schema_dump(
        UpdateAttrs(name="Ada"),
        config=SchemaDumpConfig(exclude_sentinels=False),
    ) == {"name": "Ada", "is_admin": False}


@pytest.mark.skipif(not ATTRS_INSTALLED, reason="attrs not installed")
def test_schema_dump_config_attrs_without_cattrs_uses_attrs_asdict(monkeypatch: pytest.MonkeyPatch) -> None:
    """attrs instances should still dump when cattrs is unavailable."""
    from attrs import define

    @define
    class UpdateAttrs:
        name: str
        is_admin: bool = False

    monkeypatch.setattr("advanced_alchemy.utils.serialization.CATTRS_INSTALLED", False)

    assert schema_dump(
        UpdateAttrs(name="Ada"),
        config=SchemaDumpConfig(exclude_sentinels=False),
    ) == {"name": "Ada", "is_admin": False}


def test_schema_dump_skips_pydantic_branch_when_pydantic_not_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    """schema_dump should not rely on Pydantic APIs when Pydantic is unavailable."""

    class PydanticLike:
        def __init__(self) -> None:
            self.name = "Ada"

        def model_dump(self, **kwargs: Any) -> dict[str, Any]:
            msg = "model_dump should not be called when Pydantic is unavailable"
            raise AssertionError(msg)

    monkeypatch.setattr("advanced_alchemy.utils.serialization.PYDANTIC_INSTALLED", False)

    assert schema_dump(PydanticLike()) == {"name": "Ada"}


def test_schema_dump_skips_msgspec_branch_when_msgspec_not_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    """schema_dump should not rely on msgspec APIs when msgspec is unavailable."""

    class MsgspecLike:
        __struct_fields__ = ("name",)

        def __init__(self) -> None:
            self.name = "Ada"

    monkeypatch.setattr("advanced_alchemy.utils.serialization.MSGSPEC_INSTALLED", False)

    assert schema_dump(MsgspecLike()) == {"name": "Ada"}


def test_schema_dump_skips_attrs_branch_when_attrs_not_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    """schema_dump should not rely on attrs APIs when attrs is unavailable."""

    class AttrsLike:
        __attrs_attrs__ = ()

        def __init__(self) -> None:
            self.name = "Ada"

    monkeypatch.setattr("advanced_alchemy.utils.serialization.ATTRS_INSTALLED", False)

    assert schema_dump(AttrsLike()) == {"name": "Ada"}


@pytest.mark.parametrize(
    ("kind", "value", "expected"),
    [
        (IPv4Address, "192.168.1.1", "192.168.1.1"),
        (IPv4Interface, "192.168.1.1/24", "192.168.1.1/24"),
        (IPv4Network, "192.168.1.0/24", "192.168.1.0/24"),
        (IPv6Address, "::1", "::1"),
        (IPv6Interface, "::1/128", "::1/128"),
        (IPv6Network, "::/0", "::/0"),
    ],
)
def test_default_ip_address_encoders(kind: type, value: str, expected: str) -> None:
    encoder = DEFAULT_TYPE_ENCODERS[kind]
    assert encoder(kind(value)) == expected


# ----------------------------------------------------------------------
# Msgspec serializer
# ----------------------------------------------------------------------


@pytest.mark.skipif(not MSGSPEC_INSTALLED, reason="msgspec not installed")
def test_msgspec_encode_simple_dict() -> None:
    result = MsgspecSerializer().encode({"key": "value", "number": 42})
    assert result == '{"key":"value","number":42}'


@pytest.mark.skipif(not MSGSPEC_INSTALLED, reason="msgspec not installed")
def test_msgspec_encode_as_bytes() -> None:
    result = MsgspecSerializer().encode({"key": "value"}, as_bytes=True)
    assert isinstance(result, bytes)
    assert result == b'{"key":"value"}'


@pytest.mark.skipif(not MSGSPEC_INSTALLED, reason="msgspec not installed")
def test_msgspec_decode_string() -> None:
    assert MsgspecSerializer().decode('{"key":"value","number":42}') == {"key": "value", "number": 42}


@pytest.mark.skipif(not MSGSPEC_INSTALLED, reason="msgspec not installed")
def test_msgspec_decode_bytes() -> None:
    assert MsgspecSerializer().decode(b'{"key":"value"}') == {"key": "value"}


@pytest.mark.skipif(not MSGSPEC_INSTALLED, reason="msgspec not installed")
def test_msgspec_decode_bytes_passthrough() -> None:
    data = b'{"key":"value"}'
    assert MsgspecSerializer().decode(data, decode_bytes=False) == data


@pytest.mark.skipif(not MSGSPEC_INSTALLED, reason="msgspec not installed")
def test_msgspec_custom_type_encoders() -> None:
    custom_encoders: TypeEncodersMap = {CustomType: lambda x: {"custom_value": x.value}}
    serializer = MsgspecSerializer(type_encoders=custom_encoders)
    assert serializer.encode({"obj": CustomType("test")}) == '{"obj":{"custom_value":"test"}}'


@pytest.mark.skipif(not MSGSPEC_INSTALLED, reason="msgspec not installed")
def test_msgspec_custom_enc_hook() -> None:
    def my_hook(obj: Any) -> Any:
        if isinstance(obj, CustomType):
            return f"custom:{obj.value}"
        raise TypeError

    serializer = MsgspecSerializer(enc_hook=my_hook)
    assert serializer.encode({"obj": CustomType("test")}) == '{"obj":"custom:test"}'


@pytest.mark.skipif(not MSGSPEC_INSTALLED, reason="msgspec not installed")
def test_msgspec_mro_lookup() -> None:
    custom_encoders: TypeEncodersMap = {CustomType: lambda x: f"parent:{x.value}"}
    serializer = MsgspecSerializer(type_encoders=custom_encoders)
    assert serializer.encode({"obj": ChildCustomType("child")}) == '{"obj":"parent:child"}'


@pytest.mark.skipif(not MSGSPEC_INSTALLED, reason="msgspec not installed")
def test_msgspec_custom_type_encoders_override_native_values() -> None:
    serializer = MsgspecSerializer(
        type_encoders={
            Decimal: lambda _: "custom-decimal",
            UUID: lambda _: "custom-uuid",
            bytes: lambda _: "custom-bytes",
            datetime.datetime: lambda _: "custom-datetime",
        }
    )

    result = json.loads(
        serializer.encode(
            {
                "decimal": Decimal("1.2"),
                "uuid": UUID("12345678-1234-5678-1234-567812345678"),
                "bytes": b"abc",
                "datetime": datetime.datetime(2026, 1, 2, 3, 4, 5, tzinfo=datetime.timezone.utc),
            }
        )
    )

    assert result == {
        "decimal": "custom-decimal",
        "uuid": "custom-uuid",
        "bytes": "custom-bytes",
        "datetime": "custom-datetime",
    }


# ----------------------------------------------------------------------
# Orjson serializer
# ----------------------------------------------------------------------


@pytest.mark.skipif(not ORJSON_INSTALLED, reason="orjson not installed")
def test_orjson_encode_simple_dict() -> None:
    assert OrjsonSerializer().encode({"key": "value", "number": 42}) == '{"key":"value","number":42}'


@pytest.mark.skipif(not ORJSON_INSTALLED, reason="orjson not installed")
def test_orjson_encode_as_bytes() -> None:
    result = OrjsonSerializer().encode({"key": "value"}, as_bytes=True)
    assert isinstance(result, bytes)
    assert result == b'{"key":"value"}'


@pytest.mark.skipif(not ORJSON_INSTALLED, reason="orjson not installed")
def test_orjson_decode_string() -> None:
    assert OrjsonSerializer().decode('{"key":"value","number":42}') == {"key": "value", "number": 42}


@pytest.mark.skipif(not ORJSON_INSTALLED, reason="orjson not installed")
def test_orjson_decode_bytes() -> None:
    assert OrjsonSerializer().decode(b'{"key":"value"}') == {"key": "value"}


@pytest.mark.skipif(not ORJSON_INSTALLED, reason="orjson not installed")
def test_orjson_decode_bytes_passthrough() -> None:
    data = b'{"key":"value"}'
    assert OrjsonSerializer().decode(data, decode_bytes=False) == data


@pytest.mark.skipif(not ORJSON_INSTALLED, reason="orjson not installed")
def test_orjson_custom_type_encoders() -> None:
    custom_encoders: TypeEncodersMap = {CustomType: lambda x: {"custom_value": x.value}}
    serializer = OrjsonSerializer(type_encoders=custom_encoders)
    assert serializer.encode({"obj": CustomType("test")}) == '{"obj":{"custom_value":"test"}}'


@pytest.mark.skipif(not ORJSON_INSTALLED, reason="orjson not installed")
def test_orjson_mro_lookup() -> None:
    custom_encoders: TypeEncodersMap = {CustomType: lambda x: f"parent:{x.value}"}
    serializer = OrjsonSerializer(type_encoders=custom_encoders)
    parsed = json.loads(serializer.encode({"obj": ChildCustomType("child")}))
    assert parsed["obj"] == "parent:child"


@pytest.mark.skipif(not ORJSON_INSTALLED, reason="orjson not installed")
@pytest.mark.skipif(not NUMPY_INSTALLED, reason="numpy not installed")
def test_orjson_uses_numpy_option() -> None:
    """Cover the OPT_SERIALIZE_NUMPY branch in OrjsonSerializer.encode."""
    import numpy as np

    assert OrjsonSerializer().encode({"arr": np.array([1, 2, 3])}) == '{"arr":[1,2,3]}'


# ----------------------------------------------------------------------
# Standard library serializer
# ----------------------------------------------------------------------


def test_stdlib_encode_simple_dict() -> None:
    assert StandardLibSerializer().encode({"key": "value", "number": 42}) == '{"key": "value", "number": 42}'


def test_stdlib_encode_as_bytes() -> None:
    result = StandardLibSerializer().encode({"key": "value"}, as_bytes=True)
    assert isinstance(result, bytes)
    assert result == b'{"key": "value"}'


def test_stdlib_decode_string() -> None:
    assert StandardLibSerializer().decode('{"key": "value", "number": 42}') == {"key": "value", "number": 42}


def test_stdlib_decode_bytes() -> None:
    assert StandardLibSerializer().decode(b'{"key": "value"}') == {"key": "value"}


def test_stdlib_decode_bytes_passthrough() -> None:
    data = b'{"key":"value"}'
    assert StandardLibSerializer().decode(data, decode_bytes=False) == data


def test_stdlib_custom_type_encoders() -> None:
    custom_encoders: TypeEncodersMap = {CustomType: lambda x: {"custom_value": x.value}}
    serializer = StandardLibSerializer(type_encoders=custom_encoders)
    assert serializer.encode({"obj": CustomType("test")}) == '{"obj": {"custom_value": "test"}}'


def test_stdlib_mro_lookup() -> None:
    custom_encoders: TypeEncodersMap = {CustomType: lambda x: f"parent:{x.value}"}
    serializer = StandardLibSerializer(type_encoders=custom_encoders)
    assert serializer.encode({"obj": ChildCustomType("child")}) == '{"obj": "parent:child"}'


# ----------------------------------------------------------------------
# Encoding-hook fallback inside _create_enc_hook
# ----------------------------------------------------------------------


def test_enc_hook_falls_back_to_str_for_unknown_types() -> None:
    """Types with no encoder use str() so msgspec/orjson don't raise."""
    hook = StandardLibSerializer()._create_enc_hook()

    class Plain:
        def __str__(self) -> str:
            return "plain-repr"

    assert hook(Plain()) == "plain-repr"


def test_enc_hook_raises_type_error_when_str_fails() -> None:
    """When str() itself raises, _create_enc_hook reports TypeError."""
    hook = StandardLibSerializer()._create_enc_hook()

    class Hostile:
        def __str__(self) -> str:
            msg = "boom"
            raise RuntimeError(msg)

    with pytest.raises(TypeError, match="Cannot serialize Hostile"):
        hook(Hostile())


# ----------------------------------------------------------------------
# Serializer factory
# ----------------------------------------------------------------------


def test_get_serializer_default_is_singleton() -> None:
    s1 = get_serializer()
    s2 = get_serializer()
    assert s1 is s2
    assert isinstance(s1, JSONSerializer)


def test_get_serializer_caches_by_configuration() -> None:
    encoders: TypeEncodersMap = {CustomType: lambda x: x.value}
    s1 = get_serializer(encoders)
    s2 = get_serializer(encoders)
    assert s1 is s2

    s3 = get_serializer({CustomType: lambda x: "other"})
    assert s3 is not s1


def test_get_serializer_caches_repeated_lookups() -> None:
    """A second call with the same encoders hits the cache branch."""
    encoders: TypeEncodersMap = {Decimal: str}
    a = get_serializer(encoders)
    b = get_serializer(encoders)
    assert a is b


def test_get_serializer_thread_safety() -> None:
    results: list[JSONSerializer] = []

    def worker() -> None:
        results.append(get_serializer())

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(results) == 10
    assert all(r is results[0] for r in results)


def test_get_serializer_default_initialization_is_locked(monkeypatch: pytest.MonkeyPatch) -> None:
    import advanced_alchemy.utils.serialization as serialization_module

    created: list[JSONSerializer] = []
    creation_lock = threading.Lock()
    start_barrier = threading.Barrier(20)
    monkeypatch.setattr(serialization_module, "_default_serializer", None)

    def create_default_serializer() -> JSONSerializer:
        time.sleep(0.01)
        serializer = StandardLibSerializer()
        with creation_lock:
            created.append(serializer)
        return serializer

    monkeypatch.setattr(serialization_module, "_create_default_serializer", create_default_serializer)

    results: list[JSONSerializer] = []

    def worker() -> None:
        start_barrier.wait()
        results.append(serialization_module.get_serializer())

    threads = [threading.Thread(target=worker) for _ in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(created) == 1
    assert len(results) == 20
    assert all(result is created[0] for result in results)


# ----------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------


def test_encode_json_default() -> None:
    result = encode_json({"key": "value"})
    assert isinstance(result, str)
    assert "key" in result


def test_encode_json_with_type_encoders() -> None:
    result = encode_json({"obj": CustomType("test")}, type_encoders={CustomType: lambda x: x.value})
    assert result == '{"obj":"test"}'


def test_encode_json_custom_encoder_overrides_backend_native_type() -> None:
    result = encode_json({"x": Decimal("1.2")}, type_encoders={Decimal: lambda _: "custom"})
    assert result == '{"x":"custom"}'


def test_encode_json_as_bytes() -> None:
    result = encode_json({"key": "value"}, as_bytes=True)
    assert isinstance(result, bytes)
    assert b"key" in result


def test_decode_json() -> None:
    assert decode_json('{"key":"value"}') == {"key": "value"}


def test_decode_json_bytes() -> None:
    assert decode_json(b'{"key":"value"}') == {"key": "value"}


# ----------------------------------------------------------------------
# Backward compatibility helpers
# ----------------------------------------------------------------------


def test_all_exports_present() -> None:
    from advanced_alchemy.utils.serialization import __all__

    expected = {
        "BaseModel",
        "DEFAULT_TYPE_ENCODERS",
        "FilterTypeT",
        "JSONSerializer",
        "ModelDTOT",
        "ModelDictListT",
        "ModelDictT",
        "MsgspecSerializer",
        "OrjsonSerializer",
        "StandardLibSerializer",
        "SupportedSchemaModel",
        "TypeEncodersMap",
        "convert_date_to_iso",
        "convert_datetime_to_gmt_iso",
        "decode_complex_type",
        "decode_json",
        "encode_complex_type",
        "encode_json",
        "get_serializer",
        "is_schema",
        "schema_dump",
    }
    assert expected.issubset(set(__all__))


def test_encode_complex_type_datetime() -> None:
    dt = datetime.datetime(2025, 12, 17, 10, 30, 0)
    assert encode_complex_type(dt) == {"__type__": "datetime", "value": "2025-12-17T10:30:00"}


def test_encode_complex_type_date() -> None:
    d = datetime.date(2025, 12, 17)
    assert encode_complex_type(d) == {"__type__": "date", "value": "2025-12-17"}


def test_encode_complex_type_time() -> None:
    t = datetime.time(10, 30, 0)
    assert encode_complex_type(t) == {"__type__": "time", "value": "10:30:00"}


def test_encode_complex_type_timedelta() -> None:
    td = datetime.timedelta(seconds=42)
    assert encode_complex_type(td) == {"__type__": "timedelta", "value": 42.0}


def test_encode_complex_type_decimal() -> None:
    assert encode_complex_type(Decimal("19.99")) == {"__type__": "decimal", "value": "19.99"}


def test_encode_complex_type_bytes() -> None:
    assert encode_complex_type(b"\x00\xff") == {"__type__": "bytes", "value": "00ff"}


def test_encode_complex_type_uuid() -> None:
    u = UUID("12345678-1234-5678-1234-567812345678")
    assert encode_complex_type(u) == {"__type__": "uuid", "value": str(u)}


def test_encode_complex_type_set_and_frozenset() -> None:
    result = encode_complex_type({1, 2})
    assert isinstance(result, dict) and result["__type__"] == "set"
    assert sorted(result["value"]) == [1, 2]
    result = encode_complex_type(frozenset({3}))
    assert isinstance(result, dict) and result["__type__"] == "set"
    assert result["value"] == [3]


def test_encode_complex_type_unsupported_returns_none() -> None:
    assert encode_complex_type(object()) is None


def test_decode_complex_type_passes_through_primitives() -> None:
    assert decode_complex_type(42) == 42
    assert decode_complex_type("text") == "text"


def test_decode_complex_type_recurses_into_lists() -> None:
    encoded = [{"__type__": "uuid", "value": "12345678-1234-5678-1234-567812345678"}, 7]
    decoded = decode_complex_type(encoded)
    assert isinstance(decoded[0], UUID)
    assert decoded[1] == 7


def test_decode_complex_type_passes_through_plain_dict() -> None:
    assert decode_complex_type({"x": 1, "y": 2}) == {"x": 1, "y": 2}


def test_decode_complex_type_unknown_marker_returns_dict() -> None:
    marker = {"__type__": "mystery", "value": "anything"}
    assert decode_complex_type(marker) == marker


@pytest.mark.parametrize(
    ("marker", "expected"),
    [
        ({"__type__": "datetime", "value": "2025-12-17T10:30:00"}, datetime.datetime(2025, 12, 17, 10, 30, 0)),
        ({"__type__": "date", "value": "2025-12-17"}, datetime.date(2025, 12, 17)),
        ({"__type__": "time", "value": "10:30:00"}, datetime.time(10, 30, 0)),
        ({"__type__": "timedelta", "value": 42.0}, datetime.timedelta(seconds=42)),
        ({"__type__": "decimal", "value": "19.99"}, Decimal("19.99")),
        ({"__type__": "bytes", "value": "00ff"}, b"\x00\xff"),
        (
            {"__type__": "uuid", "value": "12345678-1234-5678-1234-567812345678"},
            UUID("12345678-1234-5678-1234-567812345678"),
        ),
        ({"__type__": "set", "value": [1, 2]}, {1, 2}),
    ],
)
def test_decode_complex_type_each_typed_marker(marker: dict[str, Any], expected: Any) -> None:
    assert decode_complex_type(marker) == expected


def _import_attr(module_name: str, attr_name: str) -> Any:
    module = importlib.import_module(module_name)
    return getattr(module, attr_name)


@pytest.mark.parametrize(
    ("name", "new_module"),
    [
        ("BaseModel", "advanced_alchemy.typing"),
        ("PYDANTIC_INSTALLED", "advanced_alchemy.typing"),
        ("encode_json", "advanced_alchemy.utils.serialization"),
        ("decode_json", "advanced_alchemy.utils.serialization"),
        ("encode_complex_type", "advanced_alchemy.utils.serialization"),
        ("decode_complex_type", "advanced_alchemy.utils.serialization"),
        ("convert_datetime_to_gmt_iso", "advanced_alchemy.utils.serialization"),
        ("convert_date_to_iso", "advanced_alchemy.utils.serialization"),
    ],
)
def test_legacy_serialization_shim_emits_deprecation_warning(name: str, new_module: str) -> None:
    with pytest.warns(DeprecationWarning, match=rf"Use '{new_module}\.{name}' instead"):
        value = _import_attr("advanced_alchemy._serialization", name)

    canonical = getattr(importlib.import_module(new_module), name)
    assert value is canonical


def test_legacy_serialization_shim_unknown_attribute_raises() -> None:
    with pytest.raises(AttributeError, match="not_a_real_name"):
        _import_attr("advanced_alchemy._serialization", "not_a_real_name")


def test_legacy_serialization_shim_lists_renames_in_all() -> None:
    import advanced_alchemy._serialization as shim

    expected = {
        "BaseModel",
        "PYDANTIC_INSTALLED",
        "encode_json",
        "decode_json",
        "encode_complex_type",
        "decode_complex_type",
        "convert_datetime_to_gmt_iso",
        "convert_date_to_iso",
    }
    assert expected.issubset(set(shim.__all__))


@pytest.mark.parametrize(
    ("name", "new_module"),
    [
        # Foundational typing surface
        ("ATTRS_INSTALLED", "advanced_alchemy.typing"),
        ("CATTRS_INSTALLED", "advanced_alchemy.typing"),
        ("LITESTAR_INSTALLED", "advanced_alchemy.typing"),
        ("MSGSPEC_INSTALLED", "advanced_alchemy.typing"),
        ("PYDANTIC_INSTALLED", "advanced_alchemy.typing"),
        ("SQLMODEL_INSTALLED", "advanced_alchemy.typing"),
        ("UNSET", "advanced_alchemy.typing"),
        ("BaseModel", "advanced_alchemy.typing"),
        ("Struct", "advanced_alchemy.typing"),
        ("TypeAdapter", "advanced_alchemy.typing"),
        ("UnsetType", "advanced_alchemy.typing"),
        ("FailFast", "advanced_alchemy.typing"),
        ("DTOData", "advanced_alchemy.typing"),
        ("T", "advanced_alchemy.typing"),
        # Schema/dict/attrs guards and helpers
        ("schema_dump", "advanced_alchemy.utils.serialization"),
        ("ModelDictT", "advanced_alchemy.utils.serialization"),
        ("ModelDictListT", "advanced_alchemy.utils.serialization"),
        ("ModelDTOT", "advanced_alchemy.utils.serialization"),
        ("FilterTypeT", "advanced_alchemy.utils.serialization"),
        ("SupportedSchemaModel", "advanced_alchemy.utils.serialization"),
        ("is_attrs_instance", "advanced_alchemy.utils.serialization"),
        ("is_dto_data", "advanced_alchemy.utils.serialization"),
        ("is_msgspec_struct", "advanced_alchemy.utils.serialization"),
        ("is_pydantic_model", "advanced_alchemy.utils.serialization"),
        ("is_schema", "advanced_alchemy.utils.serialization"),
        ("is_dict", "advanced_alchemy.utils.serialization"),
        ("get_type_adapter", "advanced_alchemy.utils.serialization"),
        ("structure", "advanced_alchemy.utils.serialization"),
        ("unstructure", "advanced_alchemy.utils.serialization"),
        ("fields", "advanced_alchemy.utils.serialization"),
        ("asdict", "advanced_alchemy.utils.serialization"),
        ("has", "advanced_alchemy.utils.serialization"),
    ],
)
def test_legacy_service_typing_shim_emits_deprecation_warning(name: str, new_module: str) -> None:
    with pytest.warns(DeprecationWarning, match=rf"Use '{new_module}\.{name}' instead"):
        value = _import_attr("advanced_alchemy.service.typing", name)

    canonical = getattr(importlib.import_module(new_module), name)
    assert value is canonical


def test_legacy_service_typing_shim_unknown_attribute_raises() -> None:
    with pytest.raises(AttributeError, match="not_a_real_name"):
        _import_attr("advanced_alchemy.service.typing", "not_a_real_name")


def test_legacy_service_typing_shim_keeps_pydantic_use_failfast() -> None:
    import warnings

    import advanced_alchemy.service.typing as shim

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert shim.PYDANTIC_USE_FAILFAST is False


# ----------------------------------------------------------------------
# Optional dependency integrations
# ----------------------------------------------------------------------


@pytest.mark.skipif(not NUMPY_INSTALLED, reason="numpy not installed")
def test_numpy_support() -> None:
    import numpy as np

    data = {"array": np.array([1, 2, 3]), "int": np.int64(42)}
    assert encode_json(data) == '{"array":[1,2,3],"int":42}'


@pytest.mark.skipif(not PYDANTIC_INSTALLED, reason="pydantic not installed")
def test_pydantic_support() -> None:
    from pydantic import BaseModel

    class MyModel(BaseModel):
        name: str
        age: int

    assert encode_json({"model": MyModel(name="test", age=25)}) == '{"model":{"name":"test","age":25}}'
