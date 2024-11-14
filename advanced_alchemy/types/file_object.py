from __future__ import annotations

import contextlib
import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, ClassVar, Protocol, runtime_checkable

from sqlalchemy import TypeDecorator
from sqlalchemy.dialects.postgresql import JSONB

from advanced_alchemy.exceptions import ImproperConfigurationError, MissingDependencyError
from advanced_alchemy.utils.dataclass import Empty, EmptyType, simple_asdict

fsspec = None  # type: ignore[var-annotated,unused-ignore]
with contextlib.suppress(ImportError):
    import fsspec  # type: ignore[no-redef]

if TYPE_CHECKING:
    import fsspec  # type: ignore[no-redef] # noqa: TCH004


@dataclass
class FileMetadata:
    """Metadata for stored files.

    Args:
        filename: Original filename
        path: Storage path/key
        backend: Storage backend (e.g., 'gcs', 's3', 'file')
        size: File size in bytes
        checksum: MD5 checksum of file
        content_type: MIME type
        created_at: Timestamp of creation
        metadata: Additional metadata dict
        last_modified: Last modification timestamp
        etag: Entity tag for caching
        version_id: Version identifier for versioned storage
        storage_class: Storage class (e.g., 'STANDARD', 'NEARLINE')
    """

    filename: str
    path: str
    backend: str
    """Storage backend (e.g., 'gcs', 's3', 'file')"""
    uploaded_at: datetime
    size: int | None | EmptyType = Empty
    checksum: str | None | EmptyType = Empty
    content_type: str | None | EmptyType = Empty
    metadata: dict[str, Any] | None | EmptyType = Empty
    last_modified: datetime | None | EmptyType = Empty
    etag: str | None | EmptyType = Empty
    version_id: str | None | EmptyType = Empty

    def to_dict(self) -> dict[str, Any]:
        """Convert metadata to dictionary."""
        return simple_asdict(self, exclude_empty=True)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FileMetadata:
        """Create metadata from dictionary."""
        return cls(**data)


@runtime_checkable
class StorageBackend(Protocol):
    """Protocol for storage backend implementations."""

    async def save_file(self, path: str, data: bytes, content_type: str | None = None) -> None:
        """Save file data to storage.

        Args:
            path: Path where to store the file
            data: File data to store
            content_type: Optional MIME type of the file
        """
        ...

    async def get_url(self, path: str, expires_in: int) -> str:
        """Get access URL for file.

        Args:
            path: Path to the file
            expires_in: Expiration time in seconds

        Returns:
            Presigned URL for file access
        """
        ...

    async def get_upload_url(
        self,
        path: str,
        expires_in: int,
        content_type: str,
        max_size: int | None = None,
    ) -> str:
        """Get upload URL for file.

        Args:
            path: Path where the file will be stored
            expires_in: Expiration time in seconds
            content_type: MIME type of the file
            max_size: Optional maximum file size in bytes

        Returns:
            Presigned URL for file upload
        """
        ...

    async def delete_file(self, path: str) -> None:
        """Delete a file from storage.

        Args:
            path: Path to the file to delete
        """
        ...


class FSSpecBackend(StorageBackend):
    """FSSpec implementation of storage backend."""

    def __init__(self, backend: str, base_path: str = "", **options: Any) -> None:
        """Initialize FSSpec backend.

        Args:
            backend: Storage backend to use (e.g., 'file', 'gcs', 's3')
            base_path: Base path/prefix for stored files
            **options: Additional options for fsspec

        Raises:
            MissingDependencyError: If fsspec is not installed
        """
        if fsspec is None:
            raise MissingDependencyError(package="fsspec", install_package="fsspec")

        self.backend = backend
        self.base_path = base_path.rstrip("/")
        self._fs = fsspec.filesystem(backend, **options)

    async def save_file(self, path: str, data: bytes, content_type: str | None = None) -> None:
        """Save file data using FSSpec."""
        full_path = f"{self.base_path}/{path}".lstrip("/")

        if hasattr(self._fs, "async_put"):
            await self._fs.async_put(full_path, data)
        else:
            self._fs.put(full_path, data)

    async def get_url(self, path: str, expires_in: int) -> str:
        """Get access URL using FSSpec."""
        full_path = f"{self.base_path}/{path}".lstrip("/")

        if hasattr(self._fs, "get_signed_url"):
            return await self._fs.get_signed_url(
                full_path,
                expires=timedelta(seconds=expires_in),
            )

        # For local filesystem, return direct path
        return f"file://{full_path}"

    async def get_upload_url(
        self,
        path: str,
        expires_in: int,
        content_type: str,
        max_size: int | None = None,
    ) -> str:
        """Generate upload URL using FSSpec."""
        full_path = f"{self.base_path}/{path}".lstrip("/")

        if hasattr(self._fs, "get_signed_url"):
            return await self._fs.get_signed_url(
                full_path,
                expires=timedelta(seconds=expires_in),
                http_method="PUT",
                content_type=content_type,
            )

        return f"file://{full_path}"

    async def delete_file(self, path: str) -> None:
        """Delete file using FSSpec."""
        full_path = f"{self.base_path}/{path}".lstrip("/")

        if hasattr(self._fs, "async_rm"):
            await self._fs.async_rm(full_path)
        else:
            self._fs.rm(full_path)


