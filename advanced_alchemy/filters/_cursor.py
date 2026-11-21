"""Type-preserving, optionally signed or encrypted pagination cursor tokens.

A token is URL-safe base64 of a JSON payload holding the format version, the traversal
direction, a fingerprint of the ordering it was issued for, and the tagged sort-key values.
With a secret, the payload is signed with HMAC-SHA256 using a derived signing key, or
encrypted with AES-256-GCM (requires the optional ``cryptography`` extra,
``advanced-alchemy[cryptography]``).
"""

import base64
import binascii
import datetime as dt
import hashlib
import hmac
import json
import math
import re
import secrets
import time
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable, Final, Optional, Union, cast
from uuid import UUID

from advanced_alchemy.exceptions import ImproperConfigurationError, InvalidCursorError, MissingDependencyError
from advanced_alchemy.typing import CRYPTOGRAPHY_INSTALLED

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = (
    "CURSOR_TOKEN_MAX_LENGTH",
    "CursorEnumName",
    "DecodedCursor",
    "decode_cursor",
    "encode_cursor",
    "normalize_cursor_ttl",
    "order_fingerprint",
    "register_cursor_type",
)

CURSOR_TOKEN_MAX_LENGTH: Final = 4096
_DECIMAL_MAX_EXPONENT: Final = 6144
_TIMEDELTA_MAX_DAYS: Final = 999_999_999
_INT_LIMIT: Final = 2**127
_ENTRY_LENGTH: Final = 2
_NONCE_LENGTH: Final = 12
_SIGNED_PART_COUNT: Final = 2
_ENCRYPTED_PART_COUNT: Final = 3
_ENCRYPTED_PREFIX: Final = "e1"
_SIGNING_KEY_INFO: Final = b"advanced-alchemy-cursor-key-v1"
_ENCRYPTION_KEY_INFO: Final = b"advanced-alchemy-cursor-enc-v1"
_PAYLOAD_VERSION_KEY: Final = "v"
_PAYLOAD_DIRECTION_KEY: Final = "d"
_PAYLOAD_FINGERPRINT_KEY: Final = "o"
_PAYLOAD_KEYS_KEY: Final = "k"
_PAYLOAD_ISSUED_AT_KEY: Final = "i"
_PAYLOAD_EXPIRES_AT_KEY: Final = "e"
_B64_PART_PATTERN: Final = re.compile(r"[A-Za-z0-9_-]+")
_TAG_PATTERN: Final = re.compile(r"[a-z][a-z0-9_]{0,15}")
_RESERVED_TAGS: Final = frozenset({"n", "b", "i", "e"})
_MALFORMED: Final = "Invalid pagination cursor: malformed token"

TTLType = Union[float, dt.timedelta, None]


class CursorEnumName(str):
    """Enum member name decoded from a cursor, resolved against the key column's enum class."""

    __slots__ = ()


class DecodedCursor:
    """Decoded sort-key values and traversal direction."""

    __slots__ = ("backward", "values")

    def __init__(self, values: "tuple[Any, ...]", backward: bool) -> None:
        self.values = values
        self.backward = backward


def normalize_cursor_ttl(ttl: TTLType) -> Optional[float]:
    """Validate a cursor lifetime and return it in seconds.

    Args:
        ttl: Lifetime in seconds, a ``timedelta``, or ``None``.

    Returns:
        Positive finite seconds, or ``None`` when ``ttl`` is ``None``.

    Raises:
        TypeError: ``ttl`` has an unsupported type.
        ValueError: ``ttl`` is not positive and finite.
    """
    raw: Any = ttl
    if raw is None:
        return None
    if isinstance(raw, dt.timedelta):
        seconds = raw.total_seconds()
    elif isinstance(raw, bool) or not isinstance(raw, (int, float)):
        msg = "ttl must be a positive finite duration"
        raise TypeError(msg)
    else:
        seconds = float(raw)
    if not math.isfinite(seconds) or seconds <= 0:
        msg = "ttl must be positive and finite"
        raise ValueError(msg)
    return seconds


def register_cursor_type(
    value_type: type, tag: str, encoder: "Callable[[Any], str]", decoder: "Callable[[str], Any]"
) -> None:
    """Teach the cursor codec a sort-key value type.

    Call once at application start-up, before any cursor is issued.

    Args:
        value_type: Python type to encode.
        tag: Unique lowercase wire tag, up to 16 characters.
        encoder: Converts a value to text.
        decoder: Restores a value from text.

    Raises:
        ValueError: The type or tag is already registered, reserved, or invalid.
    """
    if (
        not _TAG_PATTERN.fullmatch(tag)
        or tag in _RESERVED_TAGS
        or tag in _DECODERS
        or value_type in _ENCODERS
        or value_type in {type(None), bool, int}
        or issubclass(value_type, Enum)
    ):
        msg = "Cursor type or tag is invalid or already registered"
        raise ValueError(msg)
    _ENCODERS[value_type] = (tag, encoder)
    _DECODERS[tag] = decoder


