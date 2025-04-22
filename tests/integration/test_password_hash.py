# ruff: noqa: RUF100, I001, UP007, UP045
from __future__ import annotations

from collections.abc import AsyncGenerator, Generator
from typing import Optional, cast
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
import pytest
from passlib.context import CryptContext
from pytest import FixtureRequest
from pytest_lazy_fixtures import lf
from sqlalchemy import Engine, insert, select, update
from sqlalchemy.orm import Mapped, mapped_column, sessionmaker
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.types import String

from advanced_alchemy.base import BigIntBase, UUIDAuditBase
from advanced_alchemy.types import PasswordHash
from advanced_alchemy.types.password_hash.argon2 import Argon2Hasher
from advanced_alchemy.types.password_hash.passlib import PasslibHasher
from advanced_alchemy.types.password_hash.pgcrypto import PgCryptoHasher
from advanced_alchemy.utils.sync_tools import maybe_async_, maybe_async_context


# Define the User model using PasswordHash
class User(BigIntBase):
    __tablename__ = "test_user_password_hash"
    name: Mapped[str] = mapped_column(String(50))
    password: Mapped[Optional[str]] = mapped_column(
        PasswordHash(backend=PasslibHasher(context=CryptContext(schemes=["argon2"])))
    )
    argon2_password: Mapped[Optional[str]] = mapped_column(PasswordHash(backend=Argon2Hasher()))
    pgcrypto_password: Mapped[Optional[str]] = mapped_column(PasswordHash(backend=PgCryptoHasher(algorithm="bf")))


@pytest.fixture(name="user_model")
def fx_user_model() -> type[User]:
    """User ORM instance"""
    return User


@pytest.fixture(
    name="postgres_sync_engine",
    params=[
        pytest.param(
            "psycopg_engine",
            marks=[
                pytest.mark.psycopg_sync,
                pytest.mark.integration,
                pytest.mark.xdist_group("postgres"),
            ],
        ),
    ],
)
def postgres_sync_engine(request: FixtureRequest) -> Generator[Engine, None, None]:
    yield cast(Engine, request.getfixturevalue(request.param))


@pytest.fixture()
def postgres_sync_session(
    postgres_sync_engine: Engine, request: FixtureRequest, user_model: type[User]
) -> Generator[Session, None, None]:
    session_instance = sessionmaker(bind=postgres_sync_engine, expire_on_commit=False)()
    with postgres_sync_engine.begin() as conn:
        user_model.metadata.create_all(conn)
    try:
        yield session_instance
    finally:
        session_instance.rollback()
        session_instance.close()


@pytest.fixture(
    name="postgres_async_engine",
    params=[
        pytest.param(
            "asyncpg_engine",
            marks=[
                pytest.mark.asyncpg,
                pytest.mark.integration,
                pytest.mark.xdist_group("postgres"),
            ],
        ),
        pytest.param(
            "psycopg_async_engine",
            marks=[
                pytest.mark.psycopg_async,
                pytest.mark.integration,
                pytest.mark.xdist_group("postgres"),
            ],
        ),
    ],
)
async def postgres_async_engine(request: FixtureRequest) -> AsyncGenerator[AsyncEngine, None]:
    """Parametrized fixture to provide different async SQLAlchemy engines."""
    engine = cast(AsyncEngine, request.getfixturevalue(request.param))
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.mark.xdist_group("postgres")
@pytest.mark.parametrize(
    ("session",),
    [
        # Run only on postgres async
        pytest.param(
            "psycopg_engine",
            marks=[
                pytest.mark.psycopg_sync,
                pytest.mark.integration,
                pytest.mark.xdist_group("postgres"),
            ],
            id="async_postgres",
        ),
        # Run only on postgres sync
        pytest.param(
            "psycopg_engine",
            marks=[
                pytest.mark.psycopg_sync,
                pytest.mark.integration,
                pytest.mark.xdist_group("postgres"),
            ],
            id="sync_postgres",
        ),
    ],
    indirect=["session"],
)
@pytest.fixture()
async def postgres_async_session(
    postgres_async_engine: AsyncEngine,
    request: FixtureRequest,
    user_model: type[User],
) -> AsyncGenerator[AsyncSession, None]:
    """Provides an async SQLAlchemy session for the parametrized async engine."""
    session_instance = async_sessionmaker(bind=postgres_async_engine, expire_on_commit=False)()
    async with postgres_async_engine.begin() as conn:
        await conn.run_sync(user_model.metadata.create_all)  # type: ignore[arg-type]
    try:
        yield session_instance
    finally:
        await session_instance.rollback()
        await session_instance.close()


