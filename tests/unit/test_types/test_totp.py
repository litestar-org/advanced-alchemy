"""Unit tests for the TOTPSecret column type and TOTPProvider wrapper."""

import pytest

from advanced_alchemy.typing import PYOTP_INSTALLED


def test_pyotp_installed_flag_is_bool() -> None:
    assert isinstance(PYOTP_INSTALLED, bool)


@pytest.mark.skipif(not PYOTP_INSTALLED, reason="pyotp not installed")
def test_generate_and_roundtrip_via_provider() -> None:
    import pyotp

    from advanced_alchemy.types import TOTPProvider, generate_totp_secret

    secret = generate_totp_secret()
    provider = TOTPProvider(secret, digits=6, interval=30, digest=None, issuer="ACME")
    code = pyotp.TOTP(secret).now()
    assert provider.verify(code) is True
    assert provider.verify("000000", valid_window=0) in (True, False)
    assert provider.secret == secret
    uri = provider.provisioning_uri(name="alice@example.com")
    assert uri.startswith("otpauth://totp/")
    assert "issuer=ACME" in uri


def test_generate_totp_secret_requires_pyotp(monkeypatch: pytest.MonkeyPatch) -> None:
    from advanced_alchemy.exceptions import MissingDependencyError
    from advanced_alchemy.types import totp

    monkeypatch.setattr(totp, "PYOTP_INSTALLED", False)
    with pytest.raises(MissingDependencyError):
        totp.generate_totp_secret()


def test_totp_secret_requires_pyotp(monkeypatch: pytest.MonkeyPatch) -> None:
    from advanced_alchemy.exceptions import MissingDependencyError
    from advanced_alchemy.types import totp

    monkeypatch.setattr(totp, "PYOTP_INSTALLED", False)
    with pytest.raises(MissingDependencyError):
        totp.TOTPSecret(key="k")


def test_totp_provider_requires_pyotp(monkeypatch: pytest.MonkeyPatch) -> None:
    from advanced_alchemy.exceptions import MissingDependencyError
    from advanced_alchemy.types import totp

    monkeypatch.setattr(totp, "PYOTP_INSTALLED", False)
    with pytest.raises(MissingDependencyError):
        totp.TOTPProvider("ABCDEFGH")


@pytest.mark.skipif(not PYOTP_INSTALLED, reason="pyotp not installed")
def test_totp_secret_zero_arg_and_lazy_key_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    """TOTPSecret supports zero-argument declaration and resolves its key lazily."""
    from sqlalchemy.dialects import sqlite

    from advanced_alchemy.exceptions import ImproperConfigurationError
    from advanced_alchemy.types import DEFAULT_ENCRYPTION_KEY_ENV, TOTPSecret, generate_totp_secret
    from advanced_alchemy.types.encrypted_string import set_default_encryption_key

    monkeypatch.delenv(DEFAULT_ENCRYPTION_KEY_ENV, raising=False)
    set_default_encryption_key(None)
    col = TOTPSecret(issuer="ACME")
    dialect = sqlite.dialect()
    with pytest.raises(ImproperConfigurationError):
        col.process_bind_param("JBSWY3DPEHPK3PXP", dialect)

    monkeypatch.setenv(DEFAULT_ENCRYPTION_KEY_ENV, "totp-env-key")
    secret = generate_totp_secret()
    encrypted = col.process_bind_param(secret, dialect)
    provider = col.process_result_value(encrypted, dialect)
    assert provider is not None
    assert provider.secret == secret


@pytest.mark.skipif(not PYOTP_INSTALLED, reason="pyotp not installed")
def test_totp_secret_repr_includes_params() -> None:
    """The repr must name TOTPSecret and carry its TOTP params without leaking secret keys."""
    from advanced_alchemy.types import TOTPSecret

    rendered = repr(TOTPSecret(key="k", issuer="ACME", digits=8, interval=60))
    assert rendered == (
        "TOTPSecret(backend=FernetBackend, digits=8, interval=60, digest=None, issuer='ACME', length=None)"
    )


@pytest.mark.skipif(not PYOTP_INSTALLED, reason="pyotp not installed")
def test_totp_secret_distinct_params_distinct_cache_key() -> None:
    from advanced_alchemy.types import TOTPSecret

    a = TOTPSecret(key="k", digits=6)
    b = TOTPSecret(key="k", digits=8)
    assert a._static_cache_key != b._static_cache_key
