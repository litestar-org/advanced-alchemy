"""Cursor token codec: round-trips, signing, expiry, encryption, and rejection of bad tokens."""

import base64
import datetime as dt
import enum
import hashlib
import hmac
import json
from decimal import Decimal
from typing import Any
from unittest.mock import patch
from uuid import UUID

import pytest

from advanced_alchemy.exceptions import (
    ImproperConfigurationError,
    InvalidCursorError,
    MissingDependencyError,
    RepositoryError,
)
from advanced_alchemy.filters._cursor import (
    CURSOR_TOKEN_MAX_LENGTH,
    CursorEnumName,
    decode_cursor,
    encode_cursor,
    order_fingerprint,
    register_cursor_type,
)

FINGERPRINT = order_fingerprint([("created_at", "desc", None), ("id", "desc", None)])
SECRET = b"cursor-test-secret"


class Color(enum.Enum):
    RED = "red"
    BLUE = "blue"


class Priority(enum.IntEnum):
    LOW = 1
    HIGH = 2


@pytest.mark.parametrize(
    "value",
    [
        None,
        True,
        False,
        0,
        -42,
        2**100,
        1.5,
        1e-9,
        "plain",
        "pipes|||and.dots",
        "naïve ✓",
        b"\x00\xffbytes",
        Decimal("1E+3"),
        Decimal("-0.000001"),
        UUID("12345678-1234-5678-1234-567812345678"),
        dt.datetime(2026, 11, 17, 1, 2, 3, 456789),
        dt.datetime(2026, 11, 17, 1, 2, 3, tzinfo=dt.timezone.utc),
        dt.date(2026, 11, 17),
        dt.time(23, 59, 1, 5),
        dt.timedelta(days=-3, seconds=7, microseconds=9),
    ],
)
def test_round_trip_preserves_type_and_value(value: Any) -> None:
    decoded = decode_cursor(encode_cursor([value], FINGERPRINT), FINGERPRINT)

    assert decoded.values == (value,)
    assert type(decoded.values[0]) is type(value)
    assert decoded.backward is False


@pytest.mark.parametrize("member", [Color.BLUE, Priority.HIGH])
def test_enum_members_round_trip_as_names(member: enum.Enum) -> None:
    (decoded,) = decode_cursor(encode_cursor([member], FINGERPRINT), FINGERPRINT).values

    assert isinstance(decoded, CursorEnumName)
    assert decoded == member.name


def test_backward_flag_round_trips() -> None:
    token = encode_cursor([1, "a"], FINGERPRINT, backward=True)

    decoded = decode_cursor(token, FINGERPRINT)

    assert decoded.values == (1, "a")
    assert decoded.backward is True


def test_unsigned_token_is_url_safe_and_unpadded() -> None:
    token = encode_cursor(["?&=/+", 10**20], FINGERPRINT)

    assert all(char.isalnum() or char in "-_" for char in token)


def test_ordering_mismatch_is_rejected() -> None:
    token = encode_cursor([1], FINGERPRINT)
    other = order_fingerprint([("name", "asc", None)])

    with pytest.raises(InvalidCursorError, match="ordering mismatch"):
        decode_cursor(token, other)


@pytest.mark.parametrize(
    "token",
    [
        None,
        42,
        "",
        "x" * (CURSOR_TOKEN_MAX_LENGTH + 1),
        "not base64!",
        "a.b.c.d",
        base64.urlsafe_b64encode(b"\xff\xfe").decode().rstrip("="),
        base64.urlsafe_b64encode(b"[1, 2]").decode().rstrip("="),
    ],
)
def test_malformed_tokens_are_rejected(token: object) -> None:
    with pytest.raises(InvalidCursorError, match="malformed"):
        decode_cursor(token, FINGERPRINT)


def _forge(payload: "dict[str, Any]") -> str:
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")


@pytest.mark.parametrize(
    "payload",
    [
        {"v": 2, "d": "f", "o": FINGERPRINT, "k": []},
        {"v": True, "d": "f", "o": FINGERPRINT, "k": []},
        {"v": 1, "d": "x", "o": FINGERPRINT, "k": []},
        {"v": 1, "d": "f", "o": FINGERPRINT, "k": [["zz", "1"]]},
        {"v": 1, "d": "f", "o": FINGERPRINT, "k": [["i", "1"]]},
        {"v": 1, "d": "f", "o": FINGERPRINT, "k": [["i", 2**130]]},
        {"v": 1, "d": "f", "o": FINGERPRINT, "k": [["f", "nan"]]},
        {"v": 1, "d": "f", "o": FINGERPRINT, "k": [["d", "1E+9999"]]},
        {"v": 1, "d": "f", "o": FINGERPRINT, "k": [["dt", "yesterday"]]},
        {"v": 1, "d": "f", "o": FINGERPRINT, "k": [["i", 1]], "e": "soon"},
    ],
)
def test_forged_payloads_are_rejected(payload: "dict[str, Any]") -> None:
    with pytest.raises(InvalidCursorError, match="malformed"):
        decode_cursor(_forge(payload), FINGERPRINT)


