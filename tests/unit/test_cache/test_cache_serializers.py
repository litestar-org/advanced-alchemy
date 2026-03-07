"""Unit tests for cache serialization utilities."""

import datetime
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import LargeBinary, Numeric, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from advanced_alchemy._serialization import (
    _decode_typed_marker,
    decode_complex_type,
    decode_json,
    encode_complex_type,
    encode_json,
)
from advanced_alchemy.cache.serializers import default_deserializer, default_serializer


class CacheBase(DeclarativeBase):
    """Declarative base for cache serializer tests."""


class CacheModel(CacheBase):
    """Model used to test cache serialization round-trips."""

    __tablename__ = "cache_model"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(length=50))
    created_at: Mapped[datetime.datetime] = mapped_column()
    payload: Mapped[bytes] = mapped_column(LargeBinary())
    amount: Mapped[Decimal] = mapped_column(Numeric())


class OtherCacheModel(CacheBase):
    """Secondary model for mismatch tests."""

    __tablename__ = "other_cache_model"

    id: Mapped[int] = mapped_column(primary_key=True)


def test_encode_complex_type_datetime() -> None:
    """Test encoding datetime objects."""
    dt = datetime.datetime(2025, 12, 14, 10, 30, 0)

    result = encode_complex_type(dt)

    assert result == {"__type__": "datetime", "value": "2025-12-14T10:30:00"}


def test_encode_complex_type_date() -> None:
    """Test encoding date objects."""
    d = datetime.date(2025, 12, 14)

    result = encode_complex_type(d)

    assert result == {"__type__": "date", "value": "2025-12-14"}


def test_encode_complex_type_time() -> None:
    """Test encoding time objects."""
    t = datetime.time(10, 30, 45)

    result = encode_complex_type(t)

    assert result == {"__type__": "time", "value": "10:30:45"}


def test_encode_complex_type_timedelta() -> None:
    """Test encoding timedelta objects."""
    td = datetime.timedelta(hours=2, minutes=30)

    result = encode_complex_type(td)

    assert result == {"__type__": "timedelta", "value": 9000.0}


def test_encode_complex_type_decimal() -> None:
    """Test encoding Decimal objects."""
    dec = Decimal("123.45")

    result = encode_complex_type(dec)

    assert result == {"__type__": "decimal", "value": "123.45"}


def test_encode_complex_type_bytes() -> None:
    """Test encoding bytes objects."""
    b = b"\x01\x02\xff"

    result = encode_complex_type(b)

    assert result == {"__type__": "bytes", "value": "0102ff"}


def test_encode_complex_type_uuid() -> None:
    """Test encoding UUID objects."""
    u = UUID("12345678-1234-5678-1234-567812345678")

    result = encode_complex_type(u)

    assert result == {"__type__": "uuid", "value": "12345678-1234-5678-1234-567812345678"}


def test_encode_complex_type_set() -> None:
    """Test encoding set objects."""
    s = {1, 2, 3}

    result = encode_complex_type(s)

    assert result["__type__"] == "set"
    assert set(result["value"]) == {1, 2, 3}


def test_encode_complex_type_unsupported_type() -> None:
    """Test encoding unsupported type returns None."""
    result = encode_complex_type(lambda: None)
    assert result is None


def test_decode_typed_marker_datetime() -> None:
    """Test decoding datetime objects."""
    data = {"__type__": "datetime", "value": "2025-12-14T10:30:00"}

    result = _decode_typed_marker(data)

    assert isinstance(result, datetime.datetime)
    assert result == datetime.datetime(2025, 12, 14, 10, 30, 0)


def test_decode_typed_marker_date() -> None:
    """Test decoding date objects."""
    data = {"__type__": "date", "value": "2025-12-14"}

    result = _decode_typed_marker(data)

    assert isinstance(result, datetime.date)
    assert result == datetime.date(2025, 12, 14)


def test_decode_typed_marker_time() -> None:
    """Test decoding time objects."""
    data = {"__type__": "time", "value": "10:30:45"}

    result = _decode_typed_marker(data)

    assert isinstance(result, datetime.time)
    assert result == datetime.time(10, 30, 45)


def test_decode_typed_marker_timedelta() -> None:
    """Test decoding timedelta objects."""
    data = {"__type__": "timedelta", "value": 9000.0}

    result = _decode_typed_marker(data)

    assert isinstance(result, datetime.timedelta)
    assert result == datetime.timedelta(hours=2, minutes=30)


def test_decode_typed_marker_decimal() -> None:
    """Test decoding Decimal objects."""
    data = {"__type__": "decimal", "value": "123.45"}

    result = _decode_typed_marker(data)

    assert isinstance(result, Decimal)
    assert result == Decimal("123.45")


def test_decode_typed_marker_bytes() -> None:
    """Test decoding bytes objects."""
    data = {"__type__": "bytes", "value": "0102ff"}

    result = _decode_typed_marker(data)

    assert isinstance(result, bytes)
    assert result == b"\x01\x02\xff"


