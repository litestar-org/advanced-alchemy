"""Declarative models for Google ADK artifact persistence."""

import datetime
from typing import Any, Optional

from sqlalchemy import Index, Integer, String, func
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column

from advanced_alchemy.extensions.adk._constants import DEFAULT_MAX_KEY_LENGTH, DEFAULT_MAX_VARCHAR_LENGTH
from advanced_alchemy.extensions.adk.v1._base import ADKv1DeclarativeBase
from advanced_alchemy.types import DateTimeUTC, FileObject, JsonB, StoredObject

DEFAULT_ARTIFACT_BACKEND_KEY = "adk-artifacts"
USER_SCOPE_SESSION_ID = "user"


class ADKArtifact(ADKv1DeclarativeBase):
    """Stored ADK artifact version row."""

    __tablename__ = "adk_artifacts"

    app_name: Mapped[str] = mapped_column(String(DEFAULT_MAX_KEY_LENGTH), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(DEFAULT_MAX_KEY_LENGTH), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(DEFAULT_MAX_KEY_LENGTH), primary_key=True)
    filename: Mapped[str] = mapped_column(String(DEFAULT_MAX_VARCHAR_LENGTH), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    artifact_kind: Mapped[str] = mapped_column(String(32))
    blob: Mapped[Optional[FileObject]] = mapped_column(
        StoredObject(backend=DEFAULT_ARTIFACT_BACKEND_KEY),
        nullable=True,
    )
    mime_type: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    artifact_data: Mapped[dict[str, Any]] = mapped_column(MutableDict.as_mutable(JsonB), default=dict)
    custom_metadata: Mapped[dict[str, Any]] = mapped_column(MutableDict.as_mutable(JsonB), default=dict)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTimeUTC(fsp=6), default=func.now())

    __table_args__ = (
        Index("idx_adk_artifacts_lookup", "app_name", "user_id", "session_id", "filename"),
        Index("idx_adk_artifacts_created_at", "created_at"),
    )


__all__ = ("DEFAULT_ARTIFACT_BACKEND_KEY", "USER_SCOPE_SESSION_ID", "ADKArtifact")
