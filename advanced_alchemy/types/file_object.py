from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from importlib.util import find_spec
from typing import TYPE_CHECKING, Any, ClassVar, Generic, Protocol, cast, runtime_checkable

from sqlalchemy import TypeDecorator
from sqlalchemy.ext.mutable import MutableComposite

from advanced_alchemy.exceptions import MissingDependencyError
from advanced_alchemy.types.json import JsonB
from advanced_alchemy.utils.dataclass import Empty, EmptyType, simple_asdict

FSSPEC_INSTALLED = bool(find_spec("fsspec"))
if not FSSPEC_INSTALLED and not TYPE_CHECKING:

    class _FileSystem(Generic):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            """Placeholder `filesystem` implementation"""

        def rm(self, *args: Any, **kwargs: Any) -> None:
            """Placeholder `rm` implementation"""

        def put(self, *args: Any, **kwargs: Any) -> None:
            """Placeholder `put` implementation"""

        def url(self, *args: Any, **kwargs: Any) -> str:
            """Placeholder `put` implementation"""
            return ""

    def filesystem(protocol: str, **storage_options: Any) -> _FileSystem:  # noqa: ARG001
        """Placeholder filesystem factory"""
        return _FileSystem()
else:
    from fsspec import filesystem  # type: ignore[no-redef]  # pyright: ignore[reportUnknownVariableType]


if TYPE_CHECKING:
    from collections.abc import Iterator

    from fsspec.spec import AbstractFileSystem  # pyright: ignore[reportMissingTypeStubs,reportMissingImports]


@dataclass
class StoredObject(MutableComposite):
    """Metadata for stored files."""

    filename: str
    """Object filename"""
    path: str
    """Object storage path or key"""
    backend: str
    """Storage backend (e.g., 'gcs', 's3', 'file')"""
    uploaded_at: datetime
    """Timestamp of when the file was uploaded/created"""
    size: int | None | EmptyType = Empty
    """"File size in bytes"""
    checksum: str | None | EmptyType = Empty
    """Checksum of saved object"""
    content_type: str | None | EmptyType = Empty
    """Content/MIME type of object"""
    metadata: dict[str, Any] | None | EmptyType = Empty
    """Additional metadata about the object."""
    last_modified: datetime | None | EmptyType = Empty
    """Last object modification date"""
    etag: str | None | EmptyType = Empty
    """ETAG of object"""
    storage_class: str | None | EmptyType = Empty
    """Storage class of object used to tag or classify object based on location, contents, or some other strategy (eg. `NEARLINE`, `COLDLINE`, `STANDARD`, `ARCHIVE`)"""
    version_id: str | None | EmptyType = Empty
    """Version identifier for versioned objects"""

    def to_dict(self) -> dict[str, Any]:
        """Convert metadata to dictionary."""
        return simple_asdict(self, exclude_empty=True)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StoredObject:
        """Create metadata from dictionary."""
        return cls(**data)


@runtime_checkable
class StorageBackend(Protocol):
    """Protocol for storage backend implementations."""

    backend: str
    """Storage backend name (e.g., 'file', 'gcs', 's3')"""

    def save_file(self, path: str, data: bytes | str | Iterator[bytes], content_type: str | None = None) -> None:
        """Save file data to storage.

        Args:
            path: Path where to store the file
            data: File data to store
            content_type: Optional MIME type of the file
        """
        ...

    def get_url(self, path: str, expires_in: int) -> str:
        """Get access URL for file.

        Args:
            path: Path to the file
            expires_in: Expiration time in seconds

        Returns:
            Presigned URL for file access
        """
        ...

    def delete_file(self, path: str) -> None:
        """Delete a file from storage.

        Args:
            path: Path to the file to delete
        """
        ...


