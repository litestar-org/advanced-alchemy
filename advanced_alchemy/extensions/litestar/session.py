import datetime
import sys
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Generic, Optional, TypeVar, Union, cast

import sqlalchemy as sa
from litestar.middleware.session.server_side import ServerSideSessionBackend, ServerSideSessionConfig
from sqlalchemy import ScalarResult
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, declarative_mixin, mapped_column, registry
from sqlalchemy.orm import Session as SyncSession

from advanced_alchemy.base import BigIntBase
from advanced_alchemy.extensions.litestar.plugins.init import (
    SQLAlchemyAsyncConfig,
    SQLAlchemySyncConfig,
)
from advanced_alchemy.utils.sync_tools import async_

if TYPE_CHECKING:
    from litestar.stores.base import Store
    from sqlalchemy.sql import Select
    from sqlalchemy.sql.elements import BooleanClauseList
SQLAlchemyConfig = Union[SQLAlchemyAsyncConfig, SQLAlchemySyncConfig]
SQLAlchemyConfigT = TypeVar("SQLAlchemyConfigT", bound=SQLAlchemyConfig)
SessionModelT = TypeVar("SessionModelT", bound="SessionModelMixin")


class SQLAlchemyBackendConfig(ServerSideSessionConfig):
    """Configuration for `SQLAlchemyBackend` and `AsyncSQLAlchemyBackend`"""

    model: "type[SessionModelMixin]"
    alchemy_config: "SQLAlchemyConfig"

    def __post_init__(self) -> None:
        if not self.model:
            msg = "A valid session model is required"
            raise ValueError(msg)
        if not self.alchemy_config:
            msg = "A valid Advanced Alchemy config is required"
            raise ValueError(msg)

    @property
    def _backend_class(self) -> "type[Union[ServerSideSessionSyncBackend, ServerSideSessionAsyncBackend]]":  # type: ignore[override]
        """Return either `SQLAlchemyBackend` or `AsyncSQLAlchemyBackend`, depending on the engine type configured in the
        `SQLAlchemyPlugin`
        """
        if isinstance(self.alchemy_config, SQLAlchemyAsyncConfig):
            return ServerSideSessionAsyncBackend
        return ServerSideSessionSyncBackend


def _get_utc_now() -> datetime.datetime:  # pragma: no cover
    if sys.version_info >= (3, 11):
        return datetime.datetime.now(datetime.UTC)
    return datetime.datetime.utcnow().replace(tzinfo=None)  # pyright: ignore  # noqa: DTZ003


@declarative_mixin
class SessionModelMixin:
    """Mixin for session storage."""

    session_id: Mapped[str] = mapped_column(sa.String(length=255), nullable=False, unique=True, index=True)  # pyright: ignore
    data: Mapped[bytes] = mapped_column(sa.LargeBinary, nullable=False)  # pyright: ignore
    expires: Mapped[datetime.datetime]

    @hybrid_property
    def expired(self) -> bool:  # pyright: ignore
        """Boolean indicating if the session has expired.

        Returns:
            `True` if the session has expired, otherwise `False`
        """
        return _get_utc_now() > self.expires

    @expired.expression  # type: ignore[no-redef]
    def expired(cls) -> "BooleanClauseList":  # noqa: N805
        """SQL-Expression to check if the session has expired.

        Returns:
            SQL-Expression to check if the session has expired.
        """
        return _get_utc_now() > cls.expires  # pyright: ignore


class UserSession(BigIntBase, SessionModelMixin):
    """Session storage model."""

    __tablename__ = "session"


def create_session_model(base: type[Any] = BigIntBase, table_name: str = "session") -> type[SessionModelMixin]:
    """Dynamically generate a session storage model and register it with the declarative base.

    Args:
        base: SQLAlchemy declarative base
        table_name: Alternative table name

    Returns:
        A mapped model subclassing `base` and `SessionModelMixin`
    """

    class UserSession(base, SessionModelMixin):  # type: ignore
        __tablename__ = table_name

    return UserSession


