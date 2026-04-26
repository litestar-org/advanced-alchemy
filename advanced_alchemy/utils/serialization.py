"""Configurable JSON serialization with Protocol-based architecture.

This module provides a flexible serialization system that supports:
- Custom type encoders via the ``type_encoders`` parameter
- Multiple backend support (msgspec, orjson, standard library)
- Thread-safe caching of serializer instances
- Integration with Litestar's type_encoders pattern

Example:
    Basic usage with default encoders::

        >>> from advanced_alchemy.utils.serialization import encode_json, decode_json
        >>> import datetime
        >>> encode_json({"date": datetime.date.today()})
        '{"date":"2025-12-17"}'

    Custom type encoders::

        >>> from decimal import Decimal
        >>> class Money:
        ...     def __init__(self, amount: Decimal):
        ...         self.amount = amount
        >>> encode_json(
        ...     {"price": Money(Decimal("19.99"))},
        ...     type_encoders={Money: lambda m: str(m.amount)}
        ... )
        '{"price":"19.99"}'
"""

import datetime
import enum
import json
import threading
from abc import ABC, abstractmethod
from collections.abc import Mapping
from decimal import Decimal
from ipaddress import IPv4Address, IPv4Interface, IPv4Network, IPv6Address, IPv6Interface, IPv6Network
from pathlib import Path, PurePath
from typing import Any, Callable, Final, Literal, Optional, Protocol, Union, cast, overload, runtime_checkable
from uuid import UUID

from advanced_alchemy.typing import (
    MSGSPEC_INSTALLED,
    NUMPY_INSTALLED,
    ORJSON_INSTALLED,
    PYDANTIC_INSTALLED,
)

__all__ = (
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
)

# Type aliases
TypeEncodersMap = Mapping[type, Callable[[Any], Any]]
"""Mapping of types to encoder functions for custom serialization."""


# ============================================================================
# Helper functions
# ============================================================================


def convert_datetime_to_gmt_iso(dt: datetime.datetime) -> str:
    """Convert datetime to ISO 8601 format with UTC timezone.

    If the datetime is naive (no timezone), UTC is assumed.
    The ``+00:00`` suffix is replaced with ``Z`` for consistency.

    Args:
        dt: The datetime to convert.

    Returns:
        ISO 8601 formatted datetime string with ``Z`` suffix for UTC.

    Example:
        >>> import datetime
        >>> dt = datetime.datetime(2025, 12, 17, 10, 30, 0)
        >>> convert_datetime_to_gmt_iso(dt)
        '2025-12-17T10:30:00Z'
    """
    if not dt.tzinfo:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


def convert_date_to_iso(dt: datetime.date) -> str:
    """Convert date to ISO 8601 format.

    Args:
        dt: The date to convert.

    Returns:
        ISO 8601 formatted date string (YYYY-MM-DD).

    Example:
        >>> import datetime
        >>> convert_date_to_iso(datetime.date(2025, 12, 17))
        '2025-12-17'
    """
    return dt.isoformat()


# ============================================================================
# Default type encoders
# ============================================================================


def _build_default_type_encoders() -> dict[type, Callable[[Any], Any]]:
    """Build the default type encoders dictionary.

    This function constructs the default encoders, including optional
    encoders for numpy and pydantic if those packages are installed.

    Returns:
        Dictionary mapping types to encoder functions.
    """
    encoders: dict[type, Callable[[Any], Any]] = {
        # Datetime types
        datetime.datetime: convert_datetime_to_gmt_iso,
        datetime.date: convert_date_to_iso,
        datetime.time: lambda v: v.isoformat(),
        datetime.timedelta: lambda v: v.total_seconds(),
        # Numeric types
        Decimal: str,  # Preserve precision as string
        # UUID and path types
        UUID: str,
        Path: str,
        PurePath: str,
        # Network types
        IPv4Address: str,
        IPv4Interface: str,
        IPv4Network: str,
        IPv6Address: str,
        IPv6Interface: str,
        IPv6Network: str,
        # Collection types
        frozenset: list,
        set: list,
        # Bytes
        bytes: lambda v: v.decode("utf-8", errors="replace"),
        # Enum (use .value to get the underlying value)
        enum.Enum: lambda v: v.value,
    }

    # Optional NumPy support
    if NUMPY_INSTALLED:
        import numpy as np

        encoders[np.ndarray] = lambda v: v.tolist()
        encoders[np.integer] = int
        encoders[np.floating] = float
        encoders[np.bool_] = bool

    # Optional Pydantic support
    if PYDANTIC_INSTALLED:
        from pydantic import BaseModel

        encoders[BaseModel] = lambda v: v.model_dump(mode="json")

    return encoders