@pytest.fixture(params=[lf("postgres_sync_session"), lf("postgres_async_session")], ids=["sync", "async"])
async def any_postgres_session(request: FixtureRequest) -> AsyncGenerator[AsyncSession | Session, None]:
    """Return a session for the current session"""
    session = request.param
    try:
        yield session
    finally:
        if isinstance(session, AsyncSession):
            await session.close()
        else:
            session.close()


@pytest.mark.integration
async def test_create_and_verify_password_explicit_argon2(
    user_model: type[User],
    any_postgres_session: AsyncSession | Session,
) -> None:
    """Tests creating a user with a password (explicit Argon2) and verifying it."""
    user = user_model(name="testuser_explicit", password="correct_password")  # type: ignore[call-arg]

    async with maybe_async_context(any_postgres_session.begin()):
        await maybe_async_(any_postgres_session.add)(user)
        await maybe_async_(any_postgres_session.flush)()
        await maybe_async_(any_postgres_session.refresh)(user)
        user_id: int = user.id
        retrieved_user = await maybe_async_(any_postgres_session.get)(user_model, user_id)  # type: ignore[arg-type]

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


@pytest.mark.integration
async def test_update_password_explicit_argon2(
    user_model: type[User],
    any_postgres_session: AsyncSession | Session,
) -> None:
    """Tests updating a user's password (explicit Argon2)."""
    user = user_model(name="updateuser_explicit", password="old_password")  # type: ignore[call-arg]

    # Initial save
    async with maybe_async_context(any_postgres_session.begin()):
        await maybe_async_(any_postgres_session.add)(user)
        await maybe_async_(any_postgres_session.flush)()
        user_id: int = user.id

    # Retrieve and update
    retrieved_user_for_update = await maybe_async_(any_postgres_session.get)(user_model, user_id)  # type: ignore[arg-type]
    assert retrieved_user_for_update is not None
    retrieved_user_for_update.password = "new_password"
    async with maybe_async_context(any_postgres_session.begin()):
        await maybe_async_(any_postgres_session.add)(retrieved_user_for_update)
        await maybe_async_(any_postgres_session.flush)()
        await maybe_async_(any_postgres_session.refresh)(retrieved_user_for_update)

    # Verify updated password
    assert retrieved_user_for_update is not None
    assert retrieved_user_for_update.password == "new_password"
    assert not (retrieved_user_for_update.password == "old_password")


@pytest.mark.integration
async def test_password_comparison_with_non_string_explicit_argon2(
    user_model: type[User],
    any_postgres_session: AsyncSession | Session,
) -> None:
    """Tests comparing password (explicit Argon2) with non-string types."""
    user = user_model(name="compareuser_explicit", password="password123")  # type: ignore[call-arg]

    async with maybe_async_context(any_postgres_session.begin()):
        await maybe_async_(any_postgres_session.add)(user)
        await maybe_async_(any_postgres_session.flush)()
        user_id: int = user.id
        retrieved_user = await maybe_async_(any_postgres_session.get)(user_model, user_id)  # type: ignore[arg-type]

    assert retrieved_user is not None
    assert not (retrieved_user.password == 123)
    assert retrieved_user.password is not None
    assert not (retrieved_user.password == b"password123")


