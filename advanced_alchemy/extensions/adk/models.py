"""Model mixins for Google ADK persistence."""

import datetime
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import Index, Integer, String, Text, UniqueConstraint, desc, func
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, declarative_mixin, declared_attr, mapped_column

from advanced_alchemy.base import UUIDv7Base
from advanced_alchemy.extensions.adk._constants import DEFAULT_MAX_KEY_LENGTH, DEFAULT_MAX_VARCHAR_LENGTH
from advanced_alchemy.types import DateTimeUTC, FileObject, JsonB, StoredObject

if TYPE_CHECKING:
    from google.adk.events.event import Event
    from google.adk.sessions.session import Session
    from sqlalchemy.orm.decl_base import _TableArgsType as TableArgsType  # pyright: ignore[reportPrivateUsage]

DEFAULT_ARTIFACT_BACKEND_KEY = "adk-artifacts"
USER_SCOPE_SESSION_ID = "user"


@declarative_mixin
class ADKSessionModelMixin(UUIDv7Base):
    """Mixin for Google ADK session storage."""

    __abstract__ = True

    @staticmethod
    def _create_session_lookup_index(*_: Any, **kwargs: Any) -> bool:
        dialect_name = kwargs["dialect"].name if "dialect" in kwargs else ""
        return dialect_name != "oracle"

    @declared_attr.directive
    @classmethod
    def __table_args__(cls) -> "TableArgsType":
        return (
            UniqueConstraint(
                cls.app_name,
                cls.user_id,
                cls.session_id,
                name=f"uq_{cls.__tablename__}_adk_session",
            ),
            Index(
                f"ix_{cls.__tablename__}_adk_session_lookup",
                cls.app_name,
                cls.user_id,
                cls.session_id,
            ).ddl_if(callable_=cls._create_session_lookup_index),
        )

    @declared_attr
    def app_name(cls) -> Mapped[str]:
        return mapped_column(String(DEFAULT_MAX_KEY_LENGTH), nullable=False)

    @declared_attr
    def user_id(cls) -> Mapped[str]:
        return mapped_column(String(DEFAULT_MAX_KEY_LENGTH), nullable=False)

    @declared_attr
    def session_id(cls) -> Mapped[str]:
        return mapped_column(String(DEFAULT_MAX_KEY_LENGTH), nullable=False)

    @declared_attr
    def state(cls) -> Mapped[dict[str, Any]]:
        return mapped_column(MutableDict.as_mutable(JsonB), default=dict)

    @declared_attr
    def create_time(cls) -> Mapped[datetime.datetime]:
        return mapped_column(DateTimeUTC(fsp=6), default=func.now())

    @declared_attr
    def update_time(cls) -> Mapped[datetime.datetime]:
        return mapped_column(DateTimeUTC(fsp=6), default=func.now(), onupdate=func.now())

    @property
    def update_timestamp_tz(self) -> float:
        """Return the update timestamp as a POSIX timestamp."""
        return self.get_update_timestamp(is_sqlite=False)

    def get_update_timestamp(self, is_sqlite: bool) -> float:
        """Return the update timestamp with SQLite's naive datetime quirk handled."""
        if is_sqlite:
            return self.update_time.replace(tzinfo=datetime.timezone.utc).timestamp()
        return self.update_time.timestamp()

    def get_update_marker(self) -> str:
        """Return a stable revision marker for optimistic concurrency checks."""
        update_time = self.update_time
        if update_time.tzinfo is not None:
            update_time = update_time.astimezone(datetime.timezone.utc)
        return update_time.isoformat(timespec="microseconds")

    def to_session(
        self,
        state: Optional[dict[str, Any]] = None,
        events: Optional[list[Any]] = None,
        is_sqlite: bool = False,
    ) -> "Session":
        """Convert this storage row into a Google ADK ``Session``."""
        from google.adk.sessions.session import Session

        session = Session(
            app_name=self.app_name,
            user_id=self.user_id,
            id=self.session_id,
            state=state or {},
            events=events or [],
            last_update_time=self.get_update_timestamp(is_sqlite=is_sqlite),
        )
        setattr(session, "_storage_update_marker", self.get_update_marker())
        return session


