"""Unit tests for the password-hash backends: facade flags, guards, and rehash-on-verify."""

import pytest

from advanced_alchemy.typing import ARGON2_INSTALLED, PASSLIB_INSTALLED, PWDLIB_INSTALLED


def test_password_hash_installed_flags_are_bool() -> None:
    assert isinstance(ARGON2_INSTALLED, bool)
    assert isinstance(PASSLIB_INSTALLED, bool)
    assert isinstance(PWDLIB_INSTALLED, bool)


def test_passlib_requires_passlib(monkeypatch: pytest.MonkeyPatch) -> None:
    from advanced_alchemy.exceptions import MissingDependencyError
    from advanced_alchemy.types.password_hash import passlib as passlib_module

    monkeypatch.setattr(passlib_module, "PASSLIB_INSTALLED", False)
    with pytest.raises(MissingDependencyError):
        passlib_module.PasslibHasher(context=None)  # type: ignore[arg-type]


def test_pwdlib_requires_pwdlib(monkeypatch: pytest.MonkeyPatch) -> None:
    from advanced_alchemy.exceptions import MissingDependencyError
    from advanced_alchemy.types.password_hash import pwdlib as pwdlib_module

    monkeypatch.setattr(pwdlib_module, "PWDLIB_INSTALLED", False)
    with pytest.raises(MissingDependencyError):
        pwdlib_module.PwdlibHasher(hasher=None)  # type: ignore[arg-type]


def test_argon2_import_guarded() -> None:
    """argon2-cffi is present in CI; the import-time guard follows the obstore pattern."""
    from advanced_alchemy.types.password_hash.argon2 import Argon2Hasher

    assert Argon2Hasher is not None


@pytest.mark.skipif(not ARGON2_INSTALLED, reason="argon2-cffi not installed")
def test_argon2_needs_rehash_false_for_current() -> None:
    from advanced_alchemy.types.password_hash.argon2 import Argon2Hasher

    backend = Argon2Hasher()
    assert backend.needs_rehash(backend.hash("pw")) is False


@pytest.mark.skipif(not ARGON2_INSTALLED, reason="argon2-cffi not installed")
def test_argon2_needs_rehash_true_for_weaker() -> None:
    from advanced_alchemy.types.password_hash.argon2 import Argon2Hasher

    weak_hash = Argon2Hasher(time_cost=1).hash("pw")
    assert Argon2Hasher(time_cost=10).needs_rehash(weak_hash) is True


@pytest.mark.skipif(not ARGON2_INSTALLED, reason="argon2-cffi not installed")
def test_argon2_needs_rehash_false_for_foreign_hash() -> None:
    from advanced_alchemy.types.password_hash.argon2 import Argon2Hasher

    assert Argon2Hasher().needs_rehash("not-a-hash") is False


@pytest.mark.skipif(not PASSLIB_INSTALLED, reason="passlib not installed")
def test_passlib_needs_rehash() -> None:
    from passlib.context import CryptContext

    from advanced_alchemy.types.password_hash.passlib import PasslibHasher

    weak = PasslibHasher(context=CryptContext(schemes=["sha256_crypt"], sha256_crypt__rounds=1000))
    weak_hash = weak.hash("pw")
    strong = PasslibHasher(context=CryptContext(schemes=["sha256_crypt"], sha256_crypt__rounds=100000))
    assert strong.needs_rehash(weak_hash) is True
    assert weak.needs_rehash(weak_hash) is False
    assert strong.needs_rehash("not-a-hash") is False


@pytest.mark.skipif(not PWDLIB_INSTALLED, reason="pwdlib not installed")
def test_pwdlib_needs_rehash() -> None:
    from pwdlib.hashers.argon2 import Argon2Hasher as PwdlibArgon2Hasher

    from advanced_alchemy.types.password_hash.pwdlib import PwdlibHasher

    weak_hash = PwdlibHasher(hasher=PwdlibArgon2Hasher(time_cost=1)).hash("pw")
    strong = PwdlibHasher(hasher=PwdlibArgon2Hasher(time_cost=10))
    assert strong.needs_rehash(weak_hash) is True
    assert strong.needs_rehash("not-a-hash") is False


@pytest.mark.skipif(not ARGON2_INSTALLED, reason="argon2-cffi not installed")
def test_password_hash_default_length_is_255() -> None:
    from advanced_alchemy.types.password_hash.argon2 import Argon2Hasher
    from advanced_alchemy.types.password_hash.base import PasswordHash

    assert PasswordHash(backend=Argon2Hasher()).length == 255


@pytest.mark.skipif(not ARGON2_INSTALLED, reason="argon2-cffi not installed")
def test_argon2_verify_returns_false_for_foreign_hash() -> None:
    from advanced_alchemy.types.password_hash.argon2 import Argon2Hasher

    assert Argon2Hasher().verify("pw", "not-a-valid-hash") is False


@pytest.mark.skipif(not ARGON2_INSTALLED, reason="argon2-cffi not installed")
def test_verify_and_update_wrong_password() -> None:
    from advanced_alchemy.types.password_hash.argon2 import Argon2Hasher
    from advanced_alchemy.types.password_hash.base import HashedPassword

    backend = Argon2Hasher()
    hp = HashedPassword(backend.hash("right"), backend)
    assert hp.verify_and_update("wrong") == (False, None)


@pytest.mark.skipif(not ARGON2_INSTALLED, reason="argon2-cffi not installed")
def test_verify_and_update_ok_no_rehash() -> None:
    from advanced_alchemy.types.password_hash.argon2 import Argon2Hasher
    from advanced_alchemy.types.password_hash.base import HashedPassword

    backend = Argon2Hasher()
    hp = HashedPassword(backend.hash("pw"), backend)
    ok, new = hp.verify_and_update("pw")
    assert ok is True
    assert new is None


@pytest.mark.skipif(not ARGON2_INSTALLED, reason="argon2-cffi not installed")
def test_verify_and_update_ok_with_rehash() -> None:
    from advanced_alchemy.types.password_hash.argon2 import Argon2Hasher
    from advanced_alchemy.types.password_hash.base import HashedPassword

    old_hash = Argon2Hasher(time_cost=1).hash("pw")
    strong = Argon2Hasher(time_cost=10)
    hp = HashedPassword(old_hash, strong)
    ok, new = hp.verify_and_update("pw")
    assert ok is True
    assert new is not None
    assert new != old_hash
    assert strong.verify("pw", new) is True
