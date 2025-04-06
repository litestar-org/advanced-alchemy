import datetime
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Generic, Optional, TypeVar, Union, cast

from litestar.middleware.session.server_side import ServerSideSessionBackend, ServerSideSessionConfig
from sqlalchemy import (
    BooleanClauseList,
    LargeBinary,
    ScalarResult,
    String,
    UniqueConstraint,
    delete,
    func,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, declarative_mixin, mapped_column
from sqlalchemy.orm import Session as SyncSession

from advanced_alchemy.base import UUIDv7Base
from advanced_alchemy.extensions.litestar.plugins.init import (
    SQLAlchemyAsyncConfig,
    SQLAlchemySyncConfig,
)
from advanced_alchemy.utils.sync_tools import async_
from advanced_alchemy.utils.time import get_utc_now

if TYPE_CHECKING:
    from litestar.stores.base import Store
    from sqlalchemy.sql import Select
    from sqlalchemy.sql.elements import BooleanClauseList

SQLAlchemyConfig = Union[SQLAlchemyAsyncConfig, SQLAlchemySyncConfig]
SQLAlchemyConfigT = TypeVar("SQLAlchemyConfigT", bound=SQLAlchemyConfig)
SessionModelT = TypeVar("SessionModelT", bound="SessionModelMixin")


@declarative_mixin
class SessionModelMixin(UUIDv7Base):
    """Mixin for session storage."""

    __table_args__ = (UniqueConstraint("session_id", name="uix_session_id"),)

    session_id: Mapped[str] = mapped_column(String(length=255), nullable=False, index=True)
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    expires_at: Mapped[datetime.datetime] = mapped_column(index=True)

    @hybrid_property
    def is_expired(self) -> bool:  # pyright: ignore
        """Boolean indicating if the session has expired.

        Returns:
            `True` if the session has expired, otherwise `False`
        """
        return get_utc_now() > self.expires_at

    @is_expired.expression  # type: ignore[no-redef]
    def is_expired(cls) -> "BooleanClauseList":  # noqa: N805
        """SQL-Expression to check if the session has expired.

        Returns:
            SQL-Expression to check if the session has expired.
        """
        return cast("BooleanClauseList", func.now() > cls.expires_at)


class SQLAlchemySessionBackendBase(ServerSideSessionBackend, ABC, Generic[SQLAlchemyConfigT]):
    """Session backend to store data in a database with SQLAlchemy. Works with both sync and async engines.

    Notes:
        - Requires `sqlalchemy` which needs to be installed separately, and a configured
        [SQLAlchemyPlugin][starlite.plugins.sql_alchemy.SQLAlchemyPlugin].
    """

    __slots__ = ("_model", "_session_maker")

    def __init__(
        self,
        config: "ServerSideSessionConfig",
        alchemy_config: "SQLAlchemyConfigT",
        model: "type[SessionModelMixin]",
    ) -> None:
        """Initialize `BaseSQLAlchemyBackend`.

        Args:
            config: An instance of `SQLAlchemyBackendConfig`
            alchemy_config: An instance of `SQLAlchemyConfig`
            model: A mapped model subclassing `SessionModelMixin`
        """
        super().__init__(config=config)
        self._model = model
        self._config = config
        self._alchemy = alchemy_config

    def _select_session_obj(self, session_id: str) -> "Select[tuple[SessionModelMixin]]":
        return select(self._model).where(self._model.session_id == session_id)

    def _update_session_expiry(self, session_obj: SessionModelMixin) -> None:
        session_obj.expires_at = get_utc_now() + datetime.timedelta(seconds=self.config.max_age)

    @abstractmethod
    async def delete_expired(self) -> None:
        """Delete all expired sessions from the database."""

    @property
    def model(self) -> "type[SessionModelMixin]":
        return self._model

    @property
    def config(self) -> "ServerSideSessionConfig":
        return self._config

    @property
    def alchemy(self) -> "SQLAlchemyConfigT":
        return self._alchemy

    @property
    def _backend_class(self) -> "type[Union[SQLAlchemySyncSessionBackend, SQLAlchemyAsyncSessionBackend]]":  # type: ignore[override]
        """Return either `SQLAlchemyBackend` or `AsyncSQLAlchemyBackend`, depending on the engine type configured in the
        `SQLAlchemyPlugin`
        """
        if isinstance(self.alchemy, SQLAlchemyAsyncConfig):
            return SQLAlchemyAsyncSessionBackend
        return SQLAlchemySyncSessionBackend


class SQLAlchemyAsyncSessionBackend(SQLAlchemySessionBackendBase[SQLAlchemyAsyncConfig]):
    """Asynchronous SQLAlchemy backend."""

    async def _get_session_obj(self, *, db_session: AsyncSession, session_id: str) -> Optional[SessionModelMixin]:
        return (
            cast(
                "ScalarResult[Optional[SessionModelMixin]]",
                await db_session.scalars(self._select_session_obj(session_id)),
            )
        ).one_or_none()

    async def get(self, /, session_id: str, store: "Store") -> Optional[bytes]:
        """Retrieve data associated with `session_id`.

        Args:
            session_id: The session-ID
            store: The store to get the session from (not used in this backend)

        Returns:
            The session data, if existing, otherwise `None`.
        """
        async with self.alchemy.get_session() as db_session:
            session_obj = await self._get_session_obj(db_session=db_session, session_id=session_id)
            if session_obj:
                if not session_obj.is_expired:
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
        async with self.alchemy.get_session() as db_session:
            session_obj = await self._get_session_obj(db_session=db_session, session_id=session_id)
            if not session_obj:
                session_obj = self._model(session_id=session_id)
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
        async with self.alchemy.get_session() as db_session:
            await db_session.execute(delete(self._model).where(self._model.session_id == session_id))
            await db_session.commit()

    async def delete_all(self, /, store: "Store") -> None:
        """Delete all session data."""
        async with self.alchemy.get_session() as db_session:
            await db_session.execute(delete(self._model))
            await db_session.commit()

    async def delete_expired(self) -> None:
        """Delete all expired session from the database."""
        async with self.alchemy.get_session() as db_session:
            await db_session.execute(delete(self._model).where(self._model.is_expired))
            await db_session.commit()


class SQLAlchemySyncSessionBackend(SQLAlchemySessionBackendBase[SQLAlchemySyncConfig]):
    """Synchronous SQLAlchemy backend."""

    def _get_session_obj(self, *, db_session: SyncSession, session_id: str) -> Optional[SessionModelMixin]:
        return db_session.scalars(self._select_session_obj(session_id)).one_or_none()

    def _get_sync(self, session_id: str) -> Optional[bytes]:
        with self.alchemy.get_session() as db_session:
            session_obj = self._get_session_obj(db_session=db_session, session_id=session_id)

            if session_obj:
                if not session_obj.is_expired:
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
        with self.alchemy.get_session() as db_session:
            session_obj = self._get_session_obj(db_session=db_session, session_id=session_id)

            if not session_obj:
                session_obj = self._model(session_id=session_id)
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
        with self.alchemy.get_session() as db_session:
            db_session.execute(delete(self._model).where(self._model.session_id == session_id))
            db_session.commit()

    async def delete(self, /, session_id: str, store: "Store") -> None:
        """Delete the data associated with `session_id`. Fails silently if no such session-ID exists.

        Args:
            session_id: The session-ID
            store: The store to delete the session from
        """
        return await async_(self._delete_sync)(session_id)

    def _delete_all_sync(self) -> None:
        with self.alchemy.get_session() as db_session:
            db_session.execute(delete(self._model))
            db_session.commit()

    async def delete_all(self) -> None:
        """Delete all session data."""
        return await async_(self._delete_all_sync)()

    def _delete_expired_sync(self) -> None:
        with self.alchemy.get_session() as db_session:
            db_session.execute(delete(self._model).where(self._model.is_expired))
            db_session.commit()

    async def delete_expired(self) -> None:
        """Delete all expired session from the database."""
        return await async_(self._delete_expired_sync)()
