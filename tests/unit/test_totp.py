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


@pytest.mark.skipif(not PYOTP_INSTALLED, reason="pyotp not installed")
def test_totp_secret_requires_explicit_key() -> None:
    """The new type has no deprecated random default; key is required."""
    from advanced_alchemy.types import TOTPSecret

    with pytest.raises(TypeError):
        TOTPSecret()  # type: ignore[call-arg]


@pytest.mark.skipif(not PYOTP_INSTALLED, reason="pyotp not installed")
def test_totp_secret_repr_includes_params() -> None:
    """The repr must name TOTPSecret and carry its TOTP params so Alembic reconstructs faithfully."""
    from advanced_alchemy.types import TOTPSecret

    rendered = repr(TOTPSecret(key="k", issuer="ACME", digits=8, interval=60))
    assert rendered == (
        "TOTPSecret(key='k', backend=FernetBackend, digits=8, interval=60, digest=None, issuer='ACME', length=None)"
    )


@pytest.mark.skipif(not PYOTP_INSTALLED, reason="pyotp not installed")
def test_totp_secret_distinct_params_distinct_cache_key() -> None:
    from advanced_alchemy.types import TOTPSecret

    a = TOTPSecret(key="k", digits=6)
    b = TOTPSecret(key="k", digits=8)
    assert a._static_cache_key != b._static_cache_key