DEFAULT_TYPE_ENCODERS: Final[dict[type, Callable[[Any], Any]]] = _build_default_type_encoders()
"""Default type encoders for common Python types.

These encoders handle serialization of types not natively supported
by JSON serializers. Users can override these by passing custom
``type_encoders`` to serializer functions.

Supported types:
    - ``datetime.datetime``: ISO 8601 with UTC timezone (Z suffix)
    - ``datetime.date``: ISO 8601 date format
    - ``datetime.time``: ISO 8601 time format
    - ``datetime.timedelta``: Total seconds as float
    - ``Decimal``: String representation (preserves precision)
    - ``UUID``: String representation
    - ``Path``, ``PurePath``: String representation
    - ``IPv4Address``, ``IPv6Address``, etc.: String representation
    - ``set``, ``frozenset``: Converted to list
    - ``bytes``: UTF-8 decoded string
    - ``enum.Enum``: Value of the enum member
    - ``numpy.ndarray``: Converted to list (if numpy installed)
    - ``pydantic.BaseModel``: model_dump with mode="json" (if pydantic installed)
"""


# ============================================================================
# Protocol and base classes
# ============================================================================


@runtime_checkable
class JSONSerializer(Protocol):
    """Protocol defining the JSON serialization interface.

    Implement this protocol to create custom serializers that integrate
    with Advanced Alchemy's serialization system.

    Example:
        >>> class MySerializer:
        ...     def encode(
        ...         self, data: Any, *, as_bytes: bool = False
        ...     ) -> "Union[str, bytes]":
        ...         # Custom encoding logic
        ...         pass
        ...
        ...     def decode(
        ...         self,
        ...         data: "Union[str, bytes]",
        ...         *,
        ...         decode_bytes: bool = True,
        ...     ) -> Any:
        ...         # Custom decoding logic
        ...         pass
    """

    @overload
    def encode(self, data: Any, *, as_bytes: Literal[False] = ...) -> str: ...

    @overload
    def encode(self, data: Any, *, as_bytes: Literal[True]) -> bytes: ...

    @overload
    def encode(self, data: Any, *, as_bytes: bool) -> "Union[str, bytes]": ...

    def encode(self, data: Any, *, as_bytes: bool = False) -> "Union[str, bytes]":
        """Encode data to JSON.

        Args:
            data: Data to encode.
            as_bytes: If True, return bytes; otherwise return str.

        Returns:
            JSON string or bytes representation.
        """
        ...

    def decode(self, data: "Union[str, bytes]", *, decode_bytes: bool = True) -> Any:
        """Decode JSON to Python object.

        Args:
            data: JSON string or bytes to decode.
            decode_bytes: If True, decode bytes input; otherwise return as-is.

        Returns:
            Decoded Python object.
        """
        ...


