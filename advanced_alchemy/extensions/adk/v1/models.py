"""Declarative models for Google ADK v1 persistence schema."""

import datetime
import uuid
from typing import Any, Optional

from sqlalchemy import ForeignKeyConstraint, Index, String, desc, func
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column, relationship

from advanced_alchemy.extensions.adk._constants import DEFAULT_MAX_KEY_LENGTH, DEFAULT_MAX_VARCHAR_LENGTH
from advanced_alchemy.extensions.adk.v1._base import ADKv1DeclarativeBase
from advanced_alchemy.types import DateTimeUTC, JsonB


def _new_adk_uuid() -> str:
    """Return an ADK-compatible generated ID without requiring ADK at import time."""
    try:
        from google.adk.platform import uuid as platform_uuid
    except ImportError:
        return str(uuid.uuid4())
    return platform_uuid.new_uuid()


class ADKSession(ADKv1DeclarativeBase):
    """Stored ADK session row."""

    __tablename__ = "sessions"

    app_name: Mapped[str] = mapped_column(String(DEFAULT_MAX_KEY_LENGTH), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(DEFAULT_MAX_KEY_LENGTH), primary_key=True)
    id: Mapped[str] = mapped_column(String(DEFAULT_MAX_KEY_LENGTH), primary_key=True, default=_new_adk_uuid)
    state: Mapped[dict[str, Any]] = mapped_column(MutableDict.as_mutable(JsonB), default=dict)
    create_time: Mapped[datetime.datetime] = mapped_column(DateTimeUTC(fsp=6), default=func.now())
    update_time: Mapped[datetime.datetime] = mapped_column(
        DateTimeUTC(fsp=6),
        default=func.now(),
        onupdate=func.now(),
    )
    storage_events: Mapped[list["ADKEvent"]] = relationship(
        "ADKEvent",
        back_populates="storage_session",
        cascade="all, delete-orphan",
    )

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
    ) -> Any:
        """Convert this storage row into a Google ADK ``Session``."""
        from google.adk.sessions.session import Session

        session = Session(
            app_name=self.app_name,
            user_id=self.user_id,
            id=self.id,
            state=state or {},
            events=events or [],
            last_update_time=self.get_update_timestamp(is_sqlite=is_sqlite),
        )
        setattr(session, "_storage_update_marker", self.get_update_marker())
        return session


class ADKEvent(ADKv1DeclarativeBase):
    """Stored ADK event row."""

    __tablename__ = "events"

    id: Mapped[str] = mapped_column(String(DEFAULT_MAX_KEY_LENGTH), primary_key=True)
    app_name: Mapped[str] = mapped_column(String(DEFAULT_MAX_KEY_LENGTH), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(DEFAULT_MAX_KEY_LENGTH), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(DEFAULT_MAX_KEY_LENGTH), primary_key=True)
    invocation_id: Mapped[str] = mapped_column(String(DEFAULT_MAX_VARCHAR_LENGTH))
    timestamp: Mapped[datetime.datetime] = mapped_column(DateTimeUTC(fsp=6), default=func.now())
    event_data: Mapped[Optional[dict[str, Any]]] = mapped_column(MutableDict.as_mutable(JsonB), nullable=True)

    storage_session: Mapped[ADKSession] = relationship("ADKSession", back_populates="storage_events")

    __table_args__ = (
        ForeignKeyConstraint(
            ["app_name", "user_id", "session_id"],
            ["sessions.app_name", "sessions.user_id", "sessions.id"],
            ondelete="CASCADE",
        ),
        Index(
            "idx_events_app_user_session_ts",
            "app_name",
            "user_id",
            "session_id",
            desc("timestamp"),
        ),
    )

    @classmethod
    def from_event(cls, session: Any, event: Any) -> "ADKEvent":
        """Create a storage event from a Google ADK ``Event``."""
        return cls(
            id=event.id,
            invocation_id=event.invocation_id,
            session_id=session.id,
            app_name=session.app_name,
            user_id=session.user_id,
            timestamp=datetime.datetime.fromtimestamp(event.timestamp, tz=datetime.timezone.utc),
            event_data=event.model_dump(exclude_none=True, mode="json"),
        )

    def to_event(self) -> Any:
        """Convert this storage row into a Google ADK ``Event``."""
        from google.adk.events.event import Event

        return Event.model_validate(
            {
                **(self.event_data or {}),
                "id": self.id,
                "invocation_id": self.invocation_id,
                "timestamp": self.timestamp.timestamp(),
            },
        )


class ADKAppState(ADKv1DeclarativeBase):
    """Stored ADK app-scoped state row."""

    __tablename__ = "app_states"

    app_name: Mapped[str] = mapped_column(String(DEFAULT_MAX_KEY_LENGTH), primary_key=True)
    state: Mapped[dict[str, Any]] = mapped_column(MutableDict.as_mutable(JsonB), default=dict)
    update_time: Mapped[datetime.datetime] = mapped_column(DateTimeUTC(fsp=6), default=func.now(), onupdate=func.now())


class ADKUserState(ADKv1DeclarativeBase):
    """Stored ADK user-scoped state row."""

    __tablename__ = "user_states"

    app_name: Mapped[str] = mapped_column(String(DEFAULT_MAX_KEY_LENGTH), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(DEFAULT_MAX_KEY_LENGTH), primary_key=True)
    state: Mapped[dict[str, Any]] = mapped_column(MutableDict.as_mutable(JsonB), default=dict)
    update_time: Mapped[datetime.datetime] = mapped_column(DateTimeUTC(fsp=6), default=func.now(), onupdate=func.now())


class ADKMetadata(ADKv1DeclarativeBase):
    """Stored ADK internal metadata row."""

    __tablename__ = "adk_internal_metadata"

    key: Mapped[str] = mapped_column(String(DEFAULT_MAX_KEY_LENGTH), primary_key=True)
    value: Mapped[str] = mapped_column(String(DEFAULT_MAX_VARCHAR_LENGTH))


__all__ = ("ADKAppState", "ADKEvent", "ADKMetadata", "ADKSession", "ADKUserState")
