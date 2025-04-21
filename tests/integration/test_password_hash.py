from __future__ import annotations

from typing import TYPE_CHECKING, Optional, cast

import pytest
from passlib.context import CryptContext
from sqlalchemy import insert, select, update
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.types import String

from advanced_alchemy.base import BigIntBase
from advanced_alchemy.exceptions import ImproperConfigurationError
from advanced_alchemy.types.password_hash import PasswordHash
from advanced_alchemy.types.password_hash.argon2 import Argon2Hasher
from advanced_alchemy.types.password_hash.passlib import PasslibHasher

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import DeclarativeBase, Session


# Define the User model using PasswordHash
class User(BigIntBase):
    __tablename__ = "test_user_password_hash"
    name: Mapped[str] = mapped_column(String(50))
    password: Mapped[Optional[str]] = mapped_column(  # noqa: UP045
        PasswordHash(backend=PasslibHasher(context=CryptContext(schemes=["argon2"])))
    )
    argon2_password: Mapped[Optional[str]] = mapped_column(  # noqa: UP045
        PasswordHash(backend=Argon2Hasher())
    )


@pytest.fixture(name="user_model")
def fx_user_model() -> type[DeclarativeBase]:
    """User ORM instance"""
    return User


@pytest.mark.parametrize(
    ("session",),
    [
        pytest.param("session", id="sync"),
        pytest.param("async_session", id="async"),
    ],
    indirect=["session"],
)
@pytest.mark.integration
async def test_create_and_verify_password_explicit_argon2(
    user_model: type[User],
    session: AsyncSession | Session,
) -> None:
    """Tests creating a user with a password (explicit Argon2) and verifying it."""
    user = user_model(name="testuser_explicit", password="correct_password")  # type: ignore[call-arg]
    assert isinstance(user.password, PasswordHash)

    if isinstance(session, AsyncSession):
        async with session.begin():
            session.add(user)
        await session.flush()
        await session.refresh(user)
        user_id: int = user.id
        retrieved_user = await session.get(user_model, user_id)
    else:
        with session.begin():
            session.add(user)
        session.flush()
        session.refresh(user)
        user_id: int = user.id
        retrieved_user = session.get(user_model, user_id)

    assert retrieved_user is not None
    assert retrieved_user.name == "testuser_explicit"
    assert isinstance(retrieved_user.password, PasswordHash)

    # Verify password
    assert retrieved_user.password == "correct_password"
    assert not (retrieved_user.password == "wrong_password")

    # Check the hash structure (optional, depends on desired strictness)
    # For Argon2, it typically looks like $argon2id$v=19$m=...,t=...,p=...$...$...
    assert isinstance(retrieved_user.password, PasswordHash)
    assert retrieved_user.password.hash is not None
    assert retrieved_user.password.hash.startswith("$argon2")


@pytest.mark.parametrize(
    ("session",),
    [
        pytest.param("session", id="sync"),
        pytest.param("async_session", id="async"),
    ],
    indirect=["session"],
)
@pytest.mark.integration
async def test_update_password_explicit_argon2(
    user_model: type[User],
    session: AsyncSession | Session,
) -> None:
    """Tests updating a user's password (explicit Argon2)."""
    user = user_model(name="updateuser_explicit", password="old_password")  # type: ignore[call-arg]

    # Initial save
    if isinstance(session, AsyncSession):
        async with session.begin():
            session.add(user)
        await session.flush()
        user_id: int = user.id
    else:
        with session.begin():
            session.add(user)
        session.flush()
        user_id: int = user.id

    # Retrieve and update
    if isinstance(session, AsyncSession):
        retrieved_user_for_update = await session.get(user_model, user_id)
        assert retrieved_user_for_update is not None
        retrieved_user_for_update.password = "new_password"
        async with session.begin():
            session.add(retrieved_user_for_update)
        await session.flush()
        await session.refresh(retrieved_user_for_update)
    else:
        retrieved_user_for_update = session.get(user_model, user_id)
        assert retrieved_user_for_update is not None
        retrieved_user_for_update.password = "new_password"
        with session.begin():
            session.add(retrieved_user_for_update)
        session.flush()
        session.refresh(retrieved_user_for_update)

    # Verify updated password
    if isinstance(session, AsyncSession):
        updated_user = await session.get(user_model, user_id)
    else:
        updated_user = session.get(user_model, user_id)

    assert updated_user is not None
    assert updated_user.password == "new_password"
    assert not (updated_user.password == "old_password")