class BaseJSONSerializer(ABC):
    """Abstract base class for JSON serializers.

    Provides common functionality for serializer implementations including
    type encoder merging and enc_hook creation.
    """

    __slots__ = ("_type_encoders",)

    def __init__(self, type_encoders: "Optional[TypeEncodersMap]" = None) -> None:
        """Initialize serializer with optional custom type encoders.

        Args:
            type_encoders: Custom type encoders to merge with defaults.
                User-provided encoders take precedence over defaults.
        """
        self._type_encoders: dict[type, Callable[[Any], Any]] = {
            **DEFAULT_TYPE_ENCODERS,
            **(type_encoders or {}),
        }

    def _create_enc_hook(self) -> "Callable[[Any], Any]":
        """Create an encoding hook function from type_encoders.

        The hook walks the MRO of the value's type to find a matching
        encoder, allowing encoders for parent classes to handle subclasses.

        Returns:
            Encoding hook function suitable for msgspec/orjson.
        """
        type_encoders = self._type_encoders

        def enc_hook(value: Any) -> Any:
            # Walk MRO to find encoder for value's type or parent class
            for base in value.__class__.__mro__[:-1]:
                encoder = type_encoders.get(base)
                if encoder is not None:
                    return encoder(value)
            # Fallback: try string conversion
            try:
                return str(value)
            except Exception as exc:
                msg = f"Cannot serialize {type(value).__name__}"
                raise TypeError(msg) from exc

        return enc_hook

    @overload
    @abstractmethod
    def encode(self, data: Any, *, as_bytes: Literal[False] = ...) -> str: ...

    @overload
    @abstractmethod
    def encode(self, data: Any, *, as_bytes: Literal[True]) -> bytes: ...

    @overload
    @abstractmethod
    def encode(self, data: Any, *, as_bytes: bool) -> "Union[str, bytes]": ...

    @abstractmethod
    def encode(self, data: Any, *, as_bytes: bool = False) -> "Union[str, bytes]":
        """Encode data to JSON."""
        ...

    @abstractmethod
    def decode(self, data: "Union[str, bytes]", *, decode_bytes: bool = True) -> Any:
        """Decode JSON to Python object."""
        ...


# ============================================================================
# Serializer implementations
# ============================================================================


class MsgspecSerializer(BaseJSONSerializer):
    """High-performance JSON serializer using msgspec.

    This is the preferred serializer when msgspec is available, offering
    the best performance for JSON encoding/decoding.

    Example:
        >>> serializer = MsgspecSerializer()
        >>> serializer.encode({"key": "value"})
        '{"key":"value"}'

        >>> # With custom type encoders
        >>> serializer = MsgspecSerializer(type_encoders={set: sorted})
        >>> serializer.encode({"items": {3, 1, 2}})
        '{"items":[1,2,3]}'
    """

    __slots__ = ("_decoder", "_enc_hook", "_encoder")

    def __init__(
        self,
        type_encoders: "Optional[TypeEncodersMap]" = None,
        enc_hook: "Optional[Callable[[Any], Any]]" = None,
    ) -> None:
        """Initialize msgspec serializer.

        Args:
            type_encoders: Custom type encoders to merge with defaults.
            enc_hook: Optional custom encoding hook. If provided, type_encoders
                is ignored and this hook is used directly for complete control.
        """
        from msgspec.json import Decoder, Encoder

        super().__init__(type_encoders)

        self._enc_hook = enc_hook if enc_hook is not None else self._create_enc_hook()
        self._encoder: Final = Encoder(enc_hook=self._enc_hook)
        self._decoder: Final = Decoder()

    @overload
    def encode(self, data: Any, *, as_bytes: Literal[False] = ...) -> str: ...

    @overload
    def encode(self, data: Any, *, as_bytes: Literal[True]) -> bytes: ...

    @overload
    def encode(self, data: Any, *, as_bytes: bool) -> "Union[str, bytes]": ...

    def encode(self, data: Any, *, as_bytes: bool = False) -> "Union[str, bytes]":
        """Encode data to JSON using msgspec.

        Args:
            data: Data to encode.
            as_bytes: If True, return bytes; otherwise return UTF-8 string.

        Returns:
            JSON representation as string or bytes.
        """
        result = self._encoder.encode(data)
        return result if as_bytes else result.decode("utf-8")

    def decode(self, data: "Union[str, bytes]", *, decode_bytes: bool = True) -> Any:
        """Decode JSON using msgspec.

        Args:
            data: JSON string or bytes to decode.
            decode_bytes: If True, decode bytes input; otherwise return as-is.

        Returns:
            Decoded Python object.
        """
        if isinstance(data, str):
            data = data.encode("utf-8")
        elif not decode_bytes:
            return data
        return self._decoder.decode(data)