def order_fingerprint(parts: "Sequence[tuple[str, str, Optional[str]]]") -> str:
    """Identify an ordering so tokens cannot be replayed against a different one.

    Args:
        parts: Key names, sort directions, and NULL placements in order.

    Returns:
        A deterministic sixteen-character digest.
    """
    return hashlib.sha256(
        "|".join(f"{field}:{order}:{nulls or ''}" for field, order, nulls in parts).encode("utf-8")
    ).hexdigest()[:16]


def encode_cursor(
    values: "Sequence[Any]",
    fingerprint: str,
    *,
    backward: bool = False,
    secret: Optional[bytes] = None,
    ttl: TTLType = None,
    encrypted: bool = False,
) -> str:
    """Encode sort-key values into an opaque URL-safe token.

    Args:
        values: Sort-key values in key order.
        fingerprint: Digest of the ordering, from :func:`order_fingerprint`.
        backward: Whether the token pages backward.
        secret: Signing or encryption key.
        ttl: Token lifetime in seconds or as a ``timedelta``.
        encrypted: Encrypt the payload instead of only signing it.

    Returns:
        The cursor token.

    Raises:
        ImproperConfigurationError: A value has a type the codec cannot encode.
        MissingDependencyError: ``encrypted=True`` was requested without ``cryptography`` installed.
        ValueError: The secret, TTL, or resulting token is invalid.
    """
    ttl_seconds = normalize_cursor_ttl(ttl)
    if secret is not None and not secret:
        msg = "secret must not be empty"
        raise ValueError(msg)
    if encrypted and not secret:
        msg = "secret must not be empty when encrypted=True"
        raise ValueError(msg)

    payload: dict[str, Any] = {
        _PAYLOAD_VERSION_KEY: 1,
        _PAYLOAD_DIRECTION_KEY: "b" if backward else "f",
        _PAYLOAD_FINGERPRINT_KEY: fingerprint,
        _PAYLOAD_KEYS_KEY: [_encode_value(value) for value in values],
    }
    if ttl_seconds is not None:
        issued_at = time.time()
        payload[_PAYLOAD_ISSUED_AT_KEY] = issued_at
        payload[_PAYLOAD_EXPIRES_AT_KEY] = issued_at + ttl_seconds

    plaintext = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    if encrypted and secret:
        if not CRYPTOGRAPHY_INSTALLED:
            raise MissingDependencyError(package="cryptography")
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        key = _derive_encryption_key(secret)
        nonce = secrets.token_bytes(_NONCE_LENGTH)
        sealed = AESGCM(key).encrypt(nonce, plaintext, _ENCRYPTED_PREFIX.encode("ascii"))
        token = f"{_ENCRYPTED_PREFIX}.{_b64(nonce)}.{_b64(sealed)}"
    else:
        body = _b64(plaintext)
        token = (
            body
            if secret is None
            else f"{body}.{_b64(hmac.new(_derive_signing_key(secret), body.encode('ascii'), hashlib.sha256).digest())}"
        )
    if len(token) > CURSOR_TOKEN_MAX_LENGTH:
        msg = "Cursor token exceeds maximum length"
        raise ValueError(msg)
    return token