@pytest.mark.parametrize(
    ("session",),
    [
        pytest.param("session", id="sync"),
        pytest.param("async_session", id="async"),
    ],
    indirect=["session"],
)
@pytest.mark.integration
async def test_password_comparison_with_non_string_explicit_argon2(
    user_model: type[User],
    session: AsyncSession | Session,
) -> None:
    """Tests comparing password (explicit Argon2) with non-string types."""
    user = user_model(name="compareuser_explicit", password="password123")  # type: ignore[call-arg]

    if isinstance(session, AsyncSession):
        async with session.begin():
            session.add(user)
        await session.flush()
        user_id: int = user.id
        retrieved_user = await session.get(user_model, user_id)
    else:
        with session.begin():
            session.add(user)
        session.flush()
        user_id: int = user.id
        retrieved_user = session.get(user_model, user_id)

    assert retrieved_user is not None
    assert not (retrieved_user.password == 123)
    assert retrieved_user.password is not None
    assert not (retrieved_user.password == b"password123")


@pytest.mark.parametrize(
    ("session",),
    [
        pytest.param("session", id="sync"),
        pytest.param("async_session", id="async"),
    ],
    indirect=["session"],
)
@pytest.mark.integration
async def test_set_password_to_none_explicit_argon2(
    user_model: type[User],
    session: AsyncSession | Session,
) -> None:
    """Tests setting the password (explicit Argon2) to None explicitly."""
    user = user_model(name="noneuser_explicit", password="initial_password")  # type: ignore[call-arg]

    # Initial save
    if isinstance(session, AsyncSession):
        async with session.begin():
            session.add(user)
        await session.flush()
        user_id: int = user.id
    else:
        with session.begin():
            session.add(user)
        session.flush()
        user_id: int = user.id

    # Retrieve and set to None
    if isinstance(session, AsyncSession):
        retrieved_user_for_update = await session.get(user_model, user_id)
        assert retrieved_user_for_update is not None
        retrieved_user_for_update.password = None
        async with session.begin():
            session.add(retrieved_user_for_update)
        await session.flush()
        refreshed_user = await session.get(user_model, user_id)
    else:
        retrieved_user_for_update = session.get(user_model, user_id)
        assert retrieved_user_for_update is not None
        retrieved_user_for_update.password = None
        with session.begin():
            session.add(retrieved_user_for_update)
        session.flush()
        refreshed_user = session.get(user_model, user_id)

    assert refreshed_user is not None
    assert refreshed_user.password is None


@pytest.mark.parametrize(
    ("session",),
    [
        pytest.param("session", id="sync"),
        pytest.param("async_session", id="async"),
    ],
    indirect=["session"],
)
@pytest.mark.integration
async def test_create_and_verify_password_default_argon2(
    user_model: type[User],
    session: AsyncSession | Session,
) -> None:
    """Tests creating a user with a password (default Argon2) and verifying it."""
    user = user_model(name="testuser_default", argon2_password="correct_password")
    assert isinstance(user.argon2_password, PasswordHash)

    if isinstance(session, AsyncSession):
        async with session.begin():
            session.add(user)
        await session.flush()
        await session.refresh(user)
        user_id: int = user.id
        retrieved_user = await session.get(user_model, user_id)
    else:
        with session.begin():
            session.add(user)
        session.flush()
        session.refresh(user)
        user_id: int = user.id
        retrieved_user = session.get(user_model, user_id)

    assert retrieved_user is not None
    assert retrieved_user.name == "testuser_default"
    assert isinstance(retrieved_user.argon2_password, PasswordHash)
    assert retrieved_user.argon2_password == "correct_password"
    assert not (retrieved_user.argon2_password == "wrong_password")
    assert retrieved_user.argon2_password.hash is not None
    # Default context uses argon2
    assert retrieved_user.argon2_password.hash.startswith("$argon2")