class FSSpecBackend(StorageBackend):
    """FSSpec implementation of storage backend."""

    backend: str
    base_path: str
    _fs: AbstractFileSystem
    _executor: ThreadPoolExecutor | None = None

    @classmethod
    def get_executor(cls) -> ThreadPoolExecutor:
        """Gets or creates the thread pool executor for async operations."""
        if cls._executor is None:
            cls._executor = ThreadPoolExecutor(max_workers=10)
        return cls._executor

    def __init__(self, backend: str, base_path: str = "", **options: Any) -> None:
        """Initialize FSSpec backend.

        Args:
            backend: Storage backend to use (e.g., 'file', 'gcs', 's3')
            base_path: Base path/prefix for stored files
            **options: Additional options for fsspec

        Raises:
            MissingDependencyError: If fsspec is not installed
        """
        if not FSSPEC_INSTALLED:
            raise MissingDependencyError(package="fsspec", install_package="fsspec")

        self.backend = backend
        self.base_path = base_path.rstrip("/")
        self._fs = filesystem(backend, **options)

    def save_file(self, path: str, data: bytes | str | Iterator[bytes], content_type: str | None = None) -> None:
        """Save file data using FSSpec."""
        full_path = f"{self.base_path}/{path}".lstrip("/")
        self._fs.put(full_path, data)  # pyright: ignore[reportUnknownMemberType]

    def get_url(self, path: str, expires_in: int) -> str:
        """Get access URL using FSSpec."""
        full_path = f"{self.base_path}/{path}".lstrip("/")

        if hasattr(self._fs, "url"):
            return cast(
                "str",
                self._fs.url(  # pyright: ignore[reportUnknownMemberType,reportAttributeAccessIssue]
                    full_path,
                    expires=timedelta(seconds=expires_in),
                ),
            )

        # For local filesystem, return direct path
        return f"file://{full_path}"

    def get_upload_url(
        self,
        path: str,
        expires_in: int,
        content_type: str,
        max_size: int | None = None,
    ) -> str:
        """Generate upload URL using FSSpec."""
        full_path = f"{self.base_path}/{path}".lstrip("/")

        if hasattr(self._fs, "url"):
            return cast(
                "str",
                self._fs.url(  # pyright: ignore[reportUnknownMemberType,reportAttributeAccessIssue]
                    full_path,
                    expires=timedelta(seconds=expires_in),
                    http_method="PUT",
                    content_type=content_type,
                ),
            )

        return f"file://{full_path}"

    def delete_file(self, path: str) -> None:
        """Delete file using FSSpec."""
        full_path = f"{self.base_path}/{path}".lstrip("/")
        self._fs.rm(full_path)  # pyright: ignore[reportUnknownMemberType]


class ObjectStore(TypeDecorator[StoredObject]):
    """Custom SQLAlchemy type for file objects using fsspec.

    Stores file metadata in JSONB and handles file operations through fsspec.
    """

    impl = JsonB
    cache_ok = True

    # Default settings
    DEFAULT_EXPIRES_IN: ClassVar[int] = 3600  # 1 hour

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
            self.storage = FSSpecBackend(backend=backend, base_path=base_path, **(backend_options or {}))

    def process_bind_param(self, value: StoredObject | dict[str, Any] | None, dialect: Any) -> dict[str, Any] | None:
        """Convert FileMetadata to database format."""
        if value is None:
            return None
        if isinstance(value, dict):
            value = StoredObject.from_dict(value)
        return value.to_dict()

    def process_result_value(self, value: dict[str, Any] | None, dialect: Any) -> StoredObject | None:
        """Convert database format to FileMetadata."""
        if value is None:
            return None
        return StoredObject.from_dict(value)

    def save_file(
        self, file_data: bytes, filename: str, content_type: str, metadata: dict[str, Any] | None = None
    ) -> StoredObject:
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
        checksum = hashlib.md5(file_data).hexdigest()  # noqa: S324

        self.storage.save_file(path, file_data, content_type)

        return StoredObject(
            filename=filename,
            path=path,
            backend=self.storage.backend,
            size=len(file_data),
            checksum=checksum,
            content_type=content_type,
            uploaded_at=datetime.now(timezone.utc),
            metadata=metadata,
        )

    async def get_url(self, metadata: StoredObject, expires_in: int | None = None) -> str:
        """Get URL for accessing file."""
        if expires_in is None:
            expires_in = self.DEFAULT_EXPIRES_IN

        return self.storage.get_url(metadata.path, expires_in)

    async def delete_file(self, metadata: StoredObject) -> None:
        """Delete file from storage."""
        self.storage.delete_file(metadata.path)
