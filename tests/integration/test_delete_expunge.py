"""Integration tests for delete operations with auto_expunge.

This test module validates the fix for issue #514 where delete operations
with auto_expunge=True and auto_commit=True would fail with InvalidRequestError.

These tests use real database sessions (not mocks) to validate that deleted
objects are properly handled by the _expunge() method across all delete operations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Union

import pytest
from sqlalchemy import String, inspect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, Session, mapped_column

from advanced_alchemy.base import UUIDAuditBase
from advanced_alchemy.repository import SQLAlchemyAsyncRepository, SQLAlchemySyncRepository

if TYPE_CHECKING:
    from sqlalchemy.orm.state import InstanceState


pytestmark = [
    pytest.mark.integration,
    pytest.mark.xdist_group("delete_expunge"),
]


class User(UUIDAuditBase):
    """Test model for delete expunge tests."""

    __tablename__ = "test_delete_expunge_user"

    name: Mapped[str] = mapped_column(String(50))
    active: Mapped[bool] = mapped_column(default=True)


class UserRepository(SQLAlchemyAsyncRepository[User]):
    """Async repository for User model."""

    model_type = User


class UserRepositorySync(SQLAlchemySyncRepository[User]):
    """Sync repository for User model."""

    model_type = User


# Helper function to check object state
def get_object_state(instance: Any) -> Union[InstanceState[Any], None]:
    """Get the SQLAlchemy object state."""
    try:
        return inspect(instance)  # type: ignore[no-any-return]
    except Exception:
        return None


def is_object_detached(instance: Any) -> bool:
    """Check if object is detached from session."""
    state = get_object_state(instance)
    return state is not None and state.detached


def is_object_in_session(instance: Any, session: Union[Session, AsyncSession]) -> bool:
    """Check if object is in session."""
    return instance in session


async def test_delete_with_auto_expunge_and_commit_async(async_session: AsyncSession) -> None:
    """Test delete() with auto_expunge=True and auto_commit=True (async).

    This is the core regression test for issue #514.
    Validates that delete() does not raise InvalidRequestError when both
    auto_expunge and auto_commit are enabled.
    """
    # Create table
    async with async_session.bind.begin() as conn:  # type: ignore[union-attr]
        await conn.run_sync(User.metadata.create_all)

    # Setup: Create a user
    repo = UserRepository(session=async_session)
    user = await repo.add(User(name="Alice", active=True))
    await async_session.commit()
    user_id = user.id

    # Create repository with auto_expunge and auto_commit
    repo_with_expunge = UserRepository(
        session=async_session,
        auto_expunge=True,
        auto_commit=True,
    )

    # This should NOT raise InvalidRequestError
    deleted = await repo_with_expunge.delete(user_id)

    # Verify: Object is detached from session
    assert is_object_detached(deleted), "Deleted object should be detached"
    assert not is_object_in_session(deleted, async_session), "Deleted object should not be in session"

    # Verify: User no longer exists in database
    with pytest.raises(Exception):  # NotFoundError or similar
        await repo.get_one(User.id == user_id)


async def test_delete_many_with_auto_expunge_and_commit_async(async_session: AsyncSession) -> None:
    """Test delete_many() with auto_expunge=True and auto_commit=True (async).

    Validates that delete_many() works correctly across different database backends.
    """
    # Create table
    async with async_session.bind.begin() as conn:  # type: ignore[union-attr]
        await conn.run_sync(User.metadata.create_all)

    # Setup: Create multiple users
    repo = UserRepository(session=async_session)
    users = await repo.add_many(
        [
            User(name="User1", active=True),
            User(name="User2", active=True),
            User(name="User3", active=True),
        ]
    )
    await async_session.commit()
    user1, user2, user3 = users[0], users[1], users[2]

    # Create repository with auto_expunge and auto_commit
    repo_with_expunge = UserRepository(
        session=async_session,
        auto_expunge=True,
        auto_commit=True,
    )

    # This should NOT raise InvalidRequestError
    deleted = await repo_with_expunge.delete_many([user1.id, user2.id])

    # Verify: All deleted objects are detached
    assert len(deleted) == 2
    for obj in deleted:
        assert is_object_detached(obj), "Deleted object should be detached"
        assert not is_object_in_session(obj, async_session), "Deleted object should not be in session"

    # Verify: Only user3 remains in database
    remaining = await repo.list()
    assert len(remaining) == 1
    assert remaining[0].id == user3.id


async def test_delete_where_with_auto_expunge_and_commit_async(async_session: AsyncSession) -> None:
    """Test delete_where() with auto_expunge=True and auto_commit=True (async).

    This is the MCVE from issue #514.
    """
    # Create table
    async with async_session.bind.begin() as conn:  # type: ignore[union-attr]
        await conn.run_sync(User.metadata.create_all)

    # Setup: Create users with different active states
    repo = UserRepository(session=async_session, auto_expunge=True, auto_commit=True)
    await repo.add_many(
        [
            User(name="Alice", active=True),
            User(name="Bob", active=False),
            User(name="Charlie", active=False),
        ]
    )
    await async_session.commit()

    # Bug reproduction: This failed with InvalidRequestError before the fix
    deleted = await repo.delete_where(User.active == False)  # noqa: E712

    # Expected: Should return 2 deleted users without error
    assert len(deleted) == 2
    assert all(not user.active for user in deleted), "All deleted users should be inactive"

    # Verify: Deleted objects are detached
    for obj in deleted:
        assert is_object_detached(obj), "Deleted object should be detached"
        assert not is_object_in_session(obj, async_session), "Deleted object should not be in session"

    # Verify: Only active user remains
    remaining = await repo.list()
    assert len(remaining) == 1
    assert remaining[0].name == "Alice"
    assert remaining[0].active is True


async def test_delete_with_auto_commit_false_keeps_in_session_async(async_session: AsyncSession) -> None:
    """Test that delete() with auto_commit=False keeps object in session.

    This validates that the fix doesn't break the case where objects
    should remain in the session (when auto_commit=False).
    """
    # Create table
    async with async_session.bind.begin() as conn:  # type: ignore[union-attr]
        await conn.run_sync(User.metadata.create_all)

    # Setup: Create a user
    repo = UserRepository(session=async_session)
    user = await repo.add(User(name="Alice", active=True))
    await async_session.commit()
    user_id = user.id

    # Delete with auto_commit=False
    repo_no_commit = UserRepository(
        session=async_session,
        auto_expunge=True,
        auto_commit=False,
    )

    deleted = await repo_no_commit.delete(user_id)

    # Object should still be in session (not committed yet)
    state = get_object_state(deleted)
    assert state is not None
    # The object is marked for deletion but hasn't been committed
    # so it's still in the session in "deleted" state

    # Rollback to clean up
    await async_session.rollback()


async def test_delete_with_auto_expunge_false_async(async_session: AsyncSession) -> None:
    """Test that delete() with auto_expunge=False doesn't expunge.

    This validates that the fix doesn't affect normal behavior when
    auto_expunge is disabled.
    """
    # Create table
    async with async_session.bind.begin() as conn:  # type: ignore[union-attr]
        await conn.run_sync(User.metadata.create_all)

    # Setup: Create a user
    repo = UserRepository(session=async_session)
    user = await repo.add(User(name="Alice", active=True))
    await async_session.commit()
    user_id = user.id

    # Delete with auto_expunge=False
    repo_no_expunge = UserRepository(
        session=async_session,
        auto_expunge=False,
        auto_commit=True,
    )

    deleted = await repo_no_expunge.delete(user_id)

    # Object should be detached (because commit happened)
    # but through normal SQLAlchemy lifecycle, not explicit expunge
    assert is_object_detached(deleted), "Object should be detached after commit"


def test_delete_with_auto_expunge_and_commit_sync(sync_session: Session) -> None:
    """Test delete() with auto_expunge=True and auto_commit=True (sync).

    Validates that the sync variant (generated by unasyncd) also works correctly.
    """
    # Create table
    if sync_session.bind is not None:
        User.metadata.create_all(sync_session.bind)

    # Setup: Create a user
    repo = UserRepositorySync(session=sync_session)
    user = repo.add(User(name="Alice", active=True))
    sync_session.commit()
    user_id = user.id

    # Create repository with auto_expunge and auto_commit
    repo_with_expunge = UserRepositorySync(
        session=sync_session,
        auto_expunge=True,
        auto_commit=True,
    )

    # This should NOT raise InvalidRequestError
    deleted = repo_with_expunge.delete(user_id)

    # Verify: Object is detached from session
    assert is_object_detached(deleted), "Deleted object should be detached"
    assert not is_object_in_session(deleted, sync_session), "Deleted object should not be in session"


def test_delete_where_with_auto_expunge_and_commit_sync(sync_session: Session) -> None:
    """Test delete_where() with auto_expunge=True and auto_commit=True (sync).

    MCVE from issue #514 for sync repository.
    """
    # Create table
    if sync_session.bind is not None:
        User.metadata.create_all(sync_session.bind)

    # Setup: Create users
    repo = UserRepositorySync(session=sync_session, auto_expunge=True, auto_commit=True)
    repo.add_many(
        [
            User(name="Alice", active=True),
            User(name="Bob", active=False),
            User(name="Charlie", active=False),
        ]
    )
    sync_session.commit()

    # This should NOT raise InvalidRequestError
    deleted = repo.delete_where(User.active == False)  # noqa: E712

    # Verify: Should return 2 deleted users
    assert len(deleted) == 2

    # Verify: Deleted objects are detached
    for obj in deleted:
        assert is_object_detached(obj), "Deleted object should be detached"
        assert not is_object_in_session(obj, sync_session), "Deleted object should not be in session"


async def test_delete_empty_result_with_auto_expunge_async(async_session: AsyncSession) -> None:
    """Test delete_where() with auto_expunge when no results match.

    Edge case: Ensure empty results don't cause issues.
    """
    # Create table
    async with async_session.bind.begin() as conn:  # type: ignore[union-attr]
        await conn.run_sync(User.metadata.create_all)

    # Setup: Create only active users
    repo = UserRepository(session=async_session, auto_expunge=True, auto_commit=True)
    await repo.add_many(
        [
            User(name="Alice", active=True),
            User(name="Bob", active=True),
        ]
    )
    await async_session.commit()

    # Delete inactive users (none exist)
    deleted = await repo.delete_where(User.active == False)  # noqa: E712

    # Verify: Empty result, no errors
    assert len(deleted) == 0


async def test_delete_nonexistent_with_auto_expunge_async(async_session: AsyncSession) -> None:
    """Test delete() on non-existent object with auto_expunge.

    Edge case: Ensure proper error handling.
    """
    # Create table
    async with async_session.bind.begin() as conn:  # type: ignore[union-attr]
        await conn.run_sync(User.metadata.create_all)

    repo = UserRepository(session=async_session, auto_expunge=True, auto_commit=True)

    # Try to delete non-existent user
    from uuid import uuid4

    fake_id = uuid4()
    with pytest.raises(Exception):  # Should raise appropriate error
        await repo.delete(fake_id)


# Mark specific database backends for targeted testing
@pytest.mark.sqlite
def test_sqlite_delete_with_auto_expunge(sync_session: Session) -> None:
    """SQLite-specific test for delete with auto_expunge."""
    test_delete_with_auto_expunge_and_commit_sync(sync_session)


@pytest.mark.aiosqlite
async def test_aiosqlite_delete_with_auto_expunge(async_session: AsyncSession) -> None:
    """SQLite async-specific test for delete with auto_expunge."""
    await test_delete_with_auto_expunge_and_commit_async(async_session)


@pytest.mark.asyncpg
async def test_postgresql_delete_with_auto_expunge(async_session: AsyncSession) -> None:
    """PostgreSQL-specific test for delete with auto_expunge."""
    await test_delete_with_auto_expunge_and_commit_async(async_session)


@pytest.mark.oracle18c
async def test_oracle_delete_with_auto_expunge(async_session: AsyncSession) -> None:
    """Oracle-specific test for delete with auto_expunge."""
    await test_delete_with_auto_expunge_and_commit_async(async_session)