@pytest.mark.parametrize(
    ("session",),
    [
        # Run only on postgres async
        pytest.param("async_pg_session", marks=pytest.mark.sqlalchemy_dialect("postgresql"), id="async_postgres"),
        # Run only on postgres sync
        pytest.param("sync_pg_session", marks=pytest.mark.sqlalchemy_dialect("postgresql"), id="sync_postgres"),
    ],
    indirect=["session"],
)
@pytest.mark.integration
async def test_create_and_verify_pgcrypto_password(
    user_model: type[User],
    session: AsyncSession | Session,
) -> None:
    """Tests creating a user with a pgcrypto password and verifying it via SQL."""

    plain_password = "correct_pg_password"
    user = user_model(name="testuser_pgcrypto")

    # Hashing for pgcrypto returns a SQL expression, not a string hash directly
    hash_expression = PgCryptoBackend().hash(plain_password)

    if isinstance(session, AsyncSession):
        async with session.begin():
            # Execute the insert with the hash expression
            insert_stmt = (
                insert(user_model).values(name=user.name, pgcrypto_password=hash_expression).returning(user_model.id)
            )
            result = await session.execute(insert_stmt)
            user_id = result.scalar_one()
            await session.flush()  # Ensure the insert happens within the transaction

        # Verify using SQL comparison expression
        verify_stmt = select(user_model).where(
            user_model.id == user_id,
            PgCryptoBackend.get_sql_comparison_expression(
                cast(ColumnElement[str], user_model.pgcrypto_password), plain_password
            ),
        )
        verify_result = await session.execute(verify_stmt)
        verified_user = verify_result.scalar_one_or_none()

        # Verify incorrect password fails
        fail_verify_stmt = select(user_model).where(
            user_model.id == user_id,
            PgCryptoBackend.get_sql_comparison_expression(
                cast(ColumnElement[str], user_model.pgcrypto_password), "wrong_password"
            ),
        )
        fail_verify_result = await session.execute(fail_verify_stmt)
        failed_user = fail_verify_result.scalar_one_or_none()

    else:  # Sync session
        with session.begin():
            insert_stmt = (
                insert(user_model).values(name=user.name, pgcrypto_password=hash_expression).returning(user_model.id)
            )
            result = session.execute(insert_stmt)
            user_id = result.scalar_one()
            session.flush()

        # Verify using SQL comparison expression
        verify_stmt = select(user_model).where(
            user_model.id == user_id,
            PgCryptoBackend.get_sql_comparison_expression(
                cast(ColumnElement[str], user_model.pgcrypto_password), plain_password
            ),
        )
        verify_result = session.execute(verify_stmt)
        verified_user = verify_result.scalar_one_or_none()

        # Verify incorrect password fails
        fail_verify_stmt = select(user_model).where(
            user_model.id == user_id,
            PgCryptoBackend.get_sql_comparison_expression(
                cast(ColumnElement[str], user_model.pgcrypto_password), "wrong_password"
            ),
        )
        fail_verify_result = session.execute(fail_verify_stmt)
        failed_user = fail_verify_result.scalar_one_or_none()

    assert verified_user is not None
    assert verified_user.name == "testuser_pgcrypto"
    assert failed_user is None  # Should not find a user with the wrong password

    # Direct comparison in Python is not supported and should fail or raise Error
    retrieved_user = (
        await session.get(user_model, user_id)
        if isinstance(session, AsyncSession)
        else session.get(user_model, user_id)
    )
    assert retrieved_user is not None

    with pytest.raises(NotImplementedError):
        _ = retrieved_user.pgcrypto_password == plain_password  # type: ignore[attr-defined]

    with pytest.raises(ImproperConfigurationError):
        # Accessing .hash directly might also be restricted depending on implementation
        _ = retrieved_user.pgcrypto_password.hash  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("session",),
    [
        pytest.param("async_pg_session", marks=pytest.mark.sqlalchemy_dialect("postgresql"), id="async_postgres"),
        pytest.param("sync_pg_session", marks=pytest.mark.sqlalchemy_dialect("postgresql"), id="sync_postgres"),
    ],
    indirect=["session"],
)
@pytest.mark.integration
async def test_update_pgcrypto_password(
    user_model: type[User],
    session: AsyncSession | Session,
) -> None:
    """Tests updating a user's pgcrypto password."""
    old_password = "old_pg_password"
    new_password = "new_pg_password"
    user_name = "updateuser_pgcrypto"

    # Initial insert
    hash_expression_old = PgCryptoBackend().hash(old_password)
    if isinstance(session, AsyncSession):
        async with session.begin():
            insert_stmt = (
                insert(user_model)
                .values(name=user_name, pgcrypto_password=hash_expression_old)
                .returning(user_model.id)
            )
            result = await session.execute(insert_stmt)
            user_id = result.scalar_one()
            await session.flush()
    else:
        with session.begin():
            insert_stmt = (
                insert(user_model)
                .values(name=user_name, pgcrypto_password=hash_expression_old)
                .returning(user_model.id)
            )
            result = session.execute(insert_stmt)
            user_id = result.scalar_one()
            session.flush()

    # Update the password
    hash_expression_new = PgCryptoBackend().hash(new_password)
    if isinstance(session, AsyncSession):
        async with session.begin():
            update_stmt = (
                update(user_model).where(user_model.id == user_id).values(pgcrypto_password=hash_expression_new)
            )
            await session.execute(update_stmt)
            await session.flush()
    else:
        with session.begin():
            update_stmt = (
                update(user_model).where(user_model.id == user_id).values(pgcrypto_password=hash_expression_new)
            )
            session.execute(update_stmt)
            session.flush()

    # Verify new password works
    verify_new_stmt = select(user_model).where(
        user_model.id == user_id,
        PgCryptoBackend.get_sql_comparison_expression(
            cast(ColumnElement[str], user_model.pgcrypto_password), new_password
        ),
    )
    # Verify old password fails
    verify_old_stmt = select(user_model).where(
        user_model.id == user_id,
        PgCryptoBackend.get_sql_comparison_expression(
            cast(ColumnElement[str], user_model.pgcrypto_password), old_password
        ),
    )

    if isinstance(session, AsyncSession):
        new_pw_result = await session.execute(verify_new_stmt)
        verified_user_new = new_pw_result.scalar_one_or_none()
        old_pw_result = await session.execute(verify_old_stmt)
        verified_user_old = old_pw_result.scalar_one_or_none()
    else:
        new_pw_result = session.execute(verify_new_stmt)
        verified_user_new = new_pw_result.scalar_one_or_none()
        old_pw_result = session.execute(verify_old_stmt)
        verified_user_old = old_pw_result.scalar_one_or_none()

    assert verified_user_new is not None  # New password should verify
    assert verified_user_old is None  # Old password should fail


