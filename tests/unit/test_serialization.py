"""Unit tests for the configurable serialization module."""

from __future__ import annotations

import datetime
import json
import threading
from decimal import Decimal
from enum import Enum
from ipaddress import IPv4Address, IPv4Interface, IPv4Network, IPv6Address, IPv6Interface, IPv6Network
from pathlib import Path, PurePath
from typing import Any
from uuid import UUID

import pytest

from advanced_alchemy.typing import (
    MSGSPEC_INSTALLED,
    NUMPY_INSTALLED,
    ORJSON_INSTALLED,
    PYDANTIC_INSTALLED,
)
from advanced_alchemy.utils.serialization import (
    DEFAULT_TYPE_ENCODERS,
    JSONSerializer,
    MsgspecSerializer,
    OrjsonSerializer,
    StandardLibSerializer,
    TypeEncodersMap,
    convert_date_to_iso,
    convert_datetime_to_gmt_iso,
    decode_complex_type,
    decode_json,
    encode_complex_type,
    encode_json,
    get_serializer,
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
        "DEFAULT_TYPE_ENCODERS",
        "JSONSerializer",
        "MsgspecSerializer",
        "OrjsonSerializer",
        "StandardLibSerializer",
        "TypeEncodersMap",
        "convert_date_to_iso",
        "convert_datetime_to_gmt_iso",
        "decode_complex_type",
        "decode_json",
        "encode_complex_type",
        "encode_json",
        "get_serializer",
    }
    assert set(__all__) == expected


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
