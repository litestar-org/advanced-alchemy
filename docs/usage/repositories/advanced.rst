===================
Advanced Repository
===================

Most tables have a single ``id`` column and simple single-row updates. When you run into trickier real-world cases—join tables with two-part keys, concurrent checkout updates, or clearing old drafts in one query—repositories handle them cleanly.

.. _composite-primary-keys:

Composite Primary Keys
----------------------

Some tables identify a row by **two columns together** rather than a single ``id``—for example, a ``UserRole`` table keyed by ``(user_id, role_id)``.

You can pass composite keys to ``get`` or ``delete_many`` as a dictionary (recommended because column names are explicit) or as an ordered tuple:

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

Imagine two requests trying to deduct credits from the same user account at the exact same instant. Passing ``with_for_update=True`` locks that row in the database until your transaction finishes so the second request waits its turn:

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

Need to purge every unpublished draft in one query without loading each post into Python first? Call ``delete_where``:

.. code-block:: python

    async def purge_unpublished_drafts(db_session: AsyncSession) -> Sequence[AdvancedPost]:
        repo = AdvancedPostRepository(session=db_session)
        return await repo.delete_where(AdvancedPost.published.is_(False))

Catching Database Errors Cleanly
--------------------------------

Every database driver raises different low-level error codes when a unique constraint or foreign key fails. Repositories automatically translate native database errors across PostgreSQL, SQLite, MySQL, MariaDB, DuckDB, CockroachDB, Oracle, MSSQL, and Spanner into consistent Python exceptions:

.. code-block:: python

    from advanced_alchemy.exceptions import DuplicateKeyError, ForeignKeyError, NotFoundError


    async def safe_assign_role(
        db_session: AsyncSession,
        user_id: int,
        role_id: int,
    ) -> AdvancedUserRole | None:
        repo = AdvancedUserRoleRepository(session=db_session)
        try:
            return await repo.add(AdvancedUserRole(user_id=user_id, role_id=role_id), auto_commit=True)
        except (DuplicateKeyError, ForeignKeyError, NotFoundError):
            await db_session.rollback()
            return None