class OrjsonSerializer(BaseJSONSerializer):
    """High-performance JSON serializer using orjson.

    Provides excellent performance with native support for datetime,
    UUID, and numpy serialization.

    Example:
        >>> serializer = OrjsonSerializer()
        >>> serializer.encode({"key": "value"})
        '{"key":"value"}'
    """

    __slots__ = ("_enc_hook",)

    def __init__(self, type_encoders: "Optional[TypeEncodersMap]" = None) -> None:
        """Initialize orjson serializer.

        Args:
            type_encoders: Custom type encoders to merge with defaults.
        """
        super().__init__(type_encoders)
        self._enc_hook = self._create_enc_hook()

    @overload
    def encode(self, data: Any, *, as_bytes: Literal[False] = ...) -> str: ...

    @overload
    def encode(self, data: Any, *, as_bytes: Literal[True]) -> bytes: ...

    @overload
    def encode(self, data: Any, *, as_bytes: bool) -> "Union[str, bytes]": ...

    def encode(self, data: Any, *, as_bytes: bool = False) -> "Union[str, bytes]":
        """Encode data to JSON using orjson.

        Args:
            data: Data to encode.
            as_bytes: If True, return bytes; otherwise return UTF-8 string.

        Returns:
            JSON representation as string or bytes.
        """
        import orjson  # type: ignore[import-not-found]  # pyright: ignore[reportMissingImports]

        orjson_module: Any = orjson
        options: int = orjson_module.OPT_NAIVE_UTC | orjson_module.OPT_SERIALIZE_UUID
        if NUMPY_INSTALLED:
            options |= orjson_module.OPT_SERIALIZE_NUMPY

        result: bytes = orjson_module.dumps(data, default=self._enc_hook, option=options)
        return result if as_bytes else result.decode("utf-8")

    def decode(self, data: "Union[str, bytes]", *, decode_bytes: bool = True) -> Any:
        """Decode JSON using orjson.

        Args:
            data: JSON string or bytes to decode.
            decode_bytes: If True, decode bytes input; otherwise return as-is.

        Returns:
            Decoded Python object.
        """
        import orjson  # type: ignore[import-not-found]  # pyright: ignore[reportMissingImports]

        orjson_module: Any = orjson
        if isinstance(data, bytes) and not decode_bytes:
            return data
        return orjson_module.loads(data)


class StandardLibSerializer(BaseJSONSerializer):
    """JSON serializer using Python's standard library.

    Fallback serializer when neither msgspec nor orjson is available.
    Slower than the alternatives but always available.

    Example:
        >>> serializer = StandardLibSerializer()
        >>> serializer.encode({"key": "value"})
        '{"key": "value"}'
    """

    __slots__ = ("_enc_hook",)

    def __init__(self, type_encoders: "Optional[TypeEncodersMap]" = None) -> None:
        """Initialize standard library serializer.

        Args:
            type_encoders: Custom type encoders to merge with defaults.
        """
        super().__init__(type_encoders)
        self._enc_hook = self._create_enc_hook()

    @overload
    def encode(self, data: Any, *, as_bytes: Literal[False] = ...) -> str: ...

    @overload
    def encode(self, data: Any, *, as_bytes: Literal[True]) -> bytes: ...

    @overload
    def encode(self, data: Any, *, as_bytes: bool) -> "Union[str, bytes]": ...

    def encode(self, data: Any, *, as_bytes: bool = False) -> "Union[str, bytes]":
        """Encode data to JSON using standard library.

        Args:
            data: Data to encode.
            as_bytes: If True, return bytes; otherwise return string.

        Returns:
            JSON representation as string or bytes.
        """
        result = json.dumps(data, default=self._enc_hook)
        return result.encode("utf-8") if as_bytes else result

    def decode(self, data: "Union[str, bytes]", *, decode_bytes: bool = True) -> Any:
        """Decode JSON using standard library.

        Args:
            data: JSON string or bytes to decode.
            decode_bytes: If True, decode bytes input; otherwise return as-is.

        Returns:
            Decoded Python object.
        """
        if isinstance(data, bytes):
            if not decode_bytes:
                return data
            data = data.decode("utf-8")
        return json.loads(data)