def test_decode_typed_marker_uuid() -> None:
    """Test decoding UUID objects."""
    data = {"__type__": "uuid", "value": "12345678-1234-5678-1234-567812345678"}

    result = _decode_typed_marker(data)

    assert isinstance(result, UUID)
    assert result == UUID("12345678-1234-5678-1234-567812345678")


def test_decode_typed_marker_set() -> None:
    """Test decoding set objects."""
    data = {"__type__": "set", "value": [1, 2, 3]}

    result = _decode_typed_marker(data)

    assert isinstance(result, set)
    assert result == {1, 2, 3}


def test_decode_complex_type_non_special_type() -> None:
    """Test decoding non-special type returns original dict."""
    data = {"foo": "bar"}

    result = decode_complex_type(data)

    assert result == {"foo": "bar"}


def test_roundtrip_json_encoding() -> None:
    """Test roundtrip encoding and decoding using AA JSON utilities."""
    test_data = {
        "datetime": datetime.datetime(2025, 12, 14, 10, 30, 0),
        "date": datetime.date(2025, 12, 14),
        "time": datetime.time(10, 30, 45),
        "timedelta": datetime.timedelta(hours=2),
        "decimal": Decimal("99.99"),
        "bytes": b"\xff\xfe",
        "uuid": UUID("12345678-1234-5678-1234-567812345678"),
        "set": {1, 2, 3},
    }

    encoded: dict[str, object] = {}
    for k, v in test_data.items():
        if (enc := encode_complex_type(v)) is not None:
            encoded[k] = enc
        else:
            encoded[k] = v

    # Encode via AA serializer
    json_str = encode_json(encoded)

    # Decode via AA parser + our special-type walker
    raw = decode_json(json_str)
    result = decode_complex_type(raw)

    assert result["datetime"] == test_data["datetime"]
    assert result["date"] == test_data["date"]
    assert result["time"] == test_data["time"]
    assert result["timedelta"] == test_data["timedelta"]
    assert result["decimal"] == test_data["decimal"]
    assert result["bytes"] == test_data["bytes"]
    assert result["uuid"] == test_data["uuid"]
    assert result["set"] == test_data["set"]


def test_decode_typed_marker_unknown_type() -> None:
    """Test _decode_typed_marker returns original dict for unknown __type__."""
    data = {"__type__": "unknown_type", "value": "something"}

    result = _decode_typed_marker(data)

    # Should return the original dict unchanged
    assert result == data
    assert isinstance(result, dict)


def test_default_serializer_plain_values_use_else_branch() -> None:
    """Test that plain int/str values go through the else branch (encode_complex_type returns None)."""

    class PlainModel(CacheBase):
        """Model with only plain-type columns."""

        __tablename__ = "plain_model"

        id: Mapped[int] = mapped_column(primary_key=True)
        name: Mapped[str] = mapped_column(String(length=50))

    instance = PlainModel(id=42, name="test")
    data = default_serializer(instance)
    decoded = decode_json(data)

    # Plain int and str should be stored directly (else branch)
    assert decoded["id"] == 42
    assert decoded["name"] == "test"
    assert decoded["__aa_model__"] == "PlainModel"


def test_default_serializer_encodes_complex_types() -> None:
    """default_serializer should encode complex types and include metadata."""
    instance = CacheModel(
        id=1,
        name="alpha",
        created_at=datetime.datetime(2025, 12, 14, 10, 30, 0),
        payload=b"\x00\xff",
        amount=Decimal("12.34"),
    )

    data = default_serializer(instance)
    decoded = decode_json(data)

    assert decoded["__aa_model__"] == "CacheModel"
    assert decoded["__aa_table__"] == "cache_model"
    assert decoded["created_at"] == {"__type__": "datetime", "value": "2025-12-14T10:30:00"}
    assert decoded["payload"] == {"__type__": "bytes", "value": "00ff"}
    assert decoded["amount"] == {"__type__": "decimal", "value": "12.34"}


def test_default_deserializer_roundtrip() -> None:
    """default_deserializer should restore decoded types and values."""
    instance = CacheModel(
        id=7,
        name="beta",
        created_at=datetime.datetime(2025, 1, 1, 9, 0, 0),
        payload=b"\xaa\xbb",
        amount=Decimal("99.99"),
    )

    serialized = default_serializer(instance)
    restored = default_deserializer(serialized, CacheModel)

    assert isinstance(restored, CacheModel)
    assert restored.id == 7
    assert restored.name == "beta"
    assert restored.created_at == datetime.datetime(2025, 1, 1, 9, 0, 0)
    assert restored.payload == b"\xaa\xbb"
    assert restored.amount == Decimal("99.99")


def test_default_deserializer_model_mismatch() -> None:
    """default_deserializer should reject mismatched model types."""
    instance = CacheModel(
        id=3,
        name="gamma",
        created_at=datetime.datetime(2025, 6, 1, 12, 0, 0),
        payload=b"\x01",
        amount=Decimal("1.00"),
    )

    serialized = default_serializer(instance)

    with pytest.raises(ValueError, match="Cannot deserialize CacheModel data as OtherCacheModel"):
        default_deserializer(serialized, OtherCacheModel)