def decode_cursor(
    token: object,
    fingerprint: str,
    *,
    secret: Optional[bytes] = None,
    ttl: TTLType = None,
    encrypted: bool = False,
) -> DecodedCursor:
    """Validate a client-supplied token and recover its sort-key values.

    Args:
        token: Cursor token from the client.
        fingerprint: Digest of the ordering the request uses.
        secret: Signing or encryption key. When set, unsigned tokens are rejected.
        ttl: Maximum token age. When set, tokens without timestamps are rejected.
        encrypted: Require encrypted tokens when ``True``; reject them when ``False``.

    Returns:
        Sort-key values and traversal direction.

    Raises:
        InvalidCursorError: The token is malformed, tampered with, expired, or bound to another ordering.
        MissingDependencyError: ``encrypted=True`` was requested without ``cryptography`` installed.
        ValueError: The secret or TTL configuration is invalid.
    """
    ttl_seconds = normalize_cursor_ttl(ttl)
    if secret is not None and not secret:
        msg = "secret must not be empty"
        raise ValueError(msg)
    if encrypted and not secret:
        msg = "secret must not be empty when encrypted=True"
        raise ValueError(msg)
    if not isinstance(token, str) or not token or len(token) > CURSOR_TOKEN_MAX_LENGTH:
        raise InvalidCursorError(_MALFORMED)

    parts = token.split(".")
    if len(parts) == _ENCRYPTED_PART_COUNT:
        raw_bytes = _decode_encrypted_parts(parts, secret=secret, encrypted=encrypted)
    elif len(parts) in {1, _SIGNED_PART_COUNT}:
        raw_bytes = _decode_signed_parts(parts, secret=secret, encrypted=encrypted)
    else:
        raise InvalidCursorError(_MALFORMED)

    try:
        raw_payload: Any = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError) as exc:
        raise InvalidCursorError(_MALFORMED) from exc
    if not isinstance(raw_payload, dict):
        raise InvalidCursorError(_MALFORMED)
    payload = cast("dict[str, Any]", raw_payload)
    if (
        type(payload.get(_PAYLOAD_VERSION_KEY)) is not int
        or payload[_PAYLOAD_VERSION_KEY] != 1
        or payload.get(_PAYLOAD_DIRECTION_KEY) not in ("f", "b")
        or not isinstance(payload.get(_PAYLOAD_FINGERPRINT_KEY), str)
        or not isinstance(payload.get(_PAYLOAD_KEYS_KEY), list)
    ):
        raise InvalidCursorError(_MALFORMED)
    if payload[_PAYLOAD_FINGERPRINT_KEY] != fingerprint:
        msg = "Invalid pagination cursor: ordering mismatch"
        raise InvalidCursorError(msg)
    _validate_payload_timestamps(payload, ttl_seconds)
    try:
        values = tuple(_decode_value(entry) for entry in cast("list[Any]", payload[_PAYLOAD_KEYS_KEY]))
    except (ValueError, TypeError, ArithmeticError, LookupError) as exc:
        raise InvalidCursorError(_MALFORMED) from exc
    return DecodedCursor(values, bool(payload[_PAYLOAD_DIRECTION_KEY] == "b"))


def _encode_value(value: Any) -> "list[Any]":
    if value is None:
        return ["n", None]
    if type(value) is bool:
        return ["b", value]
    if isinstance(value, Enum):
        return ["e", value.name]
    for value_type in type(value).__mro__:
        if value_type is int:
            result = int(value)
            if abs(result) >= _INT_LIMIT:
                msg = "Out-of-range cursor integer"
                raise ValueError(msg)
            return ["i", result]
        if value_type in _ENCODERS:
            tag, encoder = _ENCODERS[value_type]
            encoded = encoder(value)
            if tag in {"f", "d", "td"}:
                _DECODERS[tag](encoded)
            return [tag, encoded]
    msg = f"Cannot encode cursor value of type {type(value).__name__}; register it with register_cursor_type()"
    raise ImproperConfigurationError(msg)


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _derive_signing_key(secret: bytes) -> bytes:
    return hmac.new(secret, _SIGNING_KEY_INFO, hashlib.sha256).digest()


def _derive_encryption_key(secret: bytes) -> bytes:
    return hmac.new(secret, _ENCRYPTION_KEY_INFO, hashlib.sha256).digest()


def _decode_encrypted_parts(parts: "list[str]", *, secret: Optional[bytes], encrypted: bool) -> bytes:
    if (
        parts[0] != _ENCRYPTED_PREFIX
        or _B64_PART_PATTERN.fullmatch(parts[1]) is None
        or _B64_PART_PATTERN.fullmatch(parts[2]) is None
    ):
        raise InvalidCursorError(_MALFORMED)
    if secret is None:
        msg = "Invalid pagination cursor: missing secret"
        raise InvalidCursorError(msg)
    if not encrypted:
        msg = "Invalid pagination cursor: unexpected encrypted token"
        raise InvalidCursorError(msg)
    if not CRYPTOGRAPHY_INSTALLED:
        raise MissingDependencyError(package="cryptography")
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    key = _derive_encryption_key(secret)
    nonce = _b64decode(parts[1])
    if len(nonce) != _NONCE_LENGTH:
        raise InvalidCursorError(_MALFORMED)
    sealed = _b64decode(parts[2])
    try:
        return AESGCM(key).decrypt(nonce, sealed, _ENCRYPTED_PREFIX.encode("ascii"))
    except InvalidTag as exc:
        msg = "Invalid pagination cursor: signature mismatch"
        raise InvalidCursorError(msg) from exc