@pytest.mark.integration
async def test_set_password_to_none_explicit_argon2(
    user_model: type[User],
    any_postgres_session: AsyncSession | Session,
) -> None:
    """Tests setting the password (explicit Argon2) to None explicitly."""
    user = user_model(name="noneuser_explicit", password="initial_password")  # type: ignore[call-arg]

    # Initial save
    async with maybe_async_context(any_postgres_session.begin()):
        await maybe_async_(any_postgres_session.add)(user)
        await maybe_async_(any_postgres_session.flush)()
        user_id: int = user.id

    # Retrieve and set to None
    retrieved_user_for_update = await maybe_async_(any_postgres_session.get)(user_model, user_id)  # type: ignore[arg-type]
    assert retrieved_user_for_update is not None
    retrieved_user_for_update.password = None
    async with maybe_async_context(any_postgres_session.begin()):
        await maybe_async_(any_postgres_session.add)(retrieved_user_for_update)
        await maybe_async_(any_postgres_session.flush)()
        refreshed_user = await maybe_async_(any_postgres_session.get)(user_model, user_id)  # type: ignore[arg-type]

    assert refreshed_user is not None
    assert refreshed_user.password is None


@pytest.mark.integration
async def test_create_and_verify_password_default_argon2(
    user_model: type[User],
    any_postgres_session: AsyncSession | Session,
) -> None:
    """Tests creating a user with a password (default Argon2) and verifying it."""
    user = user_model(name="testuser_default", argon2_password="correct_password")
    assert isinstance(user.argon2_password, PasswordHash)

    async with maybe_async_context(any_postgres_session.begin()):
        await maybe_async_(any_postgres_session.add)(user)
        await maybe_async_(any_postgres_session.flush)()
        await maybe_async_(any_postgres_session.refresh)(user)
        user_id: int = user.id
        retrieved_user = await maybe_async_(any_postgres_session.get)(user_model, user_id)  # type: ignore[arg-type]

    assert retrieved_user is not None
    assert retrieved_user.name == "testuser_default"
    assert isinstance(retrieved_user.argon2_password, PasswordHash)
    assert retrieved_user.argon2_password == "correct_password"
    assert not (retrieved_user.argon2_password == "wrong_password")
    assert retrieved_user.argon2_password.hash is not None
    # Default context uses argon2
    assert retrieved_user.argon2_password.hash.startswith("$argon2")


@pytest.mark.integration
async def test_create_and_verify_pgcrypto_password(
    user_model: type[User],
    any_postgres_session: AsyncSession | Session,
) -> None:
    """Tests creating a user with a pgcrypto password and verifying it via SQL."""

    # Create user with pgcrypto password
    user = user_model(name="testuser_default")
    user.pgcrypto_password = "correct_password"  # This will trigger the PasswordHash type conversion
    assert isinstance(user.pgcrypto_password, PasswordHash)

    async with maybe_async_context(any_postgres_session.begin()):
        await maybe_async_(any_postgres_session.add)(user)
        await maybe_async_(any_postgres_session.flush)()
        await maybe_async_(any_postgres_session.refresh)(user)
        user_id: int = user.id
        retrieved_user = await maybe_async_(lambda: any_postgres_session.get(user_model, user_id))()

    assert retrieved_user is not None
    assert retrieved_user.name == "testuser_default"
    assert isinstance(retrieved_user.pgcrypto_password, PasswordHash)
    assert retrieved_user.pgcrypto_password == "correct_password"
    assert not (retrieved_user.pgcrypto_password == "wrong_password")
    assert retrieved_user.pgcrypto_password.hash is not None
    # Default context uses argon2
    assert retrieved_user.pgcrypto_password.hash.startswith("$2a$")


