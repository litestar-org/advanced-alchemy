import datetime
from abc import ABC, abstractmethod
from copy import deepcopy
from typing import TYPE_CHECKING, Any, Final, Generic, Optional, TypeVar, Union, cast

from litestar.exceptions import ImproperlyConfiguredException
from litestar.middleware.session.server_side import ServerSideSessionBackend, ServerSideSessionConfig
from sqlalchemy import (
    BooleanClauseList,
    Dialect,
    Index,
    LargeBinary,
    ScalarResult,
    String,
    UniqueConstraint,
    delete,
    func,
    select,
)
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, Session, declarative_mixin, declared_attr, mapped_column

from advanced_alchemy.base import UUIDv7Base
from advanced_alchemy.extensions.litestar.plugins.init import (
    SQLAlchemyAsyncConfig,
    SQLAlchemySyncConfig,
)
from advanced_alchemy.operations import OnConflictUpsert
from advanced_alchemy.utils.sync_tools import async_

if TYPE_CHECKING:
    from litestar.stores.base import Store
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm.decl_base import _TableArgsType as TableArgsType  # pyright: ignore[reportPrivateUsage]
    from sqlalchemy.sql import Select
    from sqlalchemy.sql.elements import BooleanClauseList

SQLAlchemyConfig = Union[SQLAlchemyAsyncConfig, SQLAlchemySyncConfig]
SQLAlchemyConfigT = TypeVar("SQLAlchemyConfigT", bound=SQLAlchemyConfig)
SessionModelT = TypeVar("SessionModelT", bound="SessionModelMixin")

# Session ID field limit as defined in the database schema
SESSION_ID_MAX_LENGTH = 255

# PostgreSQL version supporting MERGE (same as store.py)
_POSTGRES_VERSION_SUPPORTING_MERGE: Final = 15

# Temporary toggle to disable PostgreSQL MERGE due to locking concerns
_DISABLE_POSTGRES_MERGE: Final = True


