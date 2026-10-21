"""Unit tests for the encrypted column types and their optional-dependency facade."""

from typing import Union

import pytest
from cryptography.fernet import InvalidToken
from sqlalchemy import column, literal
from sqlalchemy.dialects import sqlite

from advanced_alchemy.config.asyncio import SQLAlchemyAsyncConfig
from advanced_alchemy.config.sync import SQLAlchemySyncConfig
from advanced_alchemy.exceptions import ImproperConfigurationError, MissingDependencyError
from advanced_alchemy.types.encrypted_string import (
    DEFAULT_ENCRYPTION_KEY_ENV,
    EncryptedString,
    EncryptedText,
    FernetBackend,
    PGCryptoBackend,
    get_default_encryption_key,
    set_default_encryption_key,
)


@pytest.fixture(autouse=True)
def _reset_default_encryption_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure the process-wide encryption key and env var start clean in every test."""
    monkeypatch.delenv(DEFAULT_ENCRYPTION_KEY_ENV, raising=False)
    set_default_encryption_key(None)


def test_cryptography_installed_flag_is_bool() -> None:
    from advanced_alchemy.typing import CRYPTOGRAPHY_INSTALLED

    assert isinstance(CRYPTOGRAPHY_INSTALLED, bool)


def test_fernet_backend_requires_cryptography(monkeypatch: pytest.MonkeyPatch) -> None:
    from advanced_alchemy.types import encrypted_string

    monkeypatch.setattr(encrypted_string, "CRYPTOGRAPHY_INSTALLED", False)
    with pytest.raises(MissingDependencyError):
        encrypted_string.FernetBackend()


def test_zero_arg_instantiation_without_key_or_env(recwarn: pytest.WarningsRecorder) -> None:
    """Zero-argument column declarations succeed at import/model definition time without warnings."""
    enc_str = EncryptedString()
    enc_text = EncryptedText()
    assert enc_str.key is None
    assert enc_text.key is None
    assert enc_str.key_env == DEFAULT_ENCRYPTION_KEY_ENV
    assert not [w for w in recwarn.list if issubclass(w.category, DeprecationWarning)]


def test_missing_key_raises_improper_configuration_at_runtime() -> None:
    """Binding or reading a value without any configured key raises ImproperConfigurationError."""
    enc = EncryptedString()
    dialect = sqlite.dialect()
    with pytest.raises(ImproperConfigurationError, match="requires an encryption key"):
        enc.process_bind_param("secret-value", dialect)


def test_key_resolution_from_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    """Zero-arg EncryptedString resolves key from ADVANCED_ALCHEMY_ENCRYPTION_KEY."""
    monkeypatch.setenv(DEFAULT_ENCRYPTION_KEY_ENV, "env-secret-key")
    enc = EncryptedString()
    dialect = sqlite.dialect()
    token = enc.process_bind_param("hello", dialect)
    assert token is not None
    assert enc.process_result_value(token, dialect) == "hello"


def test_key_resolution_from_custom_key_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Custom key_env resolves from the specified environment variable."""
    monkeypatch.setenv("CUSTOM_TOTP_KEY", "custom-env-secret")
    enc = EncryptedString(key_env="CUSTOM_TOTP_KEY")
    dialect = sqlite.dialect()
    token = enc.process_bind_param("custom-payload", dialect)
    assert token is not None
    assert enc.process_result_value(token, dialect) == "custom-payload"


def test_key_resolution_from_default_encryption_key() -> None:
    """set_default_encryption_key configures the fallback key for zero-arg columns."""
    set_default_encryption_key("global-config-key")
    assert get_default_encryption_key() == "global-config-key"
    enc = EncryptedString()
    dialect = sqlite.dialect()
    token = enc.process_bind_param("configured-payload", dialect)
    assert token is not None
    assert enc.process_result_value(token, dialect) == "configured-payload"


def test_key_resolution_from_sqlalchemy_configs() -> None:
    """SQLAlchemyAsyncConfig and SQLAlchemySyncConfig register encryption_key on init."""
    SQLAlchemyAsyncConfig(connection_string="sqlite+aiosqlite://", encryption_key="async-cfg-key")
    assert get_default_encryption_key() == "async-cfg-key"
    enc = EncryptedString()
    dialect = sqlite.dialect()
    token = enc.process_bind_param("async-val", dialect)
    assert enc.process_result_value(token, dialect) == "async-val"

    SQLAlchemySyncConfig(connection_string="sqlite://", encryption_key="sync-cfg-key")
    assert get_default_encryption_key() == "sync-cfg-key"


