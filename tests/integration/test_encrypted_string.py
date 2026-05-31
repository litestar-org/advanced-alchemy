"""Integration round-trip tests for the encrypted column types."""

from typing import Any, Optional, cast

import pytest
from sqlalchemy import Engine, String, text
from sqlalchemy.orm import Mapped, Session, mapped_column, sessionmaker

from advanced_alchemy.base import BigIntBase
from advanced_alchemy.types import EncryptedString
from advanced_alchemy.types.encrypted_string import FernetBackend, PGCryptoBackend
from advanced_alchemy.typing import PYOTP_INSTALLED

pytestmark = [
    pytest.mark.integration,
    pytest.mark.xdist_group("encrypted_string"),
]


class FernetModel(BigIntBase):
    __tablename__ = "test_encrypted_fernet"
    name: Mapped[str] = mapped_column(String(50))
    secret: Mapped[Optional[str]] = mapped_column(
        EncryptedString(key="fernet-secret", backend=FernetBackend), nullable=True
    )

    __table_args__ = {"info": {"allow_eager": True}}


class PGCryptoModel(BigIntBase):
    __tablename__ = "test_encrypted_pgcrypto"
    name: Mapped[str] = mapped_column(String(50))
    secret: Mapped[Optional[str]] = mapped_column(
        EncryptedString(key="pgcrypto-secret", backend=PGCryptoBackend), nullable=True
    )

    __table_args__ = {"info": {"allow_eager": True}}


if PYOTP_INSTALLED:
    from advanced_alchemy.types import TOTPSecret

    class TOTPModel(BigIntBase):
        __tablename__ = "test_encrypted_totp"
        name: Mapped[str] = mapped_column(String(50))
        seed: Mapped[Optional[str]] = mapped_column(  # type: ignore[assignment]
            TOTPSecret(key="totp-key", issuer="ACME"), nullable=True
        )

        __table_args__ = {"info": {"allow_eager": True}}


@pytest.fixture()
def encrypted_test_tables(engine: Engine) -> None:
    """Create the encrypted-type test tables for sync engines."""
    name = getattr(engine.dialect, "name", "")
    if name != "mock" and not name.startswith("spanner"):
        FernetModel.metadata.create_all(engine)


def _should_skip(engine: Engine) -> Optional[str]:
    name = engine.dialect.name
    if name == "mock":
        return "Mock engine doesn't support auto-generated primary keys"
    if name.startswith("spanner"):
        return "Spanner doesn't support direct UNIQUE constraints"
    if name.startswith("cockroach"):
        return "CockroachDB doesn't support BigInt primary keys"
    return None


def test_fernet_round_trip(engine: Engine, encrypted_test_tables: None) -> None:
    skip_reason = _should_skip(engine)
    if skip_reason is not None:
        pytest.skip(skip_reason)

    session_factory: sessionmaker[Session] = sessionmaker(engine, expire_on_commit=False)
    with session_factory() as db_session:
        obj = FernetModel(name="fernet", secret="top-secret-value")
        db_session.add(obj)
        db_session.commit()
        db_session.refresh(obj)
        assert obj.secret == "top-secret-value"

        obj.secret = None
        db_session.commit()
        db_session.refresh(obj)
        assert obj.secret is None


def test_pgcrypto_round_trip(engine: Engine, encrypted_test_tables: None) -> None:
    if engine.dialect.name != "postgresql":
        pytest.skip("pgcrypto requires a real PostgreSQL backend")

    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))

    session_factory: sessionmaker[Session] = sessionmaker(engine, expire_on_commit=False)
    with session_factory() as db_session:
        obj = PGCryptoModel(name="pgcrypto", secret="pg-secret-value")
        db_session.add(obj)
        db_session.commit()
        db_session.refresh(obj)
        assert obj.secret == "pg-secret-value"


@pytest.mark.parametrize("model", [FernetModel, PGCryptoModel])
def test_backends_are_interchangeable(engine: Engine, model: "type[BigIntBase]", encrypted_test_tables: None) -> None:
    """Fernet and PGCrypto must be drop-in interchangeable: same API, same external behavior.

    Run on PostgreSQL where both backends work (pgcrypto is PostgreSQL-only) so the two are
    exercised through identical assertions.
    """
    if engine.dialect.name != "postgresql":
        pytest.skip("comparing both backends on PostgreSQL (pgcrypto is PostgreSQL-only)")

    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))

    session_factory: sessionmaker[Session] = sessionmaker(engine, expire_on_commit=False)
    with session_factory() as db_session:
        for value in ["plain-value", "ünîcödé 🔐 secret", "", None]:
            obj = cast("Any", model(name="x", secret=value))
            db_session.add(obj)
            db_session.commit()
            db_session.refresh(obj)
            assert obj.secret == value

            raw = db_session.execute(
                text(f"SELECT secret FROM {model.__tablename__} WHERE id = :id"),
                {"id": obj.id},
            ).scalar_one()
            if value is None:
                assert raw is None
            else:
                assert raw != value


@pytest.mark.skipif(not PYOTP_INSTALLED, reason="pyotp not installed")
def test_totp_secret_round_trip(engine: Engine, encrypted_test_tables: None) -> None:
    import pyotp

    from advanced_alchemy.types.totp import TOTPProvider

    skip_reason = _should_skip(engine)
    if skip_reason is not None:
        pytest.skip(skip_reason)

    secret = pyotp.random_base32()
    session_factory: sessionmaker[Session] = sessionmaker(engine, expire_on_commit=False)
    with session_factory() as db_session:
        obj = TOTPModel(name="totp", seed=secret)
        db_session.add(obj)
        db_session.commit()
        row_id = obj.id
        db_session.refresh(obj)

        provider = cast("object", obj.seed)
        assert isinstance(provider, TOTPProvider)
        assert provider.secret == secret
        assert provider.verify(pyotp.TOTP(secret).now()) is True

        stored = db_session.execute(
            text("SELECT seed FROM test_encrypted_totp WHERE id = :id"), {"id": row_id}
        ).scalar_one()
        assert stored != secret