# ============================================================================
# Serializer factory with caching
# ============================================================================

_serializer_cache: "dict[frozenset[tuple[type, int]], JSONSerializer]" = {}
_cache_lock: Final[threading.RLock] = threading.RLock()
_default_serializer: "Optional[JSONSerializer]" = None


def _create_default_serializer() -> "JSONSerializer":
    """Create the default serializer based on available libraries.

    Priority: msgspec > orjson > standard library

    Returns:
        Best available JSON serializer.
    """
    if MSGSPEC_INSTALLED:
        return MsgspecSerializer()
    if ORJSON_INSTALLED:
        return OrjsonSerializer()
    return StandardLibSerializer()


def _create_serializer(type_encoders: "TypeEncodersMap") -> "JSONSerializer":
    """Create a serializer with custom type encoders.

    Args:
        type_encoders: Custom type encoders mapping.

    Returns:
        JSON serializer configured with the given encoders.
    """
    if MSGSPEC_INSTALLED:
        return MsgspecSerializer(type_encoders=type_encoders)
    if ORJSON_INSTALLED:
        return OrjsonSerializer(type_encoders=type_encoders)
    return StandardLibSerializer(type_encoders=type_encoders)


def get_serializer(type_encoders: "Optional[TypeEncodersMap]" = None) -> "JSONSerializer":
    """Get a cached serializer instance.

    This factory function returns cached serializer instances to avoid
    recreating encoders for the same configuration. The default serializer
    (no custom type_encoders) is a singleton for maximum performance.

    Args:
        type_encoders: Optional mapping of types to encoder functions.
            If None, returns the default singleton serializer.

    Returns:
        A JSONSerializer instance configured with the given type encoders.

    Example:
        >>> # Default serializer (singleton)
        >>> s1 = get_serializer()
        >>> s2 = get_serializer()
        >>> s1 is s2
        True

        >>> # Custom type encoders (cached by configuration)
        >>> encoders = {str: lambda s: s.upper()}
        >>> s3 = get_serializer(encoders)
        >>> s4 = get_serializer(encoders)
        >>> s3 is s4
        True
    """
    global _default_serializer  # noqa: PLW0603

    if type_encoders is None:
        if _default_serializer is None:
            _default_serializer = _create_default_serializer()
        return _default_serializer

    # Create hashable cache key using type and function id
    # Note: Different lambda objects create different keys even if equivalent
    try:
        cache_key = frozenset((k, id(v)) for k, v in type_encoders.items())
    except TypeError:
        # Fallback for unhashable keys - create without caching
        return _create_serializer(type_encoders)

    with _cache_lock:
        if cache_key not in _serializer_cache:
            _serializer_cache[cache_key] = _create_serializer(type_encoders)
        return _serializer_cache[cache_key]


# ============================================================================
# Public API functions
# ============================================================================


@overload
def encode_json(data: Any) -> str: ...


@overload
def encode_json(data: Any, *, as_bytes: Literal[False]) -> str: ...


@overload
def encode_json(data: Any, *, as_bytes: Literal[True]) -> bytes: ...


@overload
def encode_json(data: Any, *, type_encoders: "TypeEncodersMap") -> str: ...


@overload
def encode_json(data: Any, *, type_encoders: TypeEncodersMap, as_bytes: Literal[False]) -> str: ...


@overload
def encode_json(data: Any, *, type_encoders: TypeEncodersMap, as_bytes: Literal[True]) -> bytes: ...


