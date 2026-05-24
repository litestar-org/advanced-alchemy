"""Async Google ADK artifact service implementation."""

import datetime
from typing import Any, Optional, Union

from google.adk.artifacts import artifact_util
from google.adk.artifacts.base_artifact_service import ArtifactVersion, BaseArtifactService, ensure_part
from google.adk.errors.input_validation_error import InputValidationError
from google.genai import types
from sqlalchemy import Select, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from advanced_alchemy.extensions.adk.models import (
    DEFAULT_ARTIFACT_BACKEND_KEY,
    USER_SCOPE_SESSION_ID,
    ADKArtifactModelMixin,
)
from advanced_alchemy.types import FileObject


class ADKAsyncArtifactService(BaseArtifactService):
    """Async SQLAlchemy-backed implementation of Google ADK's artifact contract."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        artifact_model: type[ADKArtifactModelMixin],
        backend_key: str = DEFAULT_ARTIFACT_BACKEND_KEY,
    ) -> None:
        self.session = session
        self.artifact_model = artifact_model
        self.backend_key = backend_key

    async def save_artifact(
        self,
        *,
        app_name: str,
        user_id: str,
        filename: str,
        artifact: Union[types.Part, dict[str, Any]],
        session_id: Optional[str] = None,
        custom_metadata: Optional[dict[str, Any]] = None,
    ) -> int:
        """Save an ADK artifact and return its version number."""
        artifact_part = ensure_part(artifact)
        storage_session_id = self._storage_session_id(filename=filename, session_id=session_id)
        current_version = await self._get_max_version(
            app_name=app_name,
            user_id=user_id,
            session_id=storage_session_id,
            filename=filename,
        )
        version = 0 if current_version is None else current_version + 1
        artifact_kind, mime_type, content = self._serialize_artifact(artifact_part)
        blob = (
            FileObject(
                backend=self.backend_key,
                filename=self._blob_name(
                    app_name=app_name,
                    user_id=user_id,
                    session_id=storage_session_id,
                    filename=filename,
                    version=version,
                ),
                content_type=mime_type,
                content=content,
            )
            if content is not None
            else None
        )
        self.session.add(
            self.artifact_model(
                app_name=app_name,
                user_id=user_id,
                session_id=storage_session_id,
                filename=filename,
                version=version,
                artifact_kind=artifact_kind,
                blob=blob,
                mime_type=mime_type,
                artifact_data=artifact_part.model_dump(exclude_none=True, mode="json"),
                custom_metadata=custom_metadata or {},
            ),
        )
        await self.session.flush()
        return version

    async def load_artifact(
        self,
        *,
        app_name: str,
        user_id: str,
        filename: str,
        session_id: Optional[str] = None,
        version: Optional[int] = None,
    ) -> Optional[types.Part]:
        """Load an ADK artifact, returning the latest version by default."""
        artifact = await self._get_artifact(
            app_name=app_name,
            user_id=user_id,
            filename=filename,
            session_id=session_id,
            version=version,
        )
        if artifact is None:
            return None
        return await self._to_part(artifact)

    async def list_artifact_keys(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: Optional[str] = None,
    ) -> list[str]:
        """List artifact filenames for a user and optional session."""
        storage_session_ids = [USER_SCOPE_SESSION_ID]
        if session_id is not None:
            storage_session_ids.append(session_id)
        statement = (
            select(distinct(self.artifact_model.filename))
            .where(self.artifact_model.app_name == app_name)
            .where(self.artifact_model.user_id == user_id)
            .where(self.artifact_model.session_id.in_(storage_session_ids))
            .order_by(self.artifact_model.filename)
        )
        return list((await self.session.scalars(statement)).all())

    async def delete_artifact(
        self,
        *,
        app_name: str,
        user_id: str,
        filename: str,
        session_id: Optional[str] = None,
    ) -> None:
        """Delete all versions of an artifact."""
        storage_session_id = self._storage_session_id(filename=filename, session_id=session_id)
        result = await self.session.scalars(
            self._artifact_statement(
                app_name=app_name,
                user_id=user_id,
                session_id=storage_session_id,
                filename=filename,
            ),
        )
        for artifact in result.all():
            await self.session.delete(artifact)
        await self.session.flush()

    async def list_versions(
        self,
        *,
        app_name: str,
        user_id: str,
        filename: str,
        session_id: Optional[str] = None,
    ) -> list[int]:
        """List available versions for an artifact."""
        storage_session_id = self._storage_session_id(filename=filename, session_id=session_id)
        statement = (
            select(self.artifact_model.version)
            .where(self.artifact_model.app_name == app_name)
            .where(self.artifact_model.user_id == user_id)
            .where(self.artifact_model.session_id == storage_session_id)
            .where(self.artifact_model.filename == filename)
            .order_by(self.artifact_model.version)
        )
        return list((await self.session.scalars(statement)).all())

    async def list_artifact_versions(
        self,
        *,
        app_name: str,
        user_id: str,
        filename: str,
        session_id: Optional[str] = None,
    ) -> list[ArtifactVersion]:
        """List artifact versions with metadata."""
        storage_session_id = self._storage_session_id(filename=filename, session_id=session_id)
        result = await self.session.scalars(
            self._artifact_statement(
                app_name=app_name,
                user_id=user_id,
                session_id=storage_session_id,
                filename=filename,
            ),
        )
        return [self._to_artifact_version(artifact) for artifact in result.all()]

    async def get_artifact_version(
        self,
        *,
        app_name: str,
        user_id: str,
        filename: str,
        session_id: Optional[str] = None,
        version: Optional[int] = None,
    ) -> Optional[ArtifactVersion]:
        """Get metadata for a specific artifact version."""
        artifact = await self._get_artifact(
            app_name=app_name,
            user_id=user_id,
            filename=filename,
            session_id=session_id,
            version=version,
        )
        if artifact is None:
            return None
        return self._to_artifact_version(artifact)

    async def get_artifact_url(
        self,
        *,
        app_name: str,
        user_id: str,
        filename: str,
        session_id: Optional[str] = None,
        version: Optional[int] = None,
        expires_in: Optional[Union[int, datetime.timedelta]] = None,
    ) -> Optional[str]:
        """Return a backend signed URL for an artifact blob when supported."""
        artifact = await self._get_artifact(
            app_name=app_name,
            user_id=user_id,
            filename=filename,
            session_id=session_id,
            version=version,
        )
        if artifact is None or artifact.blob is None:
            return None
        expires_seconds = int(expires_in.total_seconds()) if isinstance(expires_in, datetime.timedelta) else expires_in
        return await artifact.blob.sign_async(expires_in=expires_seconds)

    async def _get_max_version(self, *, app_name: str, user_id: str, session_id: str, filename: str) -> Optional[int]:
        statement = (
            select(func.max(self.artifact_model.version))
            .where(self.artifact_model.app_name == app_name)
            .where(self.artifact_model.user_id == user_id)
            .where(self.artifact_model.session_id == session_id)
            .where(self.artifact_model.filename == filename)
        )
        return await self.session.scalar(statement)

    async def _get_artifact(
        self,
        *,
        app_name: str,
        user_id: str,
        filename: str,
        session_id: Optional[str],
        version: Optional[int],
    ) -> Optional[ADKArtifactModelMixin]:
        storage_session_id = self._storage_session_id(filename=filename, session_id=session_id)
        if version is None:
            version = await self._get_max_version(
                app_name=app_name,
                user_id=user_id,
                session_id=storage_session_id,
                filename=filename,
            )
            if version is None:
                return None
        statement = (
            self._artifact_statement(
                app_name=app_name,
                user_id=user_id,
                session_id=storage_session_id,
                filename=filename,
            )
            .where(self.artifact_model.version == version)
            .limit(1)
        )
        return await self.session.scalar(statement)

    async def _to_part(self, artifact: ADKArtifactModelMixin) -> Optional[types.Part]:
        if artifact.artifact_kind == "file_data":
            return await self._to_file_data_part(artifact)

        if artifact.blob is None:
            return None
        content = await artifact.blob.get_content_async()
        if not content:
            return None
        if artifact.artifact_kind == "text":
            return types.Part(text=content.decode("utf-8"))
        return types.Part(inline_data=types.Blob(data=content, mime_type=artifact.mime_type))

    async def _to_file_data_part(self, artifact: ADKArtifactModelMixin) -> Optional[types.Part]:
        part = types.Part.model_validate(artifact.artifact_data)
        if not artifact_util.is_artifact_ref(part):
            return part
        file_data = part.file_data
        if file_data is None or file_data.file_uri is None:
            return part
        parsed_uri = artifact_util.parse_artifact_uri(file_data.file_uri)
        if parsed_uri is None:
            msg = f"Invalid artifact reference URI: {file_data.file_uri}"
            raise InputValidationError(msg)
        return await self.load_artifact(
            app_name=parsed_uri.app_name,
            user_id=parsed_uri.user_id,
            session_id=parsed_uri.session_id,
            filename=parsed_uri.filename,
            version=parsed_uri.version,
        )

    def _to_artifact_version(self, artifact: ADKArtifactModelMixin) -> ArtifactVersion:
        return ArtifactVersion(
            version=artifact.version,
            canonical_uri=self._canonical_uri(artifact),
            custom_metadata=artifact.custom_metadata or {},
            create_time=self._timestamp(artifact.created_at),
            mime_type=artifact.mime_type,
        )

    @staticmethod
    def _timestamp(value: datetime.datetime) -> float:
        if value.tzinfo is None:
            value = value.replace(tzinfo=datetime.timezone.utc)
        return value.timestamp()

    @staticmethod
    def _canonical_uri(artifact: ADKArtifactModelMixin) -> str:
        if artifact.blob is not None:
            return f"{artifact.blob.protocol}://{artifact.blob.path}"
        session_id = None if artifact.session_id == USER_SCOPE_SESSION_ID else artifact.session_id
        return artifact_util.get_artifact_uri(
            artifact.app_name,
            artifact.user_id,
            artifact.filename,
            artifact.version,
            session_id=session_id,
        )

    @staticmethod
    def _serialize_artifact(artifact: types.Part) -> tuple[str, Optional[str], Optional[bytes]]:
        if artifact.inline_data is not None:
            return (
                "inline_data",
                artifact.inline_data.mime_type or "application/octet-stream",
                artifact.inline_data.data or b"",
            )
        if artifact.text is not None:
            return "text", "text/plain", artifact.text.encode("utf-8")
        if artifact.file_data is not None:
            is_invalid_ref = artifact_util.is_artifact_ref(artifact) and (
                artifact.file_data.file_uri is None
                or artifact_util.parse_artifact_uri(artifact.file_data.file_uri) is None
            )
            if is_invalid_ref:
                msg = f"Invalid artifact reference URI: {artifact.file_data.file_uri}"
                raise InputValidationError(msg)
            return "file_data", artifact.file_data.mime_type, None
        msg = "Artifact must have inline_data, text, or file_data."
        raise InputValidationError(msg)

    @classmethod
    def _storage_session_id(cls, *, filename: str, session_id: Optional[str]) -> str:
        if cls._file_has_user_namespace(filename):
            return USER_SCOPE_SESSION_ID
        if session_id is None:
            msg = "Session ID must be provided for session-scoped artifacts."
            raise InputValidationError(msg)
        return session_id

    @staticmethod
    def _file_has_user_namespace(filename: str) -> bool:
        return filename.startswith("user:")

    @staticmethod
    def _blob_name(*, app_name: str, user_id: str, session_id: str, filename: str, version: int) -> str:
        return f"{app_name}/{user_id}/{session_id}/{filename}/{version}"

    def _artifact_statement(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: str,
        filename: str,
    ) -> Select[tuple[ADKArtifactModelMixin]]:
        return (
            select(self.artifact_model)
            .where(self.artifact_model.app_name == app_name)
            .where(self.artifact_model.user_id == user_id)
            .where(self.artifact_model.session_id == session_id)
            .where(self.artifact_model.filename == filename)
            .order_by(self.artifact_model.version)
        )


__all__ = ("ADKAsyncArtifactService",)
