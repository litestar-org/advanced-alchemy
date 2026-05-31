"""Unit tests for the OneTimeCode column type."""

import pytest

from advanced_alchemy.typing import ARGON2_INSTALLED


@pytest.mark.skipif(not ARGON2_INSTALLED, reason="argon2-cffi not installed")
def test_one_time_code_hashes_and_verifies() -> None:
    from advanced_alchemy.types import HashedOneTimeCode
    from advanced_alchemy.types.password_hash.argon2 import Argon2Hasher

    backend = Argon2Hasher()
    hashed = backend.hash("123456")
    wrapper = HashedOneTimeCode(hashed, backend)
    assert wrapper.verify("123456") is True
    assert wrapper.verify("000000") is False
    assert hashed != "123456"


@pytest.mark.skipif(not ARGON2_INSTALLED, reason="argon2-cffi not installed")
def test_one_time_code_type_defaults() -> None:
    from advanced_alchemy.types import OneTimeCode
    from advanced_alchemy.types.password_hash.argon2 import Argon2Hasher

    code_type = OneTimeCode(backend=Argon2Hasher())
    assert code_type.length == 255


@pytest.mark.skipif(not ARGON2_INSTALLED, reason="argon2-cffi not installed")
def test_one_time_code_repr_renders_own_name() -> None:
    """OneTimeCode must repr as OneTimeCode, not PasswordHash, for Alembic fidelity."""
    from advanced_alchemy.types import OneTimeCode, PasswordHash
    from advanced_alchemy.types.password_hash.argon2 import Argon2Hasher

    assert repr(OneTimeCode(backend=Argon2Hasher())) == "OneTimeCode(backend=sa.Argon2Hasher(), length=255)"
    assert repr(PasswordHash(backend=Argon2Hasher())) == "PasswordHash(backend=sa.Argon2Hasher(), length=255)"