@declarative_mixin
class SessionModelMixin(UUIDv7Base):
    """Mixin for session storage."""

    __abstract__ = True

    @declared_attr.directive
    @classmethod
    def __table_args__(cls) -> "TableArgsType":
        return (
            UniqueConstraint(
                cls.session_id,
                name=f"uq_{cls.__tablename__}_session_id",
            ).ddl_if(callable_=cls._create_unique_session_id_constraint),
            Index(
                f"ix_{cls.__tablename__}_session_id_unique",
                cls.session_id,
                unique=True,
            ).ddl_if(callable_=cls._create_unique_session_id_index),
        )

    @declared_attr
    def session_id(cls) -> Mapped[str]:
        return mapped_column(String(length=255), nullable=False)

    @declared_attr
    def data(cls) -> Mapped[bytes]:
        return mapped_column(LargeBinary, nullable=False)

    @declared_attr
    def expires_at(cls) -> Mapped[datetime.datetime]:
        return mapped_column(index=True)

    @classmethod
    def _create_unique_session_id_index(cls, *_: Any, **kwargs: Any) -> bool:
        dialect_name = kwargs.get("dialect", {}).name if "dialect" in kwargs else ""
        return bool("spanner" in dialect_name.lower())

    @classmethod
    def _create_unique_session_id_constraint(cls, *_: Any, **kwargs: Any) -> bool:
        dialect_name = kwargs.get("dialect", {}).name if "dialect" in kwargs else ""
        return "spanner" not in dialect_name.lower()

    @hybrid_property
    def is_expired(self) -> bool:  # pyright: ignore
        """Boolean indicating if the session has expired.

        Returns:
            `True` if the session has expired, otherwise `False`
        """
        return datetime.datetime.now(datetime.timezone.utc) > self.expires_at

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
          SQLAlchemyPlugin.
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
        self._model = model
        self._config = config
        self._alchemy = alchemy_config

    def __deepcopy__(self, memo: dict[int, Any]) -> "SQLAlchemySessionBackendBase[SQLAlchemyConfigT]":
        """Custom deepcopy implementation to handle unpicklable SQLAlchemy objects."""
        # Create a new instance with the same configuration
        cls = self.__class__
        # Create a shallow copy first
        new_obj = cls.__new__(cls)
        memo[id(self)] = new_obj

        # Copy the ServerSideSessionConfig safely - it should be serializable
        try:
            new_obj._config = deepcopy(self.config, memo)  # noqa: SLF001
        except (TypeError, AttributeError):
            # If config can't be deep-copied, just reference the original
            new_obj._config = self.config  # noqa: SLF001

        # Model classes are safe to reference directly
        new_obj._model = self.model  # noqa: SLF001

        # SQLAlchemy config contains unpicklable objects, so we reference the original
        # This is safe because configs are typically shared and immutable
        new_obj._alchemy = self.alchemy  # noqa: SLF001

        return new_obj

    def _select_session_obj(self, session_id: str) -> "Select[tuple[SessionModelMixin]]":
        return select(self._model).where(self._model.session_id == session_id)

    def _update_session_expiry(self, session_obj: "SessionModelMixin") -> None:
        session_obj.expires_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
            seconds=self.config.max_age
        )

    @staticmethod
    def supports_merge(dialect: "Optional[Dialect]" = None, force_disable_merge: bool = False) -> bool:
        """Check if the dialect supports MERGE statements for upserts."""
        return bool(
            dialect
            and (
                (
                    dialect.server_version_info is not None
                    and dialect.server_version_info[0] >= _POSTGRES_VERSION_SUPPORTING_MERGE
                    and dialect.name == "postgresql"
                    and not _DISABLE_POSTGRES_MERGE  # Temporary PostgreSQL MERGE disable
                )
                or dialect.name == "oracle"
            )
            and not force_disable_merge
        )

    @staticmethod
    def supports_upsert(dialect: "Optional[Dialect]" = None, force_disable_upsert: bool = False) -> bool:
        """Check if the dialect supports native upsert operations."""
        return bool(
            dialect
            and (dialect.name in {"postgresql", "cockroachdb", "sqlite", "mysql", "mariadb", "duckdb"})
            and not force_disable_upsert
        )

    @abstractmethod
    async def delete_expired(self) -> None:
        """Delete all expired sessions from the database."""

    @property
    def model(self) -> "type[SessionModelMixin]":
        return self._model

    @property
    def config(self) -> "ServerSideSessionConfig":
        return self._config

    @config.setter
    def config(self, value: "ServerSideSessionConfig") -> None:
        self._config = value

    @property
    def alchemy(self) -> "SQLAlchemyConfigT":
        return self._alchemy

    @property
    def _backend_class(self) -> "type[Union[SQLAlchemySyncSessionBackend, SQLAlchemyAsyncSessionBackend]]":
        """Return either `SQLAlchemyBackend` or `AsyncSQLAlchemyBackend`, depending on the engine type configured in the
        `SQLAlchemyPlugin`
        """
        if isinstance(self.alchemy, SQLAlchemyAsyncConfig):
            return SQLAlchemyAsyncSessionBackend
        return SQLAlchemySyncSessionBackend


