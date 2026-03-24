=====================
Advanced Repository
=====================

This section covers advanced repository features including composite primary keys and row locking.

.. _composite-primary-keys:

Composite Primary Keys
----------------------

Advanced Alchemy supports models with composite primary keys. For these models, the repository methods accept several formats for identifying records.

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

**Tuple Format**

Pass primary key values as a tuple in the order they are defined on the model.

.. code-block:: python

    async def get_user_role_by_tuple(
        db_session: AsyncSession,
        user_id: int,
        role_id: int,
    ) -> AdvancedUserRole:
        repository = AdvancedUserRoleRepository(session=db_session)
        return await repository.get((user_id, role_id))

**Dict Format**

Pass primary key values as a dictionary with column names as keys. This is more explicit and avoids ordering issues.

.. code-block:: python

    async def get_user_role_by_mapping(
        db_session: AsyncSession,
        user_id: int,
        role_id: int,
    ) -> AdvancedUserRole:
        repository = AdvancedUserRoleRepository(session=db_session)
        return await repository.get({"user_id": user_id, "role_id": role_id})

**Bulk Operations**

You can use sequences of tuples or dicts for bulk operations like ``delete_many``.

.. code-block:: python

    async def delete_user_roles(
        db_session: AsyncSession,
        role_ids: Sequence[dict[str, int]],
    ) -> Sequence[AdvancedUserRole]:
        repository = AdvancedUserRoleRepository(session=db_session)
        return await repository.delete_many(list(role_ids))

Row Locking (FOR UPDATE)
------------------------

.. versionadded:: 1.9.0

The ``get_one`` and ``get_one_or_none`` methods support a ``with_for_update`` parameter, allowing you to emit a ``SELECT ... FOR UPDATE`` query for row-level locking.

.. code-block:: python

    async def get_user_for_update(db_session: AsyncSession, user_id: int) -> AdvancedUser:
        repository = AdvancedUserRepository(session=db_session)
        return await repository.get_one(id=user_id, with_for_update=True)


    async def get_user_for_update_nowait(db_session: AsyncSession, user_id: int) -> AdvancedUser:
        repository = AdvancedUserRepository(session=db_session)
        return await repository.get_one(
            id=user_id,
            with_for_update={"nowait": True, "of": AdvancedUser.id},
        )

Custom DELETE WHERE
--------------------

For deleting multiple records matching a specific criteria:

.. code-block:: python

    async def delete_unpublished_posts(db_session: AsyncSession) -> Sequence[AdvancedPost]:
        repository = AdvancedPostRepository(session=db_session)
        return await repository.delete_where(AdvancedPost.published.is_(False))
