# ruff: noqa: UP045
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Optional

import pytest
from passlib.context import CryptContext
from pwdlib.hashers.argon2 import Argon2Hasher as PwdlibArgon2Hasher
from sqlalchemy import String, create_engine
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import Mapped, Session, mapped_column, sessionmaker

from advanced_alchemy.base import BigIntBase
from advanced_alchemy.types import PasswordHash
from advanced_alchemy.types.password_hash.argon2 import Argon2Hasher
from advanced_alchemy.types.password_hash.base import HashedPassword
from advanced_alchemy.types.password_hash.passlib import PasslibHasher
from advanced_alchemy.types.password_hash.pwdlib import PwdlibHasher

if TYPE_CHECKING:
    from pytest import MonkeyPatch

pytestmark = [
    pytest.mark.integration,
]


# Define the User model using PasswordHash
class User(BigIntBase):
    __tablename__ = "test_user_password_hash"
    name: Mapped[str] = mapped_column(String(50))
    passlib_password: Mapped[Optional[str]] = mapped_column(
        PasswordHash(backend=PasslibHasher(context=CryptContext(schemes=["argon2"])))
    )
    argon2_password: Mapped[Optional[str]] = mapped_column(PasswordHash(backend=Argon2Hasher()))
    pwdlib_password: Mapped[Optional[str]] = mapped_column(
        PasswordHash(backend=PwdlibHasher(hasher=PwdlibArgon2Hasher()))
    )


@pytest.mark.xdist_group("sqlite")
def test_password_hash_sync_sqlite(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    """Test password hashing with Argon2 and Passlib backends using SQLite."""
    # Create engine and session
    engine = create_engine(f"sqlite:///{tmp_path}/test_password.db", echo=False)
    session_factory: sessionmaker[Session] = sessionmaker(engine, expire_on_commit=False)

    # Create tables
    with engine.begin() as conn:
        User.metadata.create_all(conn)

    # Test with session
    with session_factory() as db_session:
        # Create user with passlib password
        user1 = User(name="user1", passlib_password="password123")
        db_session.add(user1)
        db_session.flush()
        db_session.refresh(user1)

        # Verify password hash is created correctly
        assert isinstance(user1.passlib_password, HashedPassword)
        assert user1.passlib_password.hash_string.startswith("$argon2")  # type: ignore[unreachable]
        assert user1.passlib_password.verify("password123")
        assert not user1.passlib_password.verify("wrong_password")

        # Test non-string password inputs
        assert not user1.passlib_password.verify(123)  # type: ignore[arg-type]
        assert not user1.passlib_password.verify(123.45)  # type: ignore[arg-type]
        assert not user1.passlib_password.verify(True)  # type: ignore[arg-type]
        assert not user1.passlib_password.verify(None)  # type: ignore[arg-type]
        assert not user1.passlib_password.verify(["password123"])  # type: ignore[arg-type]
        assert not user1.passlib_password.verify({"password": "password123"})  # type: ignore[arg-type]

        # Create user with argon2 password
        user2 = User(name="user2", argon2_password="secret123")
        db_session.add(user2)
        db_session.flush()
        db_session.refresh(user2)

        # Verify password hash is created correctly
        assert isinstance(user2.argon2_password, HashedPassword)
        assert user2.argon2_password.hash_string.startswith("$argon2")
        assert user2.argon2_password.verify("secret123")
        assert not user2.argon2_password.verify("wrong_secret")

        # Test non-string password inputs with argon2
        assert not user2.argon2_password.verify(123)  # type: ignore[arg-type]
        assert not user2.argon2_password.verify(123.45)  # type: ignore[arg-type]
        assert not user2.argon2_password.verify(True)  # type: ignore[arg-type]
        assert not user2.argon2_password.verify(None)  # type: ignore[arg-type]
        assert not user2.argon2_password.verify(["secret123"])  # type: ignore[arg-type]
        assert not user2.argon2_password.verify({"password": "secret123"})  # type: ignore[arg-type]

        # Test updating password
        user2.argon2_password = "newsecret123"
        db_session.flush()
        db_session.refresh(user2)
        assert isinstance(user2.argon2_password, HashedPassword)
        assert user2.argon2_password.verify("newsecret123")
        assert not user2.argon2_password.verify("secret123")

        # Test setting password to None
        user2.argon2_password = None
        db_session.flush()
        db_session.refresh(user2)
        assert user2.argon2_password is None


@pytest.mark.xdist_group("sqlite")
async def test_password_hash_async_sqlite(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    """Test password hashing with Argon2 and Passlib backends using async SQLite."""
    # Create async engine and session
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/test_password_async.db", echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(User.metadata.create_all)

    # Test with async session
    async with session_factory() as db_session:
        # Create user with passlib password
        user1 = User(name="user1_async", passlib_password="password123")
        db_session.add(user1)
        await db_session.flush()
        await db_session.refresh(user1)

        # Verify password hash is created correctly
        assert isinstance(user1.passlib_password, HashedPassword)
        assert user1.passlib_password.hash_string.startswith("$argon2")  # type: ignore[unreachable]
        assert user1.passlib_password.verify("password123")
        assert not user1.passlib_password.verify("wrong_password")

        # Create user with argon2 password
        user2 = User(name="user2_async", argon2_password="secret123")
        db_session.add(user2)
        await db_session.flush()
        await db_session.refresh(user2)

        # Verify password hash is created correctly
        assert isinstance(user2.argon2_password, HashedPassword)
        assert user2.argon2_password.hash_string.startswith("$argon2")
        assert user2.argon2_password.verify("secret123")
        assert not user2.argon2_password.verify("wrong_secret")

        # Test updating password
        user2.argon2_password = "newsecret123"
        await db_session.flush()
        await db_session.refresh(user2)
        assert isinstance(user2.argon2_password, HashedPassword)
        assert user2.argon2_password.verify("newsecret123")
        assert not user2.argon2_password.verify("secret123")

        # Test setting password to None
        user2.argon2_password = None
        await db_session.flush()
        await db_session.refresh(user2)
        assert user2.argon2_password is None