def register_session_model(base: Union[registry, Any], model: type[SessionModelT]) -> type[SessionModelT]:
    """Map and register a pre-existing model subclassing `SessionModelMixin` with a declarative base or registry.

    Args:
        base: Either a `orm.registry` or `DeclarativeBase`
        model: SQLAlchemy model to register

    Returns:
        A mapped model subclassing `SessionModelMixin`, and registered in `registry`
    """
    registry_ = base.registry if not isinstance(base, registry) else base
    return cast("type[SessionModelT]", registry_.map_declaratively(model))


class ServerSideSQLAlchemySessionBackend(
    ServerSideSessionBackend,
    ABC,
    Generic[SQLAlchemyConfigT],
):
    """Session backend to store data in a database with SQLAlchemy. Works with both sync and async engines.

    Notes:
        - Requires `sqlalchemy` which needs to be installed separately, and a configured
        [SQLAlchemyPlugin][starlite.plugins.sql_alchemy.SQLAlchemyPlugin].
    """

    __slots__ = ("_model", "_session_maker")

    def __init__(self, config: "SQLAlchemyBackendConfig") -> None:
        """Initialize `BaseSQLAlchemyBackend`.

        Args:
            config: An instance of `SQLAlchemyBackendConfig`
        """
        super().__init__(config=config)
        self._model = config.model
        self._session_maker = config.alchemy_config.create_session_maker()

    def _create_sa_session(self) -> "Union[AsyncSession, SyncSession]":
        """Create a new SQLAlchemy session.

        Returns:
            A new SQLAlchemy async session.
        """
        return self._session_maker()

    def _select_session_obj(self, session_id: str) -> "Select[tuple[SessionModelMixin]]":
        return sa.select(self._model).where(self._model.session_id == session_id)

    def _update_session_expiry(self, session_obj: SessionModelMixin) -> None:
        session_obj.expires = _get_utc_now() + datetime.timedelta(seconds=self.config.max_age)

    @abstractmethod
    async def delete_expired(self) -> None:
        """Delete all expired sessions from the database."""


class ServerSideSessionAsyncBackend(ServerSideSQLAlchemySessionBackend[SQLAlchemyAsyncConfig]):
    """Asynchronous SQLAlchemy backend."""

    async def _get_session_obj(self, *, db_session: AsyncSession, session_id: str) -> Optional[SessionModelMixin]:
        result = cast(
            "ScalarResult[Optional[SessionModelMixin]]", await db_session.scalars(self._select_session_obj(session_id))
        )
        return result.one_or_none()

    async def get(self, /, session_id: str, store: "Store") -> Optional[bytes]:
        """Retrieve data associated with `session_id`.

        Args:
            session_id: The session-ID
            store: The store to get the session from (not used in this backend)

        Returns:
            The session data, if existing, otherwise `None`.
        """
        async with cast("AsyncSession", self._create_sa_session()) as db_session:
            session_obj = await self._get_session_obj(db_session=db_session, session_id=session_id)
            if session_obj:
                if not session_obj.expired:
                    self._update_session_expiry(session_obj)
                    await db_session.commit()
                    return session_obj.data
                await db_session.delete(session_obj)
                await db_session.commit()
        return None

    async def set(self, /, session_id: str, data: bytes, store: "Store") -> None:
        """Store `data` under the `session_id` for later retrieval.

        If there is already data associated with `session_id`, replace
        it with `data` and reset its expiry time

        Args:
            session_id: The session-ID.
            data: Serialized session data
            store: The store to store the session in (not used in this backend)
        """
        async with cast("AsyncSession", self._create_sa_session()) as db_session:
            session_obj = await self._get_session_obj(db_session=db_session, session_id=session_id)

            if not session_obj:
                session_obj = self._model(session_id=session_id)  # type: ignore[call-arg]
                db_session.add(session_obj)
            session_obj.data = data
            self._update_session_expiry(session_obj)
            await db_session.commit()

    async def delete(self, /, session_id: str, store: "Store") -> None:
        """Delete the data associated with `session_id`. Fails silently if no such session-ID exists.

        Args:
            session_id: The session-ID
            store: The store to delete the session from (not used in this backend)
        """
        async with cast("AsyncSession", self._create_sa_session()) as db_session:
            await db_session.execute(sa.delete(self._model).where(self._model.session_id == session_id))
            await db_session.commit()

    async def delete_all(self, /, store: "Store") -> None:
        """Delete all session data."""
        async with cast("AsyncSession", self._create_sa_session()) as db_session:
            await db_session.execute(sa.delete(self._model))
            await db_session.commit()

    async def delete_expired(self) -> None:
        """Delete all expired session from the database."""
        async with cast("AsyncSession", self._create_sa_session()) as db_session:
            await db_session.execute(sa.delete(self._model).where(self._model.expired))
            await db_session.commit()