@pytest.mark.integration
async def test_update_pgcrypto_password(
    user_model: type[User],
    any_postgres_session: AsyncSession | Session,
) -> None:
    """Tests updating a user's pgcrypto password."""
    old_password = "old_pg_password"
    new_password = "new_pg_password"
    user_name = "updateuser_pgcrypto"

    # Initial insert
    hash_expression_old = PgCryptoHasher(algorithm="bf").hash(old_password)
    async with maybe_async_context(any_postgres_session.begin()):
        insert_stmt = (
            insert(user_model).values(name=user_name, pgcrypto_password=hash_expression_old).returning(user_model.id)
        )
        result = await maybe_async_(any_postgres_session.execute)(insert_stmt)
        user_id = result.scalar_one()
        await maybe_async_(any_postgres_session.flush)()

    # Update the password
    hash_expression_new = PgCryptoHasher(algorithm="bf").hash(new_password)
    async with maybe_async_context(any_postgres_session.begin()):
        update_stmt = update(user_model).where(user_model.id == user_id).values(pgcrypto_password=hash_expression_new)
        await maybe_async_(any_postgres_session.execute)(update_stmt)
        await maybe_async_(any_postgres_session.flush)()

    # Verify new password works
    verify_new_stmt = select(user_model).where(
        user_model.id == user_id,
        PgCryptoHasher(algorithm="bf").compare_expression(
            cast(ColumnElement[str], user_model.pgcrypto_password), new_password
        ),
    )
    # Verify old password fails
    verify_old_stmt = select(user_model).where(
        user_model.id == user_id,
        PgCryptoHasher(algorithm="bf").compare_expression(
            cast(ColumnElement[str], user_model.pgcrypto_password), old_password
        ),
    )

    new_pw_result = await maybe_async_(any_postgres_session.execute)(verify_new_stmt)
    verified_user_new = new_pw_result.scalar_one_or_none()
    old_pw_result = await maybe_async_(any_postgres_session.execute)(verify_old_stmt)
    verified_user_old = old_pw_result.scalar_one_or_none()

    assert verified_user_new is not None  # New password should verify
    assert verified_user_old is None  # Old password should fail


@pytest.mark.integration
async def test_set_pgcrypto_password_to_none(
    user_model: type[User],
    any_postgres_session: AsyncSession | Session,
) -> None:
    """Tests setting the pgcrypto password to None explicitly."""
    initial_password = "initial_pg_password"
    user_name = "noneuser_pgcrypto"

    # Initial insert
    hash_expression_initial = PgCryptoHasher(algorithm="bf").hash(initial_password)
    async with maybe_async_context(any_postgres_session.begin()):
        insert_stmt = (
            insert(user_model)
            .values(name=user_name, pgcrypto_password=hash_expression_initial)
            .returning(user_model.id)
        )
        result = await maybe_async_(any_postgres_session.execute)(insert_stmt)
        user_id = result.scalar_one()
        await maybe_async_(any_postgres_session.flush)()

    # Update to None
    async with maybe_async_context(any_postgres_session.begin()):
        update_stmt = update(user_model).where(user_model.id == user_id).values(pgcrypto_password=None)
        await maybe_async_(any_postgres_session.execute)(update_stmt)
        await maybe_async_(any_postgres_session.flush)()
        refreshed_user = await maybe_async_(lambda: any_postgres_session.get(user_model, user_id))()

    assert refreshed_user is not None
    assert refreshed_user.pgcrypto_password is None