def test_signed_token_round_trips_with_matching_secret() -> None:
    token = encode_cursor([7], FINGERPRINT, secret=SECRET)

    assert token.count(".") == 1
    assert decode_cursor(token, FINGERPRINT, secret=SECRET).values == (7,)


@pytest.mark.parametrize(
    ("mutate", "secret", "message"),
    [
        (lambda token: token, b"wrong-secret", "signature mismatch"),
        (lambda token: token[:-3], SECRET, "signature mismatch"),
        (lambda token: ("B" if token[0] != "B" else "C") + token[1:], SECRET, "signature mismatch"),
        (lambda token: token.split(".")[0], SECRET, "missing signature"),
        (lambda token: token, None, "unexpected signature"),
    ],
)
def test_signature_failures_are_rejected(mutate: Any, secret: "bytes | None", message: str) -> None:
    token = mutate(encode_cursor([7], FINGERPRINT, secret=SECRET))

    with pytest.raises(InvalidCursorError, match=message):
        decode_cursor(token, FINGERPRINT, secret=secret)


def test_ttl_accepts_fresh_and_rejects_expired_tokens() -> None:
    with patch("advanced_alchemy.filters._cursor.time.time", return_value=1_000.0):
        token = encode_cursor([1], FINGERPRINT, ttl=dt.timedelta(minutes=5))
    with patch("advanced_alchemy.filters._cursor.time.time", return_value=1_100.0):
        assert decode_cursor(token, FINGERPRINT, ttl=300).values == (1,)
    with patch("advanced_alchemy.filters._cursor.time.time", return_value=1_301.0):
        with pytest.raises(InvalidCursorError, match="expired"):
            decode_cursor(token, FINGERPRINT, ttl=300)


def test_ttl_rejects_tokens_without_timestamps() -> None:
    with pytest.raises(InvalidCursorError, match="expired"):
        decode_cursor(encode_cursor([1], FINGERPRINT), FINGERPRINT, ttl=60)


def test_encrypted_tokens_hide_values_and_vary_per_issue() -> None:
    first = encode_cursor(["secret-value"], FINGERPRINT, secret=SECRET, encrypted=True)
    second = encode_cursor(["secret-value"], FINGERPRINT, secret=SECRET, encrypted=True)

    assert first != second
    assert first.startswith("e1.")
    assert b"secret-value" not in base64.urlsafe_b64decode(first.split(".")[2] + "==")
    assert decode_cursor(first, FINGERPRINT, secret=SECRET, encrypted=True).values == ("secret-value",)


@pytest.mark.parametrize("fingerprint", ["created_at:desc", "v1.order", FINGERPRINT])
def test_encrypted_tokens_round_trip_with_arbitrary_fingerprints(fingerprint: str) -> None:
    token = encode_cursor(["secret-value"], fingerprint, secret=SECRET, encrypted=True)

    assert token.startswith("e1.")
    assert decode_cursor(token, fingerprint, secret=SECRET, encrypted=True).values == ("secret-value",)


def test_encrypted_token_ordering_mismatch_is_rejected() -> None:
    token = encode_cursor([1], FINGERPRINT, secret=SECRET, encrypted=True)
    other = order_fingerprint([("name", "asc", None)])

    with pytest.raises(InvalidCursorError, match="ordering mismatch"):
        decode_cursor(token, other, secret=SECRET, encrypted=True)


def test_encrypted_token_wrong_secret_is_rejected() -> None:
    token = encode_cursor([1], FINGERPRINT, secret=SECRET, encrypted=True)

    with pytest.raises(InvalidCursorError, match="signature mismatch"):
        decode_cursor(token, FINGERPRINT, secret=b"wrong-secret", encrypted=True)


@pytest.mark.parametrize(
    "bad_token",
    [
        "e2.AAAAAAAAAAAAAAAA.AAAAAAAAAAAAAAAA",
        "e1.AA.AAAAAAAAAAAAAAAA",
        f"e1.{'A' * 27}.AAAAAAAAAAAAAAAA",
    ],
)
def test_malformed_encrypted_tokens_are_rejected(bad_token: str) -> None:
    with pytest.raises(InvalidCursorError, match="malformed"):
        decode_cursor(bad_token, FINGERPRINT, secret=SECRET, encrypted=True)