@pytest.mark.parametrize(
    ("session",),
    [
        pytest.param("async_pg_session", marks=pytest.mark.sqlalchemy_dialect("postgresql"), id="async_postgres"),
        pytest.param("sync_pg_session", marks=pytest.mark.sqlalchemy_dialect("postgresql"), id="sync_postgres"),
    ],
    indirect=["session"],
)
@pytest.mark.integration
async def test_set_pgcrypto_password_to_none(
    user_model: type[User],
    session: AsyncSession | Session,
) -> None:
    """Tests setting the pgcrypto password to None explicitly."""
    initial_password = "initial_pg_password"
    user_name = "noneuser_pgcrypto"

    # Initial insert
    hash_expression_initial = PgCryptoBackend().hash(initial_password)
    if isinstance(session, AsyncSession):
        async with session.begin():
            insert_stmt = (
                insert(user_model)
                .values(name=user_name, pgcrypto_password=hash_expression_initial)
                .returning(user_model.id)
            )
            result = await session.execute(insert_stmt)
            user_id = result.scalar_one()
            await session.flush()
    else:
        with session.begin():
            insert_stmt = (
                insert(user_model)
                .values(name=user_name, pgcrypto_password=hash_expression_initial)
                .returning(user_model.id)
            )
            result = session.execute(insert_stmt)
            user_id = result.scalar_one()
            session.flush()

    # Update to None
    if isinstance(session, AsyncSession):
        async with session.begin():
            update_stmt = update(user_model).where(user_model.id == user_id).values(pgcrypto_password=None)
            await session.execute(update_stmt)
            await session.flush()
        refreshed_user = await session.get(user_model, user_id)
    else:
        with session.begin():
            update_stmt = update(user_model).where(user_model.id == user_id).values(pgcrypto_password=None)
            session.execute(update_stmt)
            session.flush()
        refreshed_user = session.get(user_model, user_id)

    assert refreshed_user is not None
    assert refreshed_user.pgcrypto_password is None
