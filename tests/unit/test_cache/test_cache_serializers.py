"""Unit tests for cache serialization utilities."""

import datetime
from decimal import Decimal

import pytest
from sqlalchemy import LargeBinary, Numeric, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from advanced_alchemy.cache.serializers import default_deserializer, default_serializer
from advanced_alchemy.utils.serialization import decode_json


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
