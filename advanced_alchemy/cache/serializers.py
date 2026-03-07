"""Serialization utilities for caching SQLAlchemy models."""

from typing import Any, TypeVar

from sqlalchemy import inspect as sa_inspect

from advanced_alchemy._serialization import (
    decode_complex_type,
    decode_json,
    encode_complex_type,
    encode_json,
)

__all__ = (
    "default_deserializer",
    "default_serializer",
)

T = TypeVar("T")

_MODEL_KEY = "__aa_model__"
"""Metadata key for the model class name in serialized data."""

_TABLE_KEY = "__aa_table__"
"""Metadata key for the table name in serialized data."""


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

        # Encode special types into JSON-friendly marker structures.
        if (encoded := encode_complex_type(value)) is not None:
            data[column.key] = encoded
        else:
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
    parsed = decode_complex_type(parsed_raw)

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
