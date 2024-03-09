from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import ColumnElement, select

if TYPE_CHECKING:
    from collections.abc import Hashable

    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.ext.asyncio.scoping import async_scoped_session
    from sqlalchemy.orm import Session
    from sqlalchemy.orm.scoping import scoped_session
    from typing_extensions import Self


class UniqueMixin:
    """Mixin for instantiating objects while ensuring uniqueness on some field(s)."""

    @classmethod
    async def as_unique_async(
        cls,
        session: AsyncSession | async_scoped_session[AsyncSession],
        *args: Any,
        **kwargs: Any,
    ) -> Self:
        """Instantiate and return a unique object within the provided session based on the given arguments.

        If an object with the same unique identifier already exists in the session, it is returned from the cache.

        Args:
            session (AsyncSession | async_scoped_session[AsyncSession]): SQLAlchemy async session
            *args (Any): Columns belonging to a table
            **kwargs (Any): Columns belonging to a table

        Returns:
            Self: The unique object instance.
        """
        key = cls, cls.unique_hash(*args, **kwargs)
        cache: dict[tuple[type[Self], Hashable], Self] | None = getattr(session, "_unique_cache", None)
        if cache is None:
            cache = {}
            setattr(session, "_unique_cache", cache)
        if obj := cache.get(key):
            return obj

        with session.no_autoflush:
            statement = select(cls).where(cls.unique_filter(*args, **kwargs)).limit(1)
            if (obj := (await session.scalars(statement)).first()) is None:
                session.add(obj := cls(*args, **kwargs))
        cache[key] = obj
        return obj

    @classmethod
    def as_unique_sync(
        cls,
        session: Session | scoped_session[Session],
        *args: Any,
        **kwargs: Any,
    ) -> Self:
        """Instantiate and return a unique object within the provided session based on the given arguments.

        If an object with the same unique identifier already exists in the session, it is returned from the cache.


        Args:
            session (Session | scoped_session[Session]): SQLAlchemy sync session
            *args (Any): Columns belonging to a table
            **kwargs (Any): Columns belonging to a table

        Returns:
            Self: The unique object instance.
        """
        key = cls, cls.unique_hash(*args, **kwargs)
        cache: dict[tuple[type[Self], Hashable], Self] | None = getattr(session, "_unique_cache", None)
        if cache is None:
            cache = {}
            setattr(session, "_unique_cache", cache)
        if obj := cache.get(key):
            return obj

        with session.no_autoflush:
            statement = select(cls).where(cls.unique_filter(*args, **kwargs)).limit(1)
            if (obj := (session.scalars(statement)).first()) is None:
                session.add(obj := cls(*args, **kwargs))
        cache[key] = obj
        return obj

    @classmethod
    def unique_hash(cls, *arg: Any, **kw: Any) -> Hashable:  # noqa: ARG003
        """Generate a unique key based on the provided arguments.

        This method should be implemented in the subclass.

        Raises:
            NotImplementedError: If not implemented in the subclass.

        Returns:
            Hashable: Any hashable object.
        """
        msg = "Implement this in subclass"
        raise NotImplementedError(msg)

    @classmethod
    def unique_filter(cls, *arg: Any, **kw: Any) -> ColumnElement[bool]:  # noqa: ARG003
        """Generate a filter condition for ensuring uniqueness.

        This method should be implemented in the subclass.

        Raises:
            NotImplementedError: If not implemented in the subclass.

        Returns:
            ColumnElement[bool]: Filter condition to establish the uniqueness.
        """
        msg = "Implement this in subclass"
        raise NotImplementedError(msg)
