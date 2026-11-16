===================
Advanced Repository
===================

Repositories support composite primary keys, row-level ``SELECT ... FOR UPDATE`` locking, conditional bulk deletes, and cross-dialect exception translation.

.. _composite-primary-keys:

Composite Primary Keys
----------------------

Models keyed by multiple primary-key columns (such as ``(user_id, role_id)`` on ``UserRole``) accept composite keys in ``get`` and ``delete_many`` either as a column-name dictionary (recommended) or as an ordered tuple:

.. tab-set::

    .. tab-item:: Model Setup

        .. code-block:: python

            from collections.abc import Sequence
            from sqlalchemy import ForeignKey
            from sqlalchemy.ext.asyncio import AsyncSession
            from sqlalchemy.orm import Mapped, mapped_column
            from advanced_alchemy.base import BigIntBase, DefaultBase
            from advanced_alchemy.repository import SQLAlchemyAsyncRepository


            class AdvancedUser(BigIntBase):
                __tablename__ = "advanced_user_account"
                username: Mapped[str]


            class AdvancedRole(BigIntBase):
                __tablename__ = "advanced_role"
                name: Mapped[str]


            class AdvancedUserRole(DefaultBase):
                __tablename__ = "advanced_user_role"

                user_id: Mapped[int] = mapped_column(ForeignKey("advanced_user_account.id"), primary_key=True)
                role_id: Mapped[int] = mapped_column(ForeignKey("advanced_role.id"), primary_key=True)
                permissions: Mapped[str] = mapped_column(default="member")


            class AdvancedPost(BigIntBase):
                __tablename__ = "advanced_post"
                title: Mapped[str]
                published: Mapped[bool] = mapped_column(default=False)


            class AdvancedUserRoleRepository(SQLAlchemyAsyncRepository[AdvancedUserRole]):
                model_type = AdvancedUserRole


            class AdvancedUserRepository(SQLAlchemyAsyncRepository[AdvancedUser]):
                model_type = AdvancedUser


            class AdvancedPostRepository(SQLAlchemyAsyncRepository[AdvancedPost]):
                model_type = AdvancedPost

    .. tab-item:: Dictionary Key (Recommended)

        .. code-block:: python

            async def get_role_by_dict(
                db_session: AsyncSession,
                user_id: int,
                role_id: int,
            ) -> AdvancedUserRole:
                repo = AdvancedUserRoleRepository(session=db_session)
                return await repo.get({"user_id": user_id, "role_id": role_id})

    .. tab-item:: Tuple Key & Bulk Delete

        .. code-block:: python

            async def get_and_remove_roles(
                db_session: AsyncSession,
                user_id: int,
                role_id: int,
            ) -> Sequence[AdvancedUserRole]:
                repo = AdvancedUserRoleRepository(session=db_session)
                _ = await repo.get((user_id, role_id))
                return await repo.delete_many([{"user_id": user_id, "role_id": role_id}])

Row Locking
-----------

Pass ``with_for_update=True`` (or a dictionary of ``FOR UPDATE`` options such as ``nowait`` and ``of``) to acquire a row-level lock for the duration of the current transaction:

.. code-block:: python

    async def lock_user_for_update(db_session: AsyncSession, user_id: int) -> AdvancedUser:
        repo = AdvancedUserRepository(session=db_session)
        return await repo.get_one(id=user_id, with_for_update=True)


    async def lock_user_without_waiting(db_session: AsyncSession, user_id: int) -> AdvancedUser:
        repo = AdvancedUserRepository(session=db_session)
        return await repo.get_one(
            id=user_id,
            with_for_update={"nowait": True, "of": AdvancedUser.id},
        )

Deleting Rows by Condition
--------------------------

Call ``delete_where`` to delete matching rows directly by SQL predicate without loading every row first:

.. code-block:: python

    async def purge_unpublished_drafts(db_session: AsyncSession) -> Sequence[AdvancedPost]:
        repo = AdvancedPostRepository(session=db_session)
        return await repo.delete_where(AdvancedPost.published.is_(False))

Handling Database Exceptions
----------------------------

Database drivers raise backend-specific DBAPI error codes when unique or foreign-key constraints fail. Repositories translate native constraint errors across PostgreSQL, CockroachDB, SQLite, MySQL, MariaDB, DuckDB, Oracle, SQL Server, and Spanner into typed Python exceptions:

.. code-block:: python

    from typing import Optional
    from advanced_alchemy.exceptions import DuplicateKeyError, ForeignKeyError, NotFoundError


    async def safe_assign_role(
        db_session: AsyncSession,
        user_id: int,
        role_id: int,
    ) -> Optional[AdvancedUserRole]:
        repo = AdvancedUserRoleRepository(session=db_session)
        try:
            return await repo.add(AdvancedUserRole(user_id=user_id, role_id=role_id), auto_commit=True)
        except (DuplicateKeyError, ForeignKeyError, NotFoundError):
            await db_session.rollback()
            return None