class ServerSideSessionSyncBackend(ServerSideSQLAlchemySessionBackend[SQLAlchemySyncConfig]):
    """Synchronous SQLAlchemy backend."""

    def _get_session_obj(self, *, db_session: SyncSession, session_id: str) -> Optional[SessionModelMixin]:
        return db_session.scalars(self._select_session_obj(session_id)).one_or_none()

    def _get_sync(self, session_id: str) -> Optional[bytes]:
        db_session = cast("SyncSession", self._create_sa_session())
        session_obj = self._get_session_obj(db_session=db_session, session_id=session_id)

        if session_obj:
            if not session_obj.expired:
                self._update_session_expiry(session_obj)
                db_session.commit()
                return session_obj.data
            db_session.delete(session_obj)
            db_session.commit()
        return None

    async def get(self, /, session_id: str, store: "Store") -> Optional[bytes]:
        """Retrieve data associated with `session_id`.

        Args:
            session_id: The session-ID
            store: The store to get the session from

        Returns:
            The session data, if existing, otherwise `None`.
        """
        return await async_(self._get_sync)(session_id)

    def _set_sync(self, session_id: str, data: bytes) -> None:
        db_session = cast("SyncSession", self._create_sa_session())
        session_obj = self._get_session_obj(db_session=db_session, session_id=session_id)

        if not session_obj:
            session_obj = self._model(session_id=session_id)  # type: ignore[call-arg]
            db_session.add(session_obj)
        session_obj.data = data
        self._update_session_expiry(session_obj)
        db_session.commit()

    async def set(self, /, session_id: str, data: bytes, store: "Store") -> None:
        """Store `data` under the `session_id` for later retrieval.

        If there is already data associated with `session_id`, replace
        it with `data` and reset its expiry time

        Args:
            session_id: The session-ID
            data: Serialized session data
            store: The store to store the session in
        """
        return await async_(self._set_sync)(session_id, data)

    def _delete_sync(self, session_id: str) -> None:
        db_session = cast("SyncSession", self._create_sa_session())
        db_session.execute(sa.delete(self._model).where(self._model.session_id == session_id))
        db_session.commit()

    async def delete(self, /, session_id: str, store: "Store") -> None:
        """Delete the data associated with `session_id`. Fails silently if no such session-ID exists.

        Args:
            session_id: The session-ID
            store: The store to delete the session from
        """
        return await async_(self._delete_sync)(session_id)

    def _delete_all_sync(self) -> None:
        db_session = cast("SyncSession", self._create_sa_session())
        db_session.execute(sa.delete(self._model))
        db_session.commit()

    async def delete_all(self) -> None:
        """Delete all session data."""
        return await async_(self._delete_all_sync)()

    def _delete_expired_sync(self) -> None:
        db_session = cast("SyncSession", self._create_sa_session())
        db_session.execute(sa.delete(self._model).where(self._model.expired))
        db_session.commit()

    async def delete_expired(self) -> None:
        """Delete all expired session from the database."""
        return await async_(self._delete_expired_sync)()
