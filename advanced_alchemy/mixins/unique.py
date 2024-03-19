from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

from sqlalchemy import ColumnElement, select

from advanced_alchemy.exceptions import wrap_sqlalchemy_exception

if TYPE_CHECKING:
    from collections.abc import Hashable
    from typing import Iterator

    from sqlalchemy import Select
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.ext.asyncio.scoping import async_scoped_session
    from sqlalchemy.orm import Session
    from sqlalchemy.orm.scoping import scoped_session
    from typing_extensions import Self


class UniqueMixin:
    """Mixin for instantiating objects while ensuring uniqueness on some field(s).

    This is a slightly modified implementation derived from https://github.com/sqlalchemy/sqlalchemy/wiki/UniqueObject
    """

    @classmethod
    @contextmanager
    def _prevent_autoflush(
        cls,
        session: AsyncSession | async_scoped_session[AsyncSession] | Session | scoped_session[Session],
    ) -> Iterator[None]:
        with session.no_autoflush, wrap_sqlalchemy_exception():
            yield

    @classmethod
    def _check_uniqueness(
        cls,
        cache: dict[tuple[type[Self], Hashable], Self] | None,
        session: AsyncSession | async_scoped_session[AsyncSession] | Session | scoped_session[Session],
        key: tuple[type[Self], Hashable],
        *args: Any,
        **kwargs: Any,
    ) -> tuple[dict[tuple[type[Self], Hashable], Self], Select[tuple[Self]], Self | None]:
        if cache is None:
            cache = {}
            setattr(session, "_unique_cache", cache)
        statement = select(cls).where(cls.unique_filter(*args, **kwargs)).limit(2)
        return cache, statement, cache.get(key)

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
            *args (Any): Values used to instantiate the instance if no duplicate exists
            **kwargs (Any): Values used to instantiate the instance if no duplicate exists

        Returns:
            Self: The unique object instance.
        """
        key = cls, cls.unique_hash(*args, **kwargs)
        cache, statement, obj = cls._check_uniqueness(
            getattr(session, "_unique_cache", None),
            session,
            key,
            *args,
            **kwargs,
        )
        if obj:
            return obj
        with cls._prevent_autoflush(session):
            if (obj := (await session.execute(statement)).scalar_one_or_none()) is None:
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
            *args (Any): Values used to instantiate the instance if no duplicate exists
            **kwargs (Any): Values used to instantiate the instance if no duplicate exists

        Returns:
            Self: The unique object instance.
        """
        key = cls, cls.unique_hash(*args, **kwargs)
        cache, statement, obj = cls._check_uniqueness(
            getattr(session, "_unique_cache", None),
            session,
            key,
            *args,
            **kwargs,
        )
        if obj:
            return obj
        with cls._prevent_autoflush(session):
            if (obj := session.execute(statement).scalar_one_or_none()) is None:
                session.add(obj := cls(*args, **kwargs))
        cache[key] = obj
        return obj

    @classmethod
    def unique_hash(cls, *args: Any, **kwargs: Any) -> Hashable:  # noqa: ARG003
        """Generate a unique key based on the provided arguments.

        This method should be implemented in the subclass.


        Args:
            *args (Any): Values passed to the alternate classmethod constructors
            **kwargs (Any): Values passed to the alternate classmethod constructors

        Raises:
            NotImplementedError: If not implemented in the subclass.

        Returns:
            Hashable: Any hashable object.
        """
        msg = "Implement this in subclass"
        raise NotImplementedError(msg)

    @classmethod
    def unique_filter(cls, *args: Any, **kwargs: Any) -> ColumnElement[bool]:  # noqa: ARG003
        """Generate a filter condition for ensuring uniqueness.

        This method should be implemented in the subclass.


        Args:
            *args (Any): Values passed to the alternate classmethod constructors
            **kwargs (Any): Values passed to the alternate classmethod constructors

        Raises:
            NotImplementedError: If not implemented in the subclass.

        Returns:
            ColumnElement[bool]: Filter condition to establish the uniqueness.
        """
        msg = "Implement this in subclass"
        raise NotImplementedError(msg)