def _decode_signed_parts(parts: "list[str]", *, secret: Optional[bytes], encrypted: bool) -> bytes:
    if any(_B64_PART_PATTERN.fullmatch(part) is None for part in parts):
        raise InvalidCursorError(_MALFORMED)
    if encrypted:
        msg = "Invalid pagination cursor: encryption required"
        raise InvalidCursorError(msg)
    body = parts[0]
    has_signature = len(parts) == _SIGNED_PART_COUNT
    if secret is None and has_signature:
        msg = "Invalid pagination cursor: unexpected signature"
        raise InvalidCursorError(msg)
    if secret is not None:
        if not has_signature:
            msg = "Invalid pagination cursor: missing signature"
            raise InvalidCursorError(msg)
        expected = _b64(hmac.new(_derive_signing_key(secret), body.encode("ascii"), hashlib.sha256).digest())
        if not hmac.compare_digest(expected.encode("ascii"), parts[1].encode("ascii")):
            msg = "Invalid pagination cursor: signature mismatch"
            raise InvalidCursorError(msg)
    return _b64decode(body)


def _b64decode(value: str) -> bytes:
    try:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (binascii.Error, ValueError) as exc:
        raise InvalidCursorError(_MALFORMED) from exc


def _validate_payload_timestamps(payload: "dict[str, Any]", ttl_seconds: Optional[float]) -> None:
    issued_at = _parse_timestamp_claim(payload[_PAYLOAD_ISSUED_AT_KEY]) if _PAYLOAD_ISSUED_AT_KEY in payload else None
    expires_at = (
        _parse_timestamp_claim(payload[_PAYLOAD_EXPIRES_AT_KEY]) if _PAYLOAD_EXPIRES_AT_KEY in payload else None
    )
    now = time.time()
    expired = (expires_at is not None and now >= expires_at) or (
        ttl_seconds is not None and (issued_at is None or expires_at is None or now >= issued_at + ttl_seconds)
    )
    if expired:
        msg = "Invalid pagination cursor: expired"
        raise InvalidCursorError(msg)


def _parse_timestamp_claim(raw_value: Any) -> float:
    if type(raw_value) is bool or not isinstance(raw_value, (int, float)):
        raise InvalidCursorError(_MALFORMED)
    try:
        numeric_value = float(raw_value)
    except OverflowError as exc:
        raise InvalidCursorError(_MALFORMED) from exc
    if not math.isfinite(numeric_value):
        raise InvalidCursorError(_MALFORMED)
    return numeric_value


def _decode_value(entry: Any) -> Any:
    if not isinstance(entry, list):
        msg = "Invalid cursor entry"
        raise TypeError(msg)
    pair = cast("list[Any]", entry)  # type: ignore[redundant-cast]
    if len(pair) != _ENTRY_LENGTH or not isinstance(pair[0], str):
        msg = "Invalid cursor entry"
        raise ValueError(msg)
    tag: str = pair[0]
    value: Any = pair[1]
    if tag == "n" and value is None:
        return None
    if tag == "b" and type(value) is bool:
        return value
    if tag == "i" and type(value) is int and abs(value) < _INT_LIMIT:
        return value
    if tag in _DECODERS and isinstance(value, str):
        return _DECODERS[tag](value)
    msg = "Invalid cursor value"
    raise ValueError(msg)


def _float(value: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        msg = "Non-finite cursor float"
        raise ValueError(msg)
    return result


def _decimal(value: str) -> Decimal:
    result = Decimal(value)
    if not result.is_finite() or abs(result.adjusted()) > _DECIMAL_MAX_EXPONENT:
        msg = "Out-of-range cursor decimal"
        raise ValueError(msg)
    return result


def _timedelta(value: str) -> dt.timedelta:
    days, seconds, microseconds = (int(part) for part in value.split(":"))
    if abs(days) > _TIMEDELTA_MAX_DAYS:
        msg = "Out-of-range cursor timedelta"
        raise ValueError(msg)
    return dt.timedelta(days=days, seconds=seconds, microseconds=microseconds)


_ENCODERS: "dict[type, tuple[str, Callable[[Any], str]]]" = {
    float: ("f", repr),
    str: ("s", str),
    bytes: ("y", lambda value: base64.b64encode(value).decode("ascii")),
    Decimal: ("d", str),
    UUID: ("u", str),
    dt.datetime: ("dt", lambda value: value.isoformat()),
    dt.date: ("da", lambda value: value.isoformat()),
    dt.time: ("t", lambda value: value.isoformat()),
    dt.timedelta: ("td", lambda value: f"{value.days}:{value.seconds}:{value.microseconds}"),
}

_DECODERS: "dict[str, Callable[[str], Any]]" = {
    "f": _float,
    "s": str,
    "y": lambda value: base64.b64decode(value, validate=True),
    "d": _decimal,
    "u": UUID,
    "dt": dt.datetime.fromisoformat,
    "da": dt.date.fromisoformat,
    "t": dt.time.fromisoformat,
    "td": _timedelta,
    "e": CursorEnumName,
}
