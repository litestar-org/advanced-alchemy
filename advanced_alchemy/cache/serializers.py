"""Serialization utilities for caching SQLAlchemy models."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any, TypeVar, cast
from uuid import UUID

from advanced_alchemy._serialization import decode_json, encode_json

__all__ = (
    "default_deserializer",
    "default_serializer",
)

T = TypeVar("T")

# Metadata keys used in serialized data
_MODEL_KEY = "__aa_model__"
_TABLE_KEY = "__aa_table__"


def _json_encoder(obj: Any) -> Any:  # noqa: PLR0911
    """Custom JSON encoder for SQLAlchemy model attributes.

    Handles types that are not natively JSON serializable:
    - datetime, date, time: ISO format strings
    - timedelta: total seconds as float
    - Decimal: string representation
    - bytes: hex string
    - UUID: string representation
    - set, frozenset: list

    Args:
        obj: The object to encode.

    Returns:
        A JSON-serializable representation of the object.

    Raises:
        TypeError: If the object type is not supported.
    """
    if isinstance(obj, datetime):
        return {"__type__": "datetime", "value": obj.isoformat()}
    if isinstance(obj, date):
        return {"__type__": "date", "value": obj.isoformat()}
    if isinstance(obj, time):
        return {"__type__": "time", "value": obj.isoformat()}
    if isinstance(obj, timedelta):
        return {"__type__": "timedelta", "value": obj.total_seconds()}
    if isinstance(obj, Decimal):
        return {"__type__": "decimal", "value": str(obj)}
    if isinstance(obj, bytes):
        return {"__type__": "bytes", "value": obj.hex()}
    if isinstance(obj, UUID):
        return {"__type__": "uuid", "value": str(obj)}
    if isinstance(obj, (set, frozenset)):
        items: list[Any] = list(cast("set[Any] | frozenset[Any]", obj))  # type: ignore[redundant-cast]
        return {"__type__": "set", "value": items}
    msg = f"Object of type {type(obj).__name__} is not JSON serializable"
    raise TypeError(msg)


def _json_decoder(obj: dict[str, Any]) -> Any:  # noqa: PLR0911
    """Custom JSON decoder for special types.

    Args:
        obj: The dictionary to decode.

    Returns:
        The decoded object, or the original dict if not a special type.
    """
    if "__type__" not in obj:
        return obj

    type_name = obj["__type__"]
    value = obj["value"]

    if type_name == "datetime":
        return datetime.fromisoformat(value)
    if type_name == "date":
        return date.fromisoformat(value)
    if type_name == "time":
        return time.fromisoformat(value)
    if type_name == "timedelta":
        return timedelta(seconds=value)
    if type_name == "decimal":
        return Decimal(value)
    if type_name == "bytes":
        return bytes.fromhex(value)
    if type_name == "uuid":
        return UUID(value)
    if type_name == "set":
        return set(value)

    return obj


def _decode_special_types(value: Any) -> Any:
    """Recursively decode special type markers.

    When using ``encode_json`` (msgspec/orjson/json fallback), we can't rely on
    stdlib json's ``object_hook`` callback. This helper decodes the special
    ``{"__type__": ..., "value": ...}`` structures produced by ``_json_encoder``.
    """
    if isinstance(value, list):
        value_list = cast("list[Any]", value)  # type: ignore[redundant-cast]
        return [_decode_special_types(v) for v in value_list]

    if not isinstance(value, dict):
        return value

    # Decode any nested values first
    value_dict = cast("dict[Any, Any]", value)  # type: ignore[redundant-cast]
    decoded: dict[str, Any] = {str(k): _decode_special_types(v) for k, v in value_dict.items()}

    # Then decode "typed" marker dicts
    if "__type__" in decoded and "value" in decoded:
        return _json_decoder(decoded)

    return decoded


def default_serializer(model: Any) -> bytes:
    """Serialize a SQLAlchemy model instance to JSON bytes.

    This function extracts column values from a SQLAlchemy model and
    serializes them to JSON format. The serialized data includes metadata
    about the model class for validation during deserialization.

    Note:
        Relationships are NOT serialized. Only column values are included.
        The deserialized object will be a detached instance without
        relationship data loaded.

    Args:
        model: The SQLAlchemy model instance to serialize.

    Returns:
        JSON-encoded bytes representation of the model.

    Example:
        Serializing a model::

            user = User(id=1, name="John", email="john@example.com")
            data = default_serializer(user)
            # b'{"__aa_model__": "User", "__aa_table__": "users", "id": 1, ...}'
    """
    from sqlalchemy import inspect as sa_inspect

    mapper = sa_inspect(model.__class__)
    data: dict[str, Any] = {
        _MODEL_KEY: model.__class__.__name__,
        _TABLE_KEY: model.__class__.__tablename__,
    }

    for column in mapper.columns:
        # Skip internal SQLAlchemy sentinel columns (e.g., sa_orm_sentinel)
        if getattr(column, "_insert_sentinel", False):
            continue
        value = getattr(model, column.key)
        try:
            # Encode special types into JSON-friendly marker structures.
            data[column.key] = _json_encoder(value)
        except TypeError:
            # Leave unknown types alone; encode_json has its own hooks/fallbacks.
            data[column.key] = value

    return encode_json(data).encode("utf-8")


def default_deserializer(data: bytes, model_class: type[T]) -> T:
    """Deserialize JSON bytes to a SQLAlchemy model instance.

    Creates a new, detached instance of the model class populated with
    the serialized column values. The instance is NOT attached to any
    session and should be treated as a read-only snapshot.

    Warning:
        The returned instance is detached and does not have relationships
        loaded. Accessing lazy-loaded relationships will raise
        DetachedInstanceError. Use ``session.merge()`` if you need to
        work with relationships.

    Args:
        data: JSON bytes to deserialize.
        model_class: The SQLAlchemy model class to instantiate.

    Returns:
        A new, detached instance of the model class.

    Raises:
        ValueError: If the serialized data is for a different model class.

    Example:
        Deserializing data::

            data = b'{"__aa_model__": "User", "id": 1, "name": "John"}'
            user = default_deserializer(data, User)
            # user is a detached User instance
    """
    parsed_raw = decode_json(data)
    parsed = _decode_special_types(parsed_raw)

    # Validate model class matches
    serialized_model = parsed.pop(_MODEL_KEY, None)
    parsed.pop(_TABLE_KEY, None)  # Remove table key, not needed for instantiation

    if serialized_model and serialized_model != model_class.__name__:
        msg = f"Cannot deserialize {serialized_model} data as {model_class.__name__}"
        raise ValueError(msg)

    # Create detached instance using constructor
    # This properly initializes SQLAlchemy's ORM state
    instance: T = model_class(**parsed)

    return instance