def encode_json(
    data: Any,
    *,
    type_encoders: "Optional[TypeEncodersMap]" = None,
    as_bytes: bool = False,
) -> "Union[str, bytes]":
    """Encode data to JSON with optional custom type encoders.

    This is the primary interface for JSON encoding in Advanced Alchemy.
    It supports custom type encoders that can be passed per-call.

    Args:
        data: Data to encode to JSON.
        type_encoders: Optional mapping of types to encoder functions.
            These are merged with DEFAULT_TYPE_ENCODERS, with user
            encoders taking precedence.
        as_bytes: If True, return bytes; otherwise return str.

    Returns:
        JSON representation of data as string or bytes.

    Example:
        >>> import datetime
        >>> encode_json({"date": datetime.date(2025, 12, 17)})
        '{"date":"2025-12-17"}'

        >>> # Custom type encoder
        >>> class Point:
        ...     def __init__(self, x, y):
        ...         self.x, self.y = x, y
        >>> encode_json(
        ...     {"point": Point(1, 2)},
        ...     type_encoders={Point: lambda p: [p.x, p.y]},
        ... )
        '{"point":[1,2]}'

        >>> # Return bytes
        >>> encode_json({"key": "value"}, as_bytes=True)
        b'{"key":"value"}'
    """
    serializer = get_serializer(type_encoders)
    return serializer.encode(data, as_bytes=as_bytes)


def decode_json(data: "Union[str, bytes]", *, decode_bytes: bool = True) -> Any:
    """Decode JSON string or bytes to Python object.

    Args:
        data: JSON string or bytes to decode.
        decode_bytes: If True, decode bytes input. If False, bytes
            are returned as-is without decoding.

    Returns:
        Decoded Python object.

    Example:
        >>> decode_json('{"key": "value"}')
        {'key': 'value'}

        >>> decode_json(b'{"key": "value"}')
        {'key': 'value'}
    """
    serializer = get_serializer()
    return serializer.decode(data, decode_bytes=decode_bytes)


def encode_complex_type(obj: Any) -> Any:  # noqa: PLR0911
    """Convert an object to a JSON-serializable format if possible.

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
        A JSON-serializable representation of the object, or None if the type is not supported.
    """
    if isinstance(obj, datetime.datetime):
        return {"__type__": "datetime", "value": obj.isoformat()}
    if isinstance(obj, datetime.date):
        return {"__type__": "date", "value": obj.isoformat()}
    if isinstance(obj, datetime.time):
        return {"__type__": "time", "value": obj.isoformat()}
    if isinstance(obj, datetime.timedelta):
        return {"__type__": "timedelta", "value": obj.total_seconds()}
    if isinstance(obj, Decimal):
        return {"__type__": "decimal", "value": str(obj)}
    if isinstance(obj, bytes):
        return {"__type__": "bytes", "value": obj.hex()}
    if isinstance(obj, UUID):
        return {"__type__": "uuid", "value": str(obj)}
    if isinstance(obj, (set, frozenset)):
        items: list[Any] = list(cast("Union[set[Any], frozenset[Any]]", obj))  # type: ignore[redundant-cast]
        return {"__type__": "set", "value": items}
    return None


def decode_complex_type(value: Any) -> Any:
    """Recursively decode special type markers.

    Decodes the special `{"__type__": ..., "value": ...}` structures.
    """
    if isinstance(value, list):
        value_list = cast("list[Any]", value)  # type: ignore[redundant-cast]
        return [decode_complex_type(v) for v in value_list]

    if not isinstance(value, dict):
        return value

    # Decode any nested values first
    value_dict = cast("dict[Any, Any]", value)  # type: ignore[redundant-cast]
    decoded: dict[str, Any] = {str(k): decode_complex_type(v) for k, v in value_dict.items()}

    # Then decode "typed" marker dicts
    if "__type__" in decoded and "value" in decoded:
        return _decode_typed_marker(decoded)

    return decoded


def _decode_typed_marker(obj: dict[str, Any]) -> Any:  # noqa: PLR0911
    """Custom JSON decoder for special types.

    Args:
        obj: The dictionary to decode.

    Returns:
        The decoded object, or the original dict if not a special type.
    """
    type_name = obj["__type__"]
    value = obj["value"]

    if type_name == "datetime":
        return datetime.datetime.fromisoformat(value)
    if type_name == "date":
        return datetime.date.fromisoformat(value)
    if type_name == "time":
        return datetime.time.fromisoformat(value)
    if type_name == "timedelta":
        return datetime.timedelta(seconds=value)
    if type_name == "decimal":
        return Decimal(value)
    if type_name == "bytes":
        return bytes.fromhex(value)
    if type_name == "uuid":
        return UUID(value)
    if type_name == "set":
        return set(value)

    return obj