class ObjectStore(TypeDecorator[JSONB]):
    """Custom SQLAlchemy type for file objects using fsspec.

    Stores file metadata in JSONB and handles file operations through fsspec.
    """

    impl = JSONB
    cache_ok = True

    # Default settings
    DEFAULT_EXPIRES_IN: ClassVar[int] = 3600  # 1 hour
    SUPPORTED_BACKENDS: ClassVar[set[str]] = {"file", "memory", "gcs", "s3"}

    storage: StorageBackend

    def __init__(
        self,
        backend: str | StorageBackend = "file",
        base_path: str = "",
        backend_options: dict[str, Any] | None = None,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """Initialize FileObject type.

        Args:
            backend: Storage backend to use
            base_path: Base path/prefix for stored files
            backend_options: Additional options for fsspec
            *args: Additional positional arguments
            **kwargs: Additional keyword arguments

        Raises:
            ValueError: If backend is not supported
        """
        super().__init__(*args, **kwargs)

        if isinstance(backend, StorageBackend):
            self.storage = backend
        else:
            if backend not in self.SUPPORTED_BACKENDS:
                msg = f"The configured object store backend is unsupported: {backend}"
                raise ImproperConfigurationError(msg)
            self.storage = FSSpecBackend(backend=backend, base_path=base_path, **(backend_options or {}))

    def process_bind_param(self, value: FileMetadata | dict[str, Any] | None, dialect: Any) -> dict[str, Any] | None:
        """Convert FileMetadata to database format."""
        if value is None:
            return None
        if isinstance(value, dict):
            value = FileMetadata.from_dict(value)
        return value.to_dict()

    def process_result_value(self, value: dict[str, Any] | None, dialect: Any) -> FileMetadata | None:
        """Convert database format to FileMetadata."""
        if value is None:
            return None
        return FileMetadata.from_dict(value)

    async def save_file(
        self, file_data: bytes, filename: str, content_type: str, metadata: dict[str, Any] | None = None
    ) -> FileMetadata:
        """Save file data and return metadata.

        Args:
            file_data: Raw file data
            filename: Original filename
            content_type: MIME type
            metadata: Additional metadata

        Returns:
            FileMetadata object
        """
        path = f"{filename}"
        checksum = hashlib.md5(file_data).hexdigest()

        await self.storage.save_file(path, file_data, content_type)

        return FileMetadata(
            filename=filename,
            path=path,
            backend=self.storage.backend,
            size=len(file_data),
            checksum=checksum,
            content_type=content_type,
            uploaded_at=datetime.utcnow(),
            metadata=metadata,
        )

    async def get_url(self, metadata: FileMetadata, expires_in: int | None = None) -> str:
        """Get URL for accessing file."""
        if expires_in is None:
            expires_in = self.DEFAULT_EXPIRES_IN

        return await self.storage.get_url(metadata.path, expires_in)

    async def get_upload_url(
        self,
        filename: str,
        content_type: str,
        expires_in: int | None = None,
        max_size: int | None = None,
    ) -> tuple[str, str]:
        """Generate pre-signed URL for direct upload."""
        if expires_in is None:
            expires_in = self.DEFAULT_EXPIRES_IN

        path = f"{filename}"

        upload_url = await self.storage.get_upload_url(
            path,
            expires_in,
            content_type,
            max_size,
        )

        return upload_url, path

    async def delete_file(self, metadata: FileMetadata) -> None:
        """Delete file from storage."""
        await self.storage.delete_file(metadata.path)