def test_encrypted_tokens_require_cryptography_extra(monkeypatch: pytest.MonkeyPatch) -> None:
    token = encode_cursor([1], FINGERPRINT, secret=SECRET, encrypted=True)
    monkeypatch.setattr("advanced_alchemy.filters._cursor.CRYPTOGRAPHY_INSTALLED", False)

    with pytest.raises(MissingDependencyError, match="cryptography"):
        encode_cursor([1], FINGERPRINT, secret=SECRET, encrypted=True)
    with pytest.raises(MissingDependencyError, match="cryptography"):
        decode_cursor(token, FINGERPRINT, secret=SECRET, encrypted=True)

    signed = encode_cursor([1], FINGERPRINT, secret=SECRET)
    assert decode_cursor(signed, FINGERPRINT, secret=SECRET).values == (1,)


def test_signed_tokens_use_derived_key_rather_than_raw_secret() -> None:
    token = encode_cursor([7], FINGERPRINT, secret=SECRET)
    body, _ = token.split(".")
    raw_sig = (
        base64.urlsafe_b64encode(hmac.new(SECRET, body.encode("ascii"), hashlib.sha256).digest())
        .decode("ascii")
        .rstrip("=")
    )

    with pytest.raises(InvalidCursorError, match="signature mismatch"):
        decode_cursor(f"{body}.{raw_sig}", FINGERPRINT, secret=SECRET)


@pytest.mark.parametrize(
    ("issue_encrypted", "decode_secret", "decode_encrypted", "message"),
    [
        (True, SECRET, False, "unexpected encrypted token"),
        (True, None, False, "missing secret"),
        (False, SECRET, True, "encryption required"),
    ],
)
def test_encryption_mode_mismatch_is_rejected(
    issue_encrypted: bool, decode_secret: "bytes | None", decode_encrypted: bool, message: str
) -> None:
    token = encode_cursor([1], FINGERPRINT, secret=SECRET, encrypted=issue_encrypted)

    with pytest.raises(InvalidCursorError, match=message):
        decode_cursor(token, FINGERPRINT, secret=decode_secret, encrypted=decode_encrypted)


def test_tampered_encrypted_token_is_rejected() -> None:
    prefix, nonce, sealed = encode_cursor([1], FINGERPRINT, secret=SECRET, encrypted=True).split(".")
    tampered = f"{prefix}.{nonce}.{('A' if sealed[0] != 'A' else 'B') + sealed[1:]}"

    with pytest.raises(InvalidCursorError, match="signature mismatch"):
        decode_cursor(tampered, FINGERPRINT, secret=SECRET, encrypted=True)


def test_error_messages_never_echo_the_token() -> None:
    token = encode_cursor(["sensitive"], FINGERPRINT)

    with pytest.raises(InvalidCursorError) as exc_info:
        decode_cursor(token, "0" * 16)

    assert token not in str(exc_info.value)
    assert "sensitive" not in str(exc_info.value)


def test_unsupported_value_type_names_the_registration_hook() -> None:
    with pytest.raises(ImproperConfigurationError, match="register_cursor_type"):
        encode_cursor([object()], FINGERPRINT)


@pytest.mark.parametrize(
    ("kwargs", "error"),
    [
        ({"secret": b""}, ValueError),
        ({"encrypted": True}, ValueError),
        ({"ttl": 0}, ValueError),
        ({"ttl": float("inf")}, ValueError),
        ({"ttl": True}, TypeError),
        ({"ttl": "60"}, TypeError),
    ],
)
def test_invalid_codec_configuration_raises(kwargs: "dict[str, Any]", error: "type[Exception]") -> None:
    with pytest.raises(error):
        encode_cursor([1], FINGERPRINT, **kwargs)


class Money:
    def __init__(self, cents: int) -> None:
        self.cents = cents

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Money) and other.cents == self.cents

    def __hash__(self) -> int:
        return hash(self.cents)


def test_registered_custom_type_round_trips() -> None:
    register_cursor_type(Money, "money_test", lambda value: str(value.cents), lambda text: Money(int(text)))

    assert decode_cursor(encode_cursor([Money(250)], FINGERPRINT), FINGERPRINT).values == (Money(250),)
    with pytest.raises(ValueError, match="already registered"):
        register_cursor_type(Money, "money_other", str, str)


@pytest.mark.parametrize(
    ("value_type", "tag"),
    [(int, "int2"), (bool, "bool2"), (Color, "color"), (Decimal, "dec2"), (bytearray, "i"), (bytearray, "Bad Tag")],
)
def test_reserved_or_invalid_registrations_are_rejected(value_type: type, tag: str) -> None:
    with pytest.raises(ValueError, match="invalid or already registered"):
        register_cursor_type(value_type, tag, str, str)


def test_invalid_cursor_error_is_repository_and_value_error() -> None:
    assert issubclass(InvalidCursorError, RepositoryError)
    assert issubclass(InvalidCursorError, ValueError)
