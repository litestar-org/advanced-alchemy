"""Integration round-trip tests for the encrypted column types."""

from typing import Optional, cast

import pytest
from sqlalchemy import Engine, String, Table, text
from sqlalchemy.orm import Mapped, Session, mapped_column, sessionmaker

from advanced_alchemy.base import BigIntBase
from advanced_alchemy.types import EncryptedString
from advanced_alchemy.types.encrypted_string import FernetBackend, PGCryptoBackend

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


def _should_skip(engine: Engine) -> Optional[str]:
    name = engine.dialect.name
    if name == "mock":
        return "Mock engine doesn't support auto-generated primary keys"
    if name.startswith("spanner"):
        return "Spanner doesn't support direct UNIQUE constraints"
    if name.startswith("cockroach"):
        return "CockroachDB doesn't support BigInt primary keys"
    return None


def test_fernet_round_trip(engine: Engine) -> None:
    skip_reason = _should_skip(engine)
    if skip_reason is not None:
        pytest.skip(skip_reason)

    FernetModel.metadata.create_all(engine, tables=[cast("Table", FernetModel.__table__)])
    session_factory: sessionmaker[Session] = sessionmaker(engine, expire_on_commit=False)
    try:
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
    finally:
        FernetModel.metadata.drop_all(engine, tables=[cast("Table", FernetModel.__table__)])


def test_pgcrypto_round_trip(engine: Engine) -> None:
    if engine.dialect.name != "postgresql":
        pytest.skip("pgcrypto requires a real PostgreSQL backend")

    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))

    PGCryptoModel.metadata.create_all(engine, tables=[cast("Table", PGCryptoModel.__table__)])
    session_factory: sessionmaker[Session] = sessionmaker(engine, expire_on_commit=False)
    try:
        with session_factory() as db_session:
            obj = PGCryptoModel(name="pgcrypto", secret="pg-secret-value")
            db_session.add(obj)
            db_session.commit()
            db_session.refresh(obj)
            assert obj.secret == "pg-secret-value"
    finally:
        PGCryptoModel.metadata.drop_all(engine, tables=[cast("Table", PGCryptoModel.__table__)])
