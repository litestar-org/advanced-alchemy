import base64
import datetime
from contextlib import asynccontextmanager, contextmanager
from typing import TYPE_CHECKING, Any, Final, Generic, Optional, TypeVar, Union, cast

from litestar.exceptions import ImproperlyConfiguredException
from litestar.stores.base import NamespacedStore
from litestar.types import Empty, EmptyType
from litestar.utils.empty import value_or_default
from sqlalchemy import (
    BooleanClauseList,
    Dialect,
    Index,
    LargeBinary,
    String,
    UniqueConstraint,
    delete,
    func,
    insert,
    select,
    update,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, Session, declarative_mixin, declared_attr, mapped_column

from advanced_alchemy.base import UUIDv7Base

# Import config types and async_ utility
from advanced_alchemy.extensions.litestar.plugins.init import (
    SQLAlchemyAsyncConfig,
    SQLAlchemySyncConfig,
)
from advanced_alchemy.operations import OnConflictUpsert
from advanced_alchemy.utils.sync_tools import async_

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Generator

    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm.decl_base import _TableArgsType as TableArgsType  # pyright: ignore[reportPrivateUsage]
    from sqlalchemy.sql.elements import BooleanClauseList

SQLAlchemyConfigT = TypeVar("SQLAlchemyConfigT", bound=Union[SQLAlchemyAsyncConfig, SQLAlchemySyncConfig])

__all__ = ("SQLAlchemyStore", "StoreModelMixin")

_POSTGRES_VERSION_SUPPORTING_MERGE: Final = 15

# Temporary toggle to disable PostgreSQL MERGE due to locking concerns
_DISABLE_POSTGRES_MERGE: Final = True


@declarative_mixin
class StoreModelMixin(UUIDv7Base):
    """Mixin for session storage."""

    __abstract__ = True

    @declared_attr.directive
    @classmethod
    def __table_args__(cls) -> "TableArgsType":
        return (
            UniqueConstraint(
                cls.key,
                cls.namespace,
                name=f"uq_{cls.__tablename__}_key_namespace",
            ).ddl_if(callable_=cls._create_unique_store_key_namespace_constraint),
            Index(
                f"ix_{cls.__tablename__}_key_namespace_unique",
                cls.key,
                cls.namespace,
                unique=True,
            ).ddl_if(callable_=cls._create_unique_store_key_namespace_index),
        )

    @declared_attr
    def key(cls) -> Mapped[str]:
        return mapped_column(String(length=255), nullable=False)

    @declared_attr
    def namespace(cls) -> Mapped[str]:
        return mapped_column(String(length=255), nullable=False)

    @declared_attr
    def value(cls) -> Mapped[bytes]:
        return mapped_column(LargeBinary, nullable=False)

    @declared_attr
    def expires_at(cls) -> Mapped[datetime.datetime]:
        return mapped_column(index=True)

    @classmethod
    def _create_unique_store_key_namespace_index(cls, *_: Any, **kwargs: Any) -> bool:
        dialect_name = kwargs.get("dialect", {}).name if "dialect" in kwargs else ""
        return bool("spanner" in dialect_name.lower())

    @classmethod
    def _create_unique_store_key_namespace_constraint(cls, *_: Any, **kwargs: Any) -> bool:
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


class SQLAlchemyStore(NamespacedStore, Generic[SQLAlchemyConfigT]):
    """SQLAlchemy based, thread and process safe asynchronous key/value store.

    Supports both synchronous and asynchronous SQLAlchemy configurations.
    """

    __slots__ = ("_config", "_is_async", "_model", "_session_maker")

    def __init__(
        self,
        config: "SQLAlchemyConfigT",
        model: "type[StoreModelMixin]" = StoreModelMixin,
        namespace: "Optional[Union[str, EmptyType]]" = Empty,
    ) -> None:
        """Initialize :class:`SQLAlchemyStore`.

        Args:
            config: An instance of ``SQLAlchemyAsyncConfig`` or ``SQLAlchemySyncConfig``.
            model: The SQLAlchemy model to use for storing data. Defaults to :class:`StoreItem`.
            namespace: A virtual namespace for keys. If not given, defaults to ``LITESTAR``.
                Namespacing can be explicitly disabled by passing ``None``. This will make
                :meth:`.delete_all` unavailable.
        """
        self._config = config
        self._model = model
        self._is_async = isinstance(config, SQLAlchemyAsyncConfig)
        self.namespace: Optional[str] = value_or_default(namespace, "LITESTAR")

    @asynccontextmanager
    async def _get_async_session(self) -> "AsyncGenerator[AsyncSession, None]":
        if not self._is_async:
            # This should ideally not be called if configured for sync,
            # but provides a safeguard.
            msg = "Store configured for synchronous operation."
            raise ImproperlyConfiguredException(msg)
        async with cast("AsyncSession", self._config.get_session()) as session:
            yield session

    @contextmanager
    def _get_sync_session(self) -> "Generator[Session, None, None]":
        if self._is_async:
            msg = "Store configured for asynchronous operation."
            raise ImproperlyConfiguredException(msg)
        with cast("Session", self._config.get_session()) as session:
            yield session

    @staticmethod
    def supports_merge(dialect: Optional[Dialect] = None, force_disable_merge: bool = False) -> bool:
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
    def supports_upsert(dialect: Optional[Dialect] = None, force_disable_upsert: bool = False) -> bool:
        return bool(
            dialect
            and (dialect.name in {"postgresql", "cockroachdb", "sqlite", "mysql", "mariadb", "duckdb"})
            and not force_disable_upsert
        )

    def _make_key(self, key: str) -> tuple[str, Optional[str]]:
        """Return the key and namespace tuple, handling potential None namespace."""
        return key, self.namespace

    def _decode_base64_value(self, value: Optional[bytes], dialect_name: str) -> Optional[bytes]:
        """Decode base64 encoded value from Spanner if needed.

        Spanner automatically base64-encodes binary data when storing it,
        so we need to decode it when retrieving.
        """
        if value is None or not dialect_name.startswith("spanner"):
            return value

        try:
            return base64.b64decode(value)
        except Exception:  # noqa: BLE001
            return value

    def _set_sync(
        self, key: str, value: Union[bytes, str], expires_in: Optional[Union[int, datetime.timedelta]] = None
    ) -> None:
        """Synchronous implementation for setting a value."""
        db_key, db_namespace = self._make_key(key)
        expires_at: Optional[datetime.datetime] = None
        serialized_value = value if isinstance(value, bytes) else value.encode("utf-8")
        if expires_in is not None:
            delta = expires_in if isinstance(expires_in, datetime.timedelta) else datetime.timedelta(seconds=expires_in)
            expires_at = datetime.datetime.now(datetime.timezone.utc) + delta

        with self._get_sync_session() as session, session.begin():
            if session.bind is None:
                msg = "Database connection is not available"
                raise ImproperlyConfiguredException(msg)
            dialect = session.bind.dialect
            dialect_name = dialect.name

            values = {
                "key": db_key,
                "namespace": db_namespace,
                "value": serialized_value,
                "expires_at": expires_at,
            }
            conflict_columns = ["key", "namespace"]
            update_columns = ["value", "expires_at"]

            if OnConflictUpsert.supports_native_upsert(dialect_name):
                upsert_stmt = OnConflictUpsert.create_upsert(
                    table=self._model.__table__,  # type: ignore[arg-type]
                    values=values,
                    conflict_columns=conflict_columns,
                    update_columns=update_columns,
                    dialect_name=dialect_name,
                    validate_identifiers=False,
                )
                session.execute(upsert_stmt)

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
                session.execute(merge_stmt, merge_values)

            else:
                # Fallback logic: Check existence, then update or insert
                existing = session.execute(
                    select(1).where(self._model.key == db_key, self._model.namespace == db_namespace)
                ).scalar_one_or_none()
                if existing:
                    session.execute(
                        update(self._model)
                        .where(self._model.key == db_key, self._model.namespace == db_namespace)
                        .values(value=serialized_value, expires_at=expires_at)
                    )
                else:
                    session.execute(
                        insert(self._model).values(
                            key=db_key, namespace=db_namespace, value=serialized_value, expires_at=expires_at
                        )
                    )
            session.commit()

    async def _set_async(
        self, key: str, value: Union[bytes, str], expires_in: Optional[Union[int, datetime.timedelta]] = None
    ) -> None:
        """Asynchronous implementation for setting a value."""
        db_key, db_namespace = self._make_key(key)
        serialized_value = value if isinstance(value, bytes) else value.encode("utf-8")
        expires_at: Optional[datetime.datetime] = None
        if expires_in is not None:
            delta = expires_in if isinstance(expires_in, datetime.timedelta) else datetime.timedelta(seconds=expires_in)
            expires_at = datetime.datetime.now(datetime.timezone.utc) + delta

        async with self._get_async_session() as session, session.begin():
            if session.bind is None:  # pyright: ignore[reportUnnecessaryComparison]
                msg = "Database connection is not available"  # type: ignore[unreachable]
                raise ImproperlyConfiguredException(msg)
            dialect = session.bind.dialect
            dialect_name = dialect.name

            values = {
                "key": db_key,
                "namespace": db_namespace,
                "value": serialized_value,
                "expires_at": expires_at,
            }
            conflict_columns = ["key", "namespace"]
            update_columns = ["value", "expires_at"]

            if OnConflictUpsert.supports_native_upsert(dialect_name):
                upsert_stmt = OnConflictUpsert.create_upsert(
                    table=self._model.__table__,  # type: ignore[arg-type]
                    values=values,
                    conflict_columns=conflict_columns,
                    update_columns=update_columns,
                    dialect_name=dialect_name,
                    validate_identifiers=False,
                )
                await session.execute(upsert_stmt)

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
                await session.execute(merge_stmt, merge_values)

            else:
                # Fallback logic: Check existence, then update or insert
                existing_id = (
                    await session.execute(
                        select(self._model.id).where(
                            self._model.key == db_key,
                            self._model.namespace == db_namespace,
                        )
                    )
                ).scalar_one_or_none()
                if existing_id:
                    await session.execute(
                        update(self._model)
                        .where(self._model.id == existing_id)
                        .values(value=serialized_value, expires_at=expires_at)
                    )
                else:
                    await session.execute(
                        insert(self._model).values(
                            key=db_key, namespace=db_namespace, value=serialized_value, expires_at=expires_at
                        )
                    )
            await session.commit()

    async def set(
        self, key: str, value: Union[bytes, str], expires_in: Optional[Union[int, datetime.timedelta]] = None
    ) -> None:
        """Set a value. Handles both sync and async backends."""
        if self._is_async:
            await self._set_async(key, value, expires_in)
        else:
            await async_(self._set_sync)(key, value, expires_in)

    def _get_sync(self, key: str, renew_for: Optional[Union[int, datetime.timedelta]] = None) -> Optional[bytes]:
        db_key, db_namespace = self._make_key(key)
        now = datetime.datetime.now(datetime.timezone.utc)

        with self._get_sync_session() as session, session.begin():
            if session.bind is None:
                msg = "Database connection is not available"
                raise ImproperlyConfiguredException(msg)
            dialect_name = session.bind.dialect.name

            value = session.execute(
                select(self._model.value).where(
                    self._model.key == db_key,
                    self._model.namespace == db_namespace,
                    (self._model.expires_at.is_(None)) | (self._model.expires_at > now),
                )
            ).scalar_one_or_none()

            if value:
                if renew_for:
                    delta = (
                        renew_for
                        if isinstance(renew_for, datetime.timedelta)
                        else datetime.timedelta(seconds=renew_for)
                    )
                    session.execute(
                        update(self._model)
                        .where(self._model.key == db_key, self._model.namespace == db_namespace)
                        .values(expires_at=now + delta)
                    )
                session.commit()
                return self._decode_base64_value(value, dialect_name)

            session.commit()  # Commit even if not found
            return None

    async def _get_async(self, key: str, renew_for: Optional[Union[int, datetime.timedelta]] = None) -> Optional[bytes]:
        db_key, db_namespace = self._make_key(key)
        now = datetime.datetime.now(datetime.timezone.utc)

        async with self._get_async_session() as session, session.begin():
            if session.bind is None:  # pyright: ignore[reportUnnecessaryComparison]
                msg = "Database connection is not available"  # type: ignore[unreachable]
                raise ImproperlyConfiguredException(msg)
            dialect_name = session.bind.dialect.name

            value = (
                await session.execute(
                    select(self._model.value).where(
                        self._model.key == db_key,
                        self._model.namespace == db_namespace,
                        (self._model.expires_at.is_(None)) | (self._model.expires_at > now),
                    )
                )
            ).scalar_one_or_none()

            if value:
                if renew_for:
                    delta = (
                        renew_for
                        if isinstance(renew_for, datetime.timedelta)
                        else datetime.timedelta(seconds=renew_for)
                    )
                    await session.execute(
                        update(self._model)
                        .where(self._model.key == db_key, self._model.namespace == db_namespace)
                        .values(expires_at=now + delta)
                    )
                await session.commit()
                return self._decode_base64_value(value, dialect_name)

            await session.commit()  # Commit even if not found
            return None

    async def get(self, key: str, renew_for: Optional[Union[int, datetime.timedelta]] = None) -> Optional[bytes]:
        """Get a value. Handles both sync and async backends.

        Args:
            key: The key to get the value for.
            renew_for: The amount of time to renew the value for.

        Returns:
            The value of the key, or None if the key does not exist or has expired.
        """
        if self._is_async:
            return await self._get_async(key, renew_for)
        return await async_(self._get_sync)(key, renew_for)

    def _delete_sync(self, key: str) -> None:
        db_key, db_namespace = self._make_key(key)
        with self._get_sync_session() as session, session.begin():
            session.execute(delete(self._model).where(self._model.key == db_key, self._model.namespace == db_namespace))
            session.commit()

    async def _delete_async(self, key: str) -> None:
        db_key, db_namespace = self._make_key(key)
        async with self._get_async_session() as session, session.begin():
            await session.execute(
                delete(self._model).where(self._model.key == db_key, self._model.namespace == db_namespace)
            )
            await session.commit()

    async def delete(self, key: str) -> None:
        """Delete a value. Handles both sync and async backends.

        Args:
            key: The key to delete.
        """
        if self._is_async:
            await self._delete_async(key)
        else:
            await async_(self._delete_sync)(key)

    def _delete_all_sync(self) -> None:
        if self.namespace is None:
            msg = "Cannot perform delete operation: No namespace configured"
            raise ImproperlyConfiguredException(msg)
        db_namespace = self.namespace
        with self._get_sync_session() as session, session.begin():
            session.execute(delete(self._model).where(self._model.namespace == db_namespace))
            session.commit()

    async def _delete_all_async(self) -> None:
        if self.namespace is None:
            msg = "Cannot perform delete operation: No namespace configured"
            raise ImproperlyConfiguredException(msg)
        db_namespace = self.namespace
        async with self._get_async_session() as session, session.begin():
            await session.execute(delete(self._model).where(self._model.namespace == db_namespace))
            await session.commit()

    async def delete_all(self) -> None:
        """Delete all values in the namespace. Handles both sync and async backends.

        Args:
            key: The key to delete.
        """
        if self._is_async:
            await self._delete_all_async()
        else:
            await async_(self._delete_all_sync)()

    def _exists_sync(self, key: str) -> bool:
        db_key, db_namespace = self._make_key(key)
        now = datetime.datetime.now(datetime.timezone.utc)
        with self._get_sync_session() as session:
            # Use count for potentially better performance if only existence is needed
            stmt = (
                select(self._model.key)
                .where(
                    self._model.key == db_key,
                    self._model.namespace == db_namespace,
                    (self._model.expires_at.is_(None)) | (self._model.expires_at > now),
                )
                .limit(1)
            )  # limit 1 is important for performance
            return session.execute(stmt).scalar_one_or_none() is not None

    async def _exists_async(self, key: str) -> bool:
        db_key, db_namespace = self._make_key(key)
        now = datetime.datetime.now(datetime.timezone.utc)
        async with self._get_async_session() as session:
            # Use count for potentially better performance if only existence is needed
            stmt = (
                select(self._model.key)
                .where(
                    self._model.key == db_key,
                    self._model.namespace == db_namespace,
                    (self._model.expires_at.is_(None)) | (self._model.expires_at > now),
                )
                .limit(1)
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none() is not None

    async def exists(self, key: str) -> bool:
        """Check if a key exists. Handles both sync and async backends.

        Args:
            key: The key to check if it exists.

        Returns:
            True if the key exists, False otherwise.
        """
        if self._is_async:
            return await self._exists_async(key)
        return await async_(self._exists_sync)(key)

    def _expires_in_sync(self, key: str) -> Optional[int]:
        db_key, db_namespace = self._make_key(key)
        now = datetime.datetime.now(datetime.timezone.utc)
        with self._get_sync_session() as session:
            stmt = select(self._model.expires_at).where(
                self._model.key == db_key,
                self._model.namespace == db_namespace,
                self._model.expires_at.is_not(None),  # Explicitly check for non-null expiry
                self._model.expires_at > now,
            )
            expires_at = session.execute(stmt).scalar_one_or_none()
            if expires_at:
                return int((expires_at - now).total_seconds())
            return None

    async def _expires_in_async(self, key: str) -> Optional[int]:
        db_key, db_namespace = self._make_key(key)
        now = datetime.datetime.now(datetime.timezone.utc)
        async with self._get_async_session() as session:
            stmt = select(self._model.expires_at).where(
                self._model.key == db_key,
                self._model.namespace == db_namespace,
                self._model.expires_at.is_not(None),  # Explicitly check for non-null expiry
                self._model.expires_at > now,
            )
            result = await session.execute(stmt)
            expires_at = result.scalar_one_or_none()
            if expires_at:
                return int((expires_at - now).total_seconds())
            return None

    async def expires_in(self, key: str) -> Optional[int]:
        """Get expiration time. Handles both sync and async backends.

        Args:
            key: The key to get the expiration time for.

        Returns:
            The expiration time in seconds, or None if the key does not exist or has no expiration time.
        """
        if self._is_async:
            return await self._expires_in_async(key)
        return await async_(self._expires_in_sync)(key)

    def with_namespace(self, namespace: str) -> "SQLAlchemyStore[SQLAlchemyConfigT]":
        """Return a new :class:`SQLAlchemyStore` with a nested virtual key namespace."""
        new_namespace = f"{self.namespace}_{namespace}" if self.namespace else namespace
        # We pass the original config, model type to the new instance
        return type(self)(
            config=self._config,  # Pass the original config
            model=self._model,
            namespace=new_namespace,
        )

    async def __aexit__(
        self,
        exc_type: object,
        exc_val: object,
        exc_tb: object,
    ) -> None:
        # Session lifecycle is managed by the context managers (_get_sync_session/_get_async_session)
        # or externally via the provided config's lifespan manager. No explicit cleanup needed here.
        pass