@declarative_mixin
class ADKEventModelMixin(UUIDv7Base):
    """Mixin for Google ADK event storage."""

    __abstract__ = True

    @declared_attr.directive
    @classmethod
    def __table_args__(cls) -> "TableArgsType":
        return (
            UniqueConstraint(
                cls.app_name,
                cls.user_id,
                cls.session_id,
                cls.event_id,
                name=f"uq_{cls.__tablename__}_adk_event",
            ),
            Index(
                f"ix_{cls.__tablename__}_adk_session_ts",
                cls.app_name,
                cls.user_id,
                cls.session_id,
                desc(cls.timestamp),
            ),
        )

    @declared_attr
    def event_id(cls) -> Mapped[str]:
        return mapped_column(String(DEFAULT_MAX_KEY_LENGTH), nullable=False)

    @declared_attr
    def app_name(cls) -> Mapped[str]:
        return mapped_column(String(DEFAULT_MAX_KEY_LENGTH), nullable=False)

    @declared_attr
    def user_id(cls) -> Mapped[str]:
        return mapped_column(String(DEFAULT_MAX_KEY_LENGTH), nullable=False)

    @declared_attr
    def session_id(cls) -> Mapped[str]:
        return mapped_column(String(DEFAULT_MAX_KEY_LENGTH), nullable=False)

    @declared_attr
    def invocation_id(cls) -> Mapped[str]:
        return mapped_column(String(DEFAULT_MAX_VARCHAR_LENGTH), nullable=False)

    @declared_attr
    def timestamp(cls) -> Mapped[datetime.datetime]:
        return mapped_column(DateTimeUTC(fsp=6), default=func.now())

    @declared_attr
    def event_data(cls) -> Mapped[Optional[dict[str, Any]]]:
        return mapped_column(MutableDict.as_mutable(JsonB), nullable=True)

    @classmethod
    def from_event(cls, session: "Session", event: "Event") -> "ADKEventModelMixin":
        """Create a storage event from a Google ADK ``Event``."""
        return cls(
            event_id=event.id,
            invocation_id=event.invocation_id,
            session_id=session.id,
            app_name=session.app_name,
            user_id=session.user_id,
            timestamp=datetime.datetime.fromtimestamp(event.timestamp, tz=datetime.timezone.utc),
            event_data=event.model_dump(exclude_none=True, mode="json"),
        )

    def to_event(self) -> "Event":
        """Convert this storage row into a Google ADK ``Event``."""
        from google.adk.events.event import Event

        return Event.model_validate(
            {
                **(self.event_data or {}),
                "id": self.event_id,
                "invocation_id": self.invocation_id,
                "timestamp": self.timestamp.timestamp(),
            },
        )


@declarative_mixin
class ADKAppStateModelMixin(UUIDv7Base):
    """Mixin for Google ADK app-scoped state storage."""

    __abstract__ = True

    @declared_attr.directive
    @classmethod
    def __table_args__(cls) -> "TableArgsType":
        return (UniqueConstraint(cls.app_name, name=f"uq_{cls.__tablename__}_app_name"),)

    @declared_attr
    def app_name(cls) -> Mapped[str]:
        return mapped_column(String(DEFAULT_MAX_KEY_LENGTH), nullable=False)

    @declared_attr
    def state(cls) -> Mapped[dict[str, Any]]:
        return mapped_column(MutableDict.as_mutable(JsonB), default=dict)

    @declared_attr
    def update_time(cls) -> Mapped[datetime.datetime]:
        return mapped_column(DateTimeUTC(fsp=6), default=func.now(), onupdate=func.now())


@declarative_mixin
class ADKUserStateModelMixin(UUIDv7Base):
    """Mixin for Google ADK user-scoped state storage."""

    __abstract__ = True

    @declared_attr.directive
    @classmethod
    def __table_args__(cls) -> "TableArgsType":
        return (UniqueConstraint(cls.app_name, cls.user_id, name=f"uq_{cls.__tablename__}_app_user"),)

    @declared_attr
    def app_name(cls) -> Mapped[str]:
        return mapped_column(String(DEFAULT_MAX_KEY_LENGTH), nullable=False)

    @declared_attr
    def user_id(cls) -> Mapped[str]:
        return mapped_column(String(DEFAULT_MAX_KEY_LENGTH), nullable=False)

    @declared_attr
    def state(cls) -> Mapped[dict[str, Any]]:
        return mapped_column(MutableDict.as_mutable(JsonB), default=dict)

    @declared_attr
    def update_time(cls) -> Mapped[datetime.datetime]:
        return mapped_column(DateTimeUTC(fsp=6), default=func.now(), onupdate=func.now())