class SQLAlchemyAsyncSessionBackend(SQLAlchemySessionBackendBase[SQLAlchemyAsyncConfig]):
    """Asynchronous SQLAlchemy backend."""

    async def _get_session_obj(self, *, db_session: "AsyncSession", session_id: str) -> Optional[SessionModelMixin]:
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
        session_id = session_id[:SESSION_ID_MAX_LENGTH] if len(session_id) > SESSION_ID_MAX_LENGTH else session_id

        async with self.alchemy.get_session() as db_session:
            session_obj = await self._get_session_obj(db_session=db_session, session_id=session_id)
            if session_obj:
                if not session_obj.is_expired:
                    data = session_obj.data
                    self._update_session_expiry(session_obj)
                    await db_session.commit()
                    return data
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
        session_id = session_id[:SESSION_ID_MAX_LENGTH] if len(session_id) > SESSION_ID_MAX_LENGTH else session_id
        expires_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=self.config.max_age)

        async with self.alchemy.get_session() as db_session:
            if db_session.bind is None:  # pyright: ignore[reportUnnecessaryComparison]
                msg = "Database connection is not available"  # type: ignore[unreachable]
                raise ImproperlyConfiguredException(msg)
            dialect = db_session.bind.dialect
            dialect_name = dialect.name

            values = {
                "session_id": session_id,
                "data": data,
                "expires_at": expires_at,
            }
            conflict_columns = ["session_id"]
            update_columns = ["data", "expires_at"]

            if OnConflictUpsert.supports_native_upsert(dialect_name):
                upsert_stmt = OnConflictUpsert.create_upsert(
                    table=self._model.__table__,  # type: ignore[arg-type]
                    values=values,
                    conflict_columns=conflict_columns,
                    update_columns=update_columns,
                    dialect_name=dialect_name,
                    validate_identifiers=False,
                )
                await db_session.execute(upsert_stmt)

            elif self.supports_merge(dialect):
                merge_stmt, additional_params = OnConflictUpsert.create_merge_upsert(
                    table=self._model.__table__,  # type: ignore[arg-type]
                    values=values,
                    conflict_columns=conflict_columns,
                    update_columns=update_columns,
                    dialect_name=dialect_name,
                    validate_identifiers=False,
                )
                # Merge additional Oracle parameters with original values
                merge_values = {**values, **additional_params}
                await db_session.execute(merge_stmt, merge_values)

            else:
                # Fallback logic: Check existence, then update or insert
                session_obj = await self._get_session_obj(db_session=db_session, session_id=session_id)
                if not session_obj:
                    session_obj = self._model(session_id=session_id)
                    db_session.add(session_obj)
                session_obj.data = data
                session_obj.expires_at = expires_at

            await db_session.commit()

    async def delete(self, /, session_id: str, store: "Store") -> None:
        """Delete the data associated with `session_id`. Fails silently if no such session-ID exists.

        Args:
            session_id: The session-ID
            store: The store to delete the session from (not used in this backend)
        """
        session_id = session_id[:SESSION_ID_MAX_LENGTH] if len(session_id) > SESSION_ID_MAX_LENGTH else session_id

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

    def _get_session_obj(self, *, db_session: "Session", session_id: str) -> "Optional[SessionModelMixin]":
        return db_session.scalars(self._select_session_obj(session_id)).one_or_none()

    def _get_sync(self, session_id: str) -> Optional[bytes]:
        session_id = session_id[:SESSION_ID_MAX_LENGTH] if len(session_id) > SESSION_ID_MAX_LENGTH else session_id

        with self.alchemy.get_session() as db_session:
            session_obj = self._get_session_obj(db_session=db_session, session_id=session_id)

            if session_obj:
                if not session_obj.is_expired:
                    data = session_obj.data
                    self._update_session_expiry(session_obj)
                    db_session.commit()
                    return data
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
        session_id = session_id[:SESSION_ID_MAX_LENGTH] if len(session_id) > SESSION_ID_MAX_LENGTH else session_id
        expires_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=self.config.max_age)

        with self.alchemy.get_session() as db_session:
            if db_session.bind is None:
                msg = "Database connection is not available"
                raise ImproperlyConfiguredException(msg)
            dialect = db_session.bind.dialect
            dialect_name = dialect.name

            values = {
                "session_id": session_id,
                "data": data,
                "expires_at": expires_at,
            }
            conflict_columns = ["session_id"]
            update_columns = ["data", "expires_at"]

            if OnConflictUpsert.supports_native_upsert(dialect_name):
                upsert_stmt = OnConflictUpsert.create_upsert(
                    table=self._model.__table__,  # type: ignore[arg-type]
                    values=values,
                    conflict_columns=conflict_columns,
                    update_columns=update_columns,
                    dialect_name=dialect_name,
                    validate_identifiers=False,
                )
                db_session.execute(upsert_stmt)

            elif self.supports_merge(dialect):
                merge_stmt, additional_params = OnConflictUpsert.create_merge_upsert(
                    table=self._model.__table__,  # type: ignore[arg-type]
                    values=values,
                    conflict_columns=conflict_columns,
                    update_columns=update_columns,
                    dialect_name=dialect_name,
                    validate_identifiers=False,
                )
                # Merge additional Oracle parameters with original values
                merge_values = {**values, **additional_params}
                db_session.execute(merge_stmt, merge_values)

            else:
                # Fallback logic: Check existence, then update or insert
                session_obj = self._get_session_obj(db_session=db_session, session_id=session_id)
                if not session_obj:
                    session_obj = self._model(session_id=session_id)
                    db_session.add(session_obj)
                session_obj.data = data
                session_obj.expires_at = expires_at

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
        session_id = session_id[:SESSION_ID_MAX_LENGTH] if len(session_id) > SESSION_ID_MAX_LENGTH else session_id

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
