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
    @classmethod
    async def as_unique_async(
        cls,
        session: AsyncSession | async_scoped_session[AsyncSession],
        *args: Any,
        **kwargs: Any,
    ) -> Self:
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
        msg = "Implement this in subclass"
        raise NotImplementedError(msg)

    @classmethod
    def unique_filter(cls, *arg: Any, **kw: Any) -> ColumnElement[bool]:  # noqa: ARG003
        msg = "Implement this in subclass"
        raise NotImplementedError(msg)