@declarative_mixin
class ADKArtifactModelMixin(UUIDv7Base):
    """Mixin for Google ADK artifact version storage."""

    __abstract__ = True

    @declared_attr.directive
    @classmethod
    def __table_args__(cls) -> "TableArgsType":
        return (
            UniqueConstraint(
                cls.app_name,
                cls.user_id,
                cls.session_id,
                cls.filename,
                cls.version,
                name=f"uq_{cls.__tablename__}_adk_artifact_version",
            ),
            Index(
                f"ix_{cls.__tablename__}_adk_artifact_lookup", cls.app_name, cls.user_id, cls.session_id, cls.filename
            ),
        )

    @declared_attr
    def app_name(cls) -> Mapped[str]:
        return mapped_column(String(DEFAULT_MAX_KEY_LENGTH), nullable=False)

    @declared_attr
    def user_id(cls) -> Mapped[str]:
        return mapped_column(String(DEFAULT_MAX_KEY_LENGTH), nullable=False)

    @declared_attr
    def session_id(cls) -> Mapped[str]:
        return mapped_column(String(DEFAULT_MAX_KEY_LENGTH), nullable=False)

    @declared_attr
    def filename(cls) -> Mapped[str]:
        return mapped_column(String(DEFAULT_MAX_VARCHAR_LENGTH), nullable=False)

    @declared_attr
    def version(cls) -> Mapped[int]:
        return mapped_column(Integer, nullable=False)

    @declared_attr
    def artifact_kind(cls) -> Mapped[str]:
        return mapped_column(String(32), nullable=False)

    @declared_attr
    def blob(cls) -> Mapped[Optional[FileObject]]:
        return mapped_column(StoredObject(backend=DEFAULT_ARTIFACT_BACKEND_KEY), nullable=True)

    @declared_attr
    def mime_type(cls) -> Mapped[Optional[str]]:
        return mapped_column(String(128), nullable=True)

    @declared_attr
    def artifact_data(cls) -> Mapped[dict[str, Any]]:
        return mapped_column(MutableDict.as_mutable(JsonB), default=dict)

    @declared_attr
    def custom_metadata(cls) -> Mapped[dict[str, Any]]:
        return mapped_column(MutableDict.as_mutable(JsonB), default=dict)

    @declared_attr
    def created_at(cls) -> Mapped[datetime.datetime]:
        return mapped_column(DateTimeUTC(fsp=6), default=func.now())


@declarative_mixin
class ADKMemoryModelMixin(UUIDv7Base):
    """Mixin for Google ADK long-term memory storage."""

    __abstract__ = True

    @declared_attr.directive
    @classmethod
    def __table_args__(cls) -> "TableArgsType":
        return (
            UniqueConstraint(cls.app_name, cls.user_id, cls.memory_id, name=f"uq_{cls.__tablename__}_memory_id"),
            Index(f"ix_{cls.__tablename__}_app_user_ts", cls.app_name, cls.user_id, desc(cls.timestamp)),
            Index(f"ix_{cls.__tablename__}_session", cls.session_id),
        )

    @declared_attr
    def memory_id(cls) -> Mapped[str]:
        return mapped_column(String(DEFAULT_MAX_KEY_LENGTH), nullable=False)

    @declared_attr
    def app_name(cls) -> Mapped[str]:
        return mapped_column(String(DEFAULT_MAX_KEY_LENGTH), nullable=False)

    @declared_attr
    def user_id(cls) -> Mapped[str]:
        return mapped_column(String(DEFAULT_MAX_KEY_LENGTH), nullable=False)

    @declared_attr
    def session_id(cls) -> Mapped[Optional[str]]:
        return mapped_column(String(DEFAULT_MAX_KEY_LENGTH), nullable=True)

    @declared_attr
    def event_id(cls) -> Mapped[Optional[str]]:
        return mapped_column(String(DEFAULT_MAX_KEY_LENGTH), nullable=True)

    @declared_attr
    def author(cls) -> Mapped[Optional[str]]:
        return mapped_column(String(DEFAULT_MAX_VARCHAR_LENGTH), nullable=True)

    @declared_attr
    def timestamp(cls) -> Mapped[datetime.datetime]:
        return mapped_column(DateTimeUTC(fsp=6))

    @declared_attr
    def content_json(cls) -> Mapped[dict[str, Any]]:
        return mapped_column(MutableDict.as_mutable(JsonB))

    @declared_attr
    def content_text(cls) -> Mapped[str]:
        return mapped_column(Text)

    @declared_attr
    def metadata_json(cls) -> Mapped[dict[str, Any]]:
        return mapped_column(MutableDict.as_mutable(JsonB), default=dict)

    @declared_attr
    def inserted_at(cls) -> Mapped[datetime.datetime]:
        return mapped_column(DateTimeUTC(fsp=6), default=func.now())


@dataclass(frozen=True)
class ADKSessionModelConfig:
    """Mapped model classes used by the ADK session service."""

    session_model: type[ADKSessionModelMixin]
    event_model: type[ADKEventModelMixin]
    app_state_model: type[ADKAppStateModelMixin]
    user_state_model: type[ADKUserStateModelMixin]
    artifact_model: Optional[type[ADKArtifactModelMixin]] = None


__all__ = (
    "DEFAULT_ARTIFACT_BACKEND_KEY",
    "USER_SCOPE_SESSION_ID",
    "ADKAppStateModelMixin",
    "ADKArtifactModelMixin",
    "ADKEventModelMixin",
    "ADKMemoryModelMixin",
    "ADKSessionModelConfig",
    "ADKSessionModelMixin",
    "ADKUserStateModelMixin",
)