def test_explicit_key_precedence_over_default_and_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Explicit column key takes precedence over default config key and environment variable."""
    monkeypatch.setenv(DEFAULT_ENCRYPTION_KEY_ENV, "env-key")
    set_default_encryption_key("default-key")
    explicit_col = EncryptedString(key="explicit-key")
    other_explicit = EncryptedString(key="explicit-key")
    default_col = EncryptedString()
    dialect = sqlite.dialect()

    token = explicit_col.process_bind_param("secret", dialect)
    assert other_explicit.process_result_value(token, dialect) == "secret"
    with pytest.raises(InvalidToken):
        default_col.process_result_value(token, dialect)


def test_subclass_repr_renders_own_name_and_never_leaks_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    """EncryptedString and EncryptedText render their own class name and never leak secret keys."""
    monkeypatch.setenv(DEFAULT_ENCRYPTION_KEY_ENV, "env-top-secret")
    set_default_encryption_key("config-top-secret")
    assert repr(EncryptedText(key="literal-top-secret")) == "EncryptedText(backend=FernetBackend, length=None)"
    assert repr(EncryptedString(key="literal-top-secret")) == "EncryptedString(backend=FernetBackend, length=None)"
    assert repr(EncryptedString()) == "EncryptedString(backend=FernetBackend, length=None)"
    assert "literal-top-secret" not in repr(EncryptedString(key="literal-top-secret"))
    assert "config-top-secret" not in repr(EncryptedString())
    assert "env-top-secret" not in repr(EncryptedString())


def test_fernet_backend_is_client_side() -> None:
    """Fernet encrypts in Python, so it advertises no SQL-side expression."""
    backend = FernetBackend()
    backend.mount_vault("k")
    assert backend.bind_expression("v") is None
    assert backend.column_expression("c") is None


def test_pgcrypto_backend_wraps_sql() -> None:
    """PGCrypto runs server-side, wrapping binds/reads in pgcrypto functions."""
    import advanced_alchemy.types as aa_types

    assert "PGCryptoBackend" in aa_types.__all__

    backend = PGCryptoBackend()
    backend.mount_vault("k")
    bind_expr = backend.bind_expression(literal("secret"))
    column_expr = backend.column_expression(column("c"))
    assert bind_expr is not None
    assert column_expr is not None
    bind_sql = str(bind_expr)
    column_sql = str(column_expr)
    assert "pgp_sym_encrypt" in bind_sql
    assert "armor" in bind_sql
    assert "pgp_sym_decrypt" in column_sql
    assert "dearmor" in column_sql


def test_pgcrypto_different_keys_distinct_cache_key() -> None:
    """Columns with different keys must not collide in the statement cache."""
    a = EncryptedString(key="key-a", backend=PGCryptoBackend)
    b = EncryptedString(key="key-b", backend=PGCryptoBackend)
    assert a._static_cache_key != b._static_cache_key


def test_fernet_ciphertext_backward_compat() -> None:
    """A token written by an earlier release must still decrypt with the same key.

    Locks the SHA256 key derivation and Fernet format so future changes cannot
    silently render existing rows undecryptable.
    """
    golden_token = "gAAAAABqHELupN0FK6NTQxUQD-7kN1TOxrgP9pVU_NaaW31Y7wljqqG16DHn9ZXxNb2Jqt2UtMqr-Bcjegh84-E6VHkDq1F-Ic8TXqTn2q_i4u-vv_0qEl8="
    enc = EncryptedString(key="golden-key")
    enc.mount_vault()
    assert enc.backend.decrypt(golden_token) == "golden-plaintext"


def test_static_key_caches_vault(monkeypatch: pytest.MonkeyPatch) -> None:
    enc = EncryptedString(key="static-key")
    calls = {"n": 0}
    original = enc.backend.mount_vault

    def counting(key: Union[str, bytes]) -> None:
        calls["n"] += 1
        original(key)

    monkeypatch.setattr(enc.backend, "mount_vault", counting)
    enc.mount_vault()
    enc.mount_vault()
    assert calls["n"] == 1


def test_callable_key_caches_until_key_rotates(monkeypatch: pytest.MonkeyPatch) -> None:
    """Callable key only remounts the backend when the returned key value changes."""
    state = {"key": "rotation-v1"}
    enc = EncryptedString(key=lambda: state["key"])
    calls = {"n": 0}
    original = enc.backend.mount_vault

    def counting(key: Union[str, bytes]) -> None:
        calls["n"] += 1
        original(key)

    monkeypatch.setattr(enc.backend, "mount_vault", counting)
    dialect = sqlite.dialect()
    token_v1 = enc.process_bind_param("payload-1", dialect)
    assert enc.process_result_value(token_v1, dialect) == "payload-1"
    assert calls["n"] == 1

    state["key"] = "rotation-v2"
    token_v2 = enc.process_bind_param("payload-2", dialect)
    assert enc.process_result_value(token_v2, dialect) == "payload-2"
    assert calls["n"] == 2
