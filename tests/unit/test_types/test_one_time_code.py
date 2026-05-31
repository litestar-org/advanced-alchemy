"""Unit tests for the OneTimeCode column type and its lifecycle."""

import pytest

from advanced_alchemy.typing import ARGON2_INSTALLED


def test_generate_one_time_code_defaults() -> None:
    from advanced_alchemy.types import generate_one_time_code

    code = generate_one_time_code()
    assert len(code) == 6
    assert code.isdigit()


def test_generate_one_time_code_custom() -> None:
    from advanced_alchemy.types import generate_one_time_code

    code = generate_one_time_code(length=10, digits_only=False)
    assert len(code) == 10
    assert all(c.isdigit() or c.isupper() for c in code)


@pytest.mark.skipif(not ARGON2_INSTALLED, reason="argon2-cffi not installed")
def test_one_time_code_type_repr() -> None:
    from advanced_alchemy.types import OneTimeCode
    from advanced_alchemy.types.password_hash.argon2 import Argon2Hasher

    code_type = OneTimeCode(backend=Argon2Hasher(), ttl_seconds=600, max_attempts=3)
    assert repr(code_type) == "OneTimeCode(backend=sa.Argon2Hasher(), ttl_seconds=600, max_attempts=3)"


@pytest.mark.skipif(not ARGON2_INSTALLED, reason="argon2-cffi not installed")
def test_one_time_code_round_trip_via_processors() -> None:
    """process_bind_param hashes a new code; process_result_value returns a verifier."""
    from advanced_alchemy.types import OneTimeCode
    from advanced_alchemy.types.password_hash.argon2 import Argon2Hasher
    from advanced_alchemy.types.password_hash.one_time_code import HashedOneTimeCode

    code_type = OneTimeCode(backend=Argon2Hasher())
    stored = code_type.process_bind_param("123456", dialect=None)
    assert stored is not None
    assert stored["hash"] != "123456"
    assert stored["used_at"] is None
    assert stored["attempts"] == 0

    wrapper = code_type.process_result_value(stored, dialect=None)
    assert isinstance(wrapper, HashedOneTimeCode)
    assert wrapper.verify("123456") is True
    assert wrapper.verify("000000") is False


@pytest.mark.skipif(not ARGON2_INSTALLED, reason="argon2-cffi not installed")
def test_single_use_redeem() -> None:
    from advanced_alchemy.types.password_hash.argon2 import Argon2Hasher
    from advanced_alchemy.types.password_hash.one_time_code import HashedOneTimeCode

    backend = Argon2Hasher()
    otp = HashedOneTimeCode(backend.hash("123456"), backend)
    ok, consumed = otp.redeem("123456")
    assert ok is True
    assert consumed.is_used is True
    assert consumed.verify("123456") is False


@pytest.mark.skipif(not ARGON2_INSTALLED, reason="argon2-cffi not installed")
def test_expiry() -> None:
    from advanced_alchemy.types.password_hash.argon2 import Argon2Hasher
    from advanced_alchemy.types.password_hash.one_time_code import HashedOneTimeCode

    backend = Argon2Hasher()
    expired = HashedOneTimeCode(backend.hash("123456"), backend, expires_at=0.0)
    assert expired.is_expired is True
    assert expired.verify("123456") is False


@pytest.mark.skipif(not ARGON2_INSTALLED, reason="argon2-cffi not installed")
def test_attempt_lockout() -> None:
    from advanced_alchemy.types.password_hash.argon2 import Argon2Hasher
    from advanced_alchemy.types.password_hash.one_time_code import HashedOneTimeCode

    backend = Argon2Hasher()
    otp = HashedOneTimeCode(backend.hash("123456"), backend, max_attempts=2)
    ok, otp = otp.redeem("000000")
    assert ok is False
    assert otp.attempts == 1
    ok, otp = otp.redeem("000000")
    assert otp.attempts == 2
    assert otp.is_locked is True
    assert otp.verify("123456") is False