@pytest.fixture()
async def async_session_maker(async_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create an async session maker."""
    return async_sessionmaker(async_engine, expire_on_commit=False)


@pytest.fixture()
async def async_session(async_session_maker: async_sessionmaker[AsyncSession]) -> AsyncGenerator[AsyncSession, None]:
    """Create an async session."""
    async with async_session_maker() as session:
        yield session


@pytest.fixture(autouse=True)
async def setup_database(async_engine: AsyncEngine) -> AsyncGenerator[None, None]:
    """Set up the database."""
    async with async_engine.begin() as conn:
        await conn.run_sync(UUIDAuditBase.metadata.create_all)
    yield
    async with async_engine.begin() as conn:
        await conn.run_sync(UUIDAuditBase.metadata.drop_all)


@pytest.fixture(scope="function")
async def async_user(async_session: AsyncSession) -> User:
    """Create a test user with an argon2 password."""
    user = User(name="testuser", argon2_password="correct_password")
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)
    return user


@pytest.fixture(scope="function")
async def async_user_pgcrypto(async_session: AsyncSession) -> User:
    """Create a test user with a pgcrypto password."""
    user = User(name="testuser", pgcrypto_password="correct_password")
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)
    return user


@pytest.mark.asyncio
async def test_create_and_verify_argon2_password_async_only(async_session: AsyncSession) -> None:
    """Test creating and verifying an argon2 password."""
    user = User(name="testuser", argon2_password="correct_password")
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)

    assert user.argon2_password is not None
    assert isinstance(user.argon2_password, PasswordHash)
    assert str(user.argon2_password).startswith("$argon2")
    assert user.argon2_password == "correct_password"
    assert user.argon2_password != "wrong_password"


@pytest.mark.asyncio
async def test_create_and_verify_pgcrypto_password_async_only(async_session: AsyncSession) -> None:
    """Test creating and verifying a pgcrypto password."""
    user = User(name="testuser", pgcrypto_password="correct_password")
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)

    assert user.pgcrypto_password is not None
    assert isinstance(user.pgcrypto_password, PasswordHash)
    assert user.pgcrypto_password == "correct_password"
    assert user.pgcrypto_password != "wrong_password"


@pytest.mark.asyncio
async def test_update_password_async_only(async_user: User, async_session: AsyncSession) -> None:
    """Test updating an argon2 password."""
    async_user.argon2_password = "new_password"
    await async_session.commit()
    await async_session.refresh(async_user)

    assert async_user.argon2_password == "new_password"
    assert async_user.argon2_password != "old_password"


@pytest.mark.asyncio
async def test_update_password_pgcrypto_async_only(async_user_pgcrypto: User, async_session: AsyncSession) -> None:
    """Test updating a pgcrypto password."""
    async_user_pgcrypto.pgcrypto_password = "new_password"
    await async_session.commit()
    await async_session.refresh(async_user_pgcrypto)

    assert async_user_pgcrypto.pgcrypto_password == "new_password"
    assert async_user_pgcrypto.pgcrypto_password != "old_password"


@pytest.mark.asyncio
async def test_password_comparison_with_non_string_async_only(async_user: User) -> None:
    """Test comparing a password with non-string values."""
    assert async_user.argon2_password != None  # noqa: E711
    assert async_user.argon2_password != 123
    assert async_user.argon2_password != []
    assert async_user.argon2_password != {}


@pytest.mark.asyncio
async def test_set_password_to_none_async_only(async_user: User, async_session: AsyncSession) -> None:
    """Test setting a password to None."""
    async_user.argon2_password = None
    await async_session.commit()
    await async_session.refresh(async_user)
    assert async_user.argon2_password is None


@pytest.mark.asyncio
async def test_set_pgcrypto_password_to_none_async_only(async_user_pgcrypto: User, async_session: AsyncSession) -> None:
    """Test setting a pgcrypto password to None."""
    async_user_pgcrypto.pgcrypto_password = None
    await async_session.commit()
    await async_session.refresh(async_user_pgcrypto)
    assert async_user_pgcrypto.pgcrypto_password is None


@pytest.mark.asyncio
async def test_delete_user_async_only(async_user: User, async_session: AsyncSession) -> None:
    """Test deleting a user."""
    await async_session.delete(async_user)
    await async_session.commit()
    result = await async_session.execute(select(User).filter_by(name="testuser"))
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_delete_user_pgcrypto_async_only(async_user_pgcrypto: User, async_session: AsyncSession) -> None:
    """Test deleting a user with pgcrypto password."""
    await async_session.delete(async_user_pgcrypto)
    await async_session.commit()
    result = await async_session.execute(select(User).filter_by(name="testuser"))
    assert result.scalar_one_or_none() is None
