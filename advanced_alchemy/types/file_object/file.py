"""Generic unified storage protocol compatible with multiple backend implementations."""

import mimetypes
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional, Union

from sqlalchemy.ext.mutable import MutableList
from typing_extensions import TypeAlias

from advanced_alchemy.exceptions import MissingDependencyError
from advanced_alchemy.types.file_object._typing import PYDANTIC_INSTALLED, GetCoreSchemaHandler, core_schema
from advanced_alchemy.types.file_object.base import AsyncDataLike, DataLike, StorageBackend
from advanced_alchemy.types.file_object.registry import storages

if TYPE_CHECKING:
    from advanced_alchemy.types.file_object.base import PathLike


class FileObject:
    """Represents file metadata during processing using a dataclass structure.

    This class provides a unified interface for handling file metadata and operations
    across different storage backends.

    Content or a source path can optionally be provided during initialization via kwargs, store it internally, and add save/save_async methods to persist this pending data using the configured backend.
    """

    __slots__ = (
        "_checksum",
        "_content_type",
        "_etag",
        "_filename",
        "_last_modified",
        "_metadata",
        "_pending_source_content",
        "_pending_source_path",
        "_raw_backend",
        "_resolved_backend",
        "_size",
        "_to_filename",
        "_version_id",
    )

    def __init__(
        self,
        backend: "Union[str, StorageBackend]",
        filename: str,
        to_filename: Optional[str] = None,
        content_type: Optional[str] = None,
        size: Optional[int] = None,
        last_modified: Optional[float] = None,
        checksum: Optional[str] = None,
        etag: Optional[str] = None,
        version_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        source_path: "Optional[PathLike]" = None,
        content: "Optional[Union[DataLike, AsyncDataLike]]" = None,
    ) -> None:
        """Perform post-initialization validation and setup.

        Handles default path, content type guessing, backend protocol inference,
        and processing of 'content' or 'source_path' from extra kwargs.

        Raises:
            ValueError: If filename is not provided, size is negative, backend/protocol mismatch,
                        or both 'content' and 'source_path' are provided.
        """
        self._size = size
        self._last_modified = last_modified
        self._checksum = checksum
        self._etag = etag
        self._version_id = version_id
        self._metadata = metadata or {}
        self._filename = filename
        self._content_type = content_type
        self._to_filename = to_filename
        self._resolved_backend: Optional[StorageBackend] = backend if isinstance(backend, StorageBackend) else None
        self._raw_backend = backend
        self._pending_source_path = Path(source_path) if source_path is not None else None
        self._pending_source_content = content
        if self._pending_source_content is not None and self._pending_source_path is not None:
            msg = "Cannot provide both 'source_content' and 'source_path' during initialization."
            raise ValueError(msg)

    def __repr__(self) -> str:
        """Return a string representation of the FileObject."""
        return f"FileObject(filename={self.path}, backend={self.backend.key}, size={self.size}, content_type={self.content_type}, etag={self.etag}, last_modified={self.last_modified}, version_id={self.version_id})"

    def __eq__(self, other: object) -> bool:
        """Check equality based on filename and backend key.

        Args:
            other: The object to compare with.


        Returns:
            bool: True if the objects are equal, False otherwise.

        """
        if not isinstance(other, FileObject):
            return False
        return self.path == other.path and self.backend.key == other.backend.key

    def __hash__(self) -> int:
        """Return a hash based on filename and backend key."""
        return hash((self.path, self.backend.key))

    @property
    def backend(self) -> "StorageBackend":
        if self._resolved_backend is None:
            self._resolved_backend = (
                storages.get_backend(self._raw_backend) if isinstance(self._raw_backend, str) else self._raw_backend
            )
        return self._resolved_backend

    @property
    def filename(self) -> str:
        return self.path

    @property
    def content_type(self) -> str:
        if self._content_type is None:
            guessed_type, _ = mimetypes.guess_type(self._filename)
            self._content_type = guessed_type or "application/octet-stream"
        return self._content_type

    @property
    def protocol(self) -> str:
        return self.backend.protocol if self.backend else "file"

    @property
    def path(self) -> str:
        return self._to_filename or self._filename

    @property
    def has_pending_data(self) -> bool:
        return bool(self._pending_source_content or self._pending_source_path)

    @property
    def metadata(self) -> dict[str, Any]:
        return self._metadata

    @metadata.setter
    def metadata(self, value: dict[str, Any]) -> None:
        self._metadata = value

    @property
    def size(self) -> "Optional[int]":
        return self._size

    @size.setter
    def size(self, value: int) -> None:
        self._size = value

    @property
    def last_modified(self) -> "Optional[float]":
        return self._last_modified

    @last_modified.setter
    def last_modified(self, value: float) -> None:
        self._last_modified = value

    @property
    def checksum(self) -> "Optional[str]":
        return self._checksum

    @checksum.setter
    def checksum(self, value: str) -> None:
        self._checksum = value

    @property
    def etag(self) -> "Optional[str]":
        return self._etag

    @etag.setter
    def etag(self, value: str) -> None:
        self._etag = value

    @property
    def version_id(self) -> "Optional[str]":
        return self._version_id

    @version_id.setter
    def version_id(self, value: str) -> None:
        self._version_id = value

    def update_metadata(self, metadata: "dict[str, Any]") -> None:
        """Update the file metadata.

        Args:
            metadata: New metadata to merge with existing metadata.
        """
        self.metadata.update(metadata)

    def to_dict(self) -> "dict[str, Any]":
        """Convert FileObject to a dictionary for storage or serialization.

        Note: The 'backend' attribute is intentionally excluded as it's often
              not serializable or relevant for storage representations.
              The 'extra' dict is included.

        Returns:
            dict[str, Any]: A dictionary representation of the file information.
        """
        # Use dataclasses.asdict and filter out the backend
        return {
            "filename": self.path,
            "content_type": self.content_type,
            "size": self.size,
            "last_modified": self.last_modified,
            "checksum": self.checksum,
            "etag": self.etag,
            "version_id": self.version_id,
            "metadata": self.metadata,
            "backend": self.backend.key,
        }

    def get_content(self, *, options: "Optional[dict[str, Any]]" = None) -> bytes:
        """Get the file content from the storage backend.

        Args:
            options: Optional backend-specific options.

        Returns:
            bytes: The file content.
        """
        return self.backend.get_content(self.path, options=options)

    async def get_content_async(self, *, options: "Optional[dict[str, Any]]" = None) -> bytes:
        """Get the file content from the storage backend asynchronously.

        Args:
            options: Optional backend-specific options.

        Returns:
            bytes: The file content.
        """
        return await self.backend.get_content_async(self.path, options=options)

    def sign(
        self,
        *,
        expires_in: "Optional[int]" = None,
        for_upload: bool = False,
    ) -> str:
        """Generate a signed URL for the file.

        Args:
            expires_in: Optional expiration time in seconds.
            for_upload: Whether the URL is for upload.

        Raises:
            RuntimeError: If no signed URL is generated.

        Returns:
            str: The signed URL.
        """
        result = self.backend.sign(self.path, expires_in=expires_in, for_upload=for_upload)
        if isinstance(result, list):
            if not result:
                msg = "No signed URL generated"
                raise RuntimeError(msg)
            return result[0]
        return result

    async def sign_async(
        self,
        *,
        expires_in: "Optional[int]" = None,
        for_upload: bool = False,
    ) -> str:
        """Generate a signed URL for the file asynchronously.

        Args:
            expires_in: Optional expiration time in seconds.
            for_upload: Whether the URL is for upload.

        Returns:
            str: The signed URL.

        Raises:
            RuntimeError: If no signed URL is generated.
        """
        result = await self.backend.sign_async(self.path, expires_in=expires_in, for_upload=for_upload)
        if isinstance(result, list):
            if not result:
                msg = "No signed URL generated"
                raise RuntimeError(msg)
            return result[0]
        return result

    def delete(self) -> None:
        """Delete the file from storage.

        Raises:
            RuntimeError: If no backend is configured or path is missing.
        """
        if not self.backend:
            msg = "No storage backend configured"
            raise RuntimeError(msg)
        self.backend.delete_object(self.path)

    async def delete_async(self) -> None:
        """Delete the file from storage asynchronously."""
        await self.backend.delete_object_async(self.path)

    def save(
        self,
        data: Optional[DataLike] = None,
        *,
        use_multipart: Optional[bool] = None,
        chunk_size: int = 5 * 1024 * 1024,
        max_concurrency: int = 12,
    ) -> "FileObject":
        """Save data to the storage backend using this FileObject's metadata.

        If `data` is provided, it is used directly.
        If `data` is None, checks internal source_content or source_path.
        Clears pending attributes after successful save.

        Args:
            data: Optional data to save (bytes, iterator, file-like, Path). If None,
                  internal pending data is used.
            use_multipart: Passed to the backend's save method.
            chunk_size: Passed to the backend's save method.
            max_concurrency: Passed to the backend's save method.

        Returns:
            The updated FileObject instance returned by the backend.

        Raises:
            TypeError: If trying to save async data synchronously.
        """

        if data is None and self._pending_source_content is not None:
            data = self._pending_source_content  # type: ignore[assignment]
        elif data is None and self._pending_source_path is not None:
            data = self._pending_source_path

        if data is None:
            msg = "No data provided and no pending content/path found to save."
            raise TypeError(msg)

        # The backend's save method is expected to update the FileObject instance in-place
        # and return the updated instance.
        updated_self = self.backend.save_object(
            file_object=self,
            data=data,
            use_multipart=use_multipart,
            chunk_size=chunk_size,
            max_concurrency=max_concurrency,
        )

        # Clear pending attributes after successful save
        self._pending_source_content = None
        self._pending_source_path = None

        return updated_self

    async def save_async(
        self,
        data: Optional[AsyncDataLike] = None,
        *,
        use_multipart: Optional[bool] = None,
        chunk_size: int = 5 * 1024 * 1024,
        max_concurrency: int = 12,
    ) -> "FileObject":
        """Save data to the storage backend asynchronously.

        If `data` is provided, it is used directly.
        If `data` is None, checks internal source_content or source_path.
        Clears pending attributes after successful save.
        Uses asyncio.to_thread for reading source_path if backend doesn't handle Path directly.

        Args:
            data: Optional data to save (bytes, async iterator, file-like, Path, etc.).
                  If None, internal pending data is used.
            use_multipart: Passed to the backend's async save method.
            chunk_size: Passed to the backend's async save method.
            max_concurrency: Passed to the backend's async save method.

        Returns:
            The updated FileObject instance returned by the backend.

        Raises:
            TypeError: If trying to save sync data asynchronously.
        """

        if data is None and self._pending_source_content is not None:
            data = self._pending_source_content
        elif data is None and self._pending_source_path is not None:
            data = self._pending_source_path

        if data is None:
            msg = "No data provided and no pending content/path found to save."
            raise TypeError(msg)

        # Backend's async save method updates the FileObject instance
        updated_self = await self.backend.save_object_async(
            file_object=self,
            data=data,  # Pass the determined data source
            use_multipart=use_multipart,
            chunk_size=chunk_size,
            max_concurrency=max_concurrency,
        )

        # Clear pending attributes after successful save
        self._pending_source_content = None
        self._pending_source_path = None

        return updated_self

    @classmethod
    def __get_pydantic_core_schema__(
        cls,
        source_type: Any,
        handler: "GetCoreSchemaHandler",  # Use imported GetCoreSchemaHandler
    ) -> "core_schema.CoreSchema":  # Use imported core_schema
        """Get the Pydantic core schema for FileObject.

        This method defines how Pydantic should validate and serialize FileObject instances.
        It creates a schema that validates dictionaries with the required fields and
        converts them to FileObject instances.

        Raises:
            MissingDependencyError: If Pydantic is not installed when this method is called.

        Args:
            source_type: The source type (FileObject)
            handler: The Pydantic schema handler

        Returns:
            A Pydantic core schema for FileObject
        """
        if not PYDANTIC_INSTALLED:
            raise MissingDependencyError(package="pydantic")

        def validate_from_dict(data: dict[str, Any]) -> "FileObject":
            # We expect a dictionary derived from to_dict()
            # We need to resolve the backend string back to an instance if needed
            backend_input = data.get("backend")
            if backend_input is None:
                msg = "backend is required"
                raise TypeError(msg)
            key = backend_input if isinstance(backend_input, str) else backend_input.key
            return cls(
                backend=key,
                filename=data["filename"],
                to_filename=data.get("to_filename"),
                content_type=data.get("content_type"),
                size=data.get("size"),
                last_modified=data.get("last_modified"),
                checksum=data.get("checksum"),
                etag=data.get("etag"),
                version_id=data.get("version_id"),
                metadata=data.get("metadata"),
            )

        typed_dict_schema = core_schema.typed_dict_schema(
            {
                "filename": core_schema.typed_dict_field(core_schema.str_schema()),
                "backend": core_schema.typed_dict_field(core_schema.str_schema()),
                "to_filename": core_schema.typed_dict_field(core_schema.str_schema(), required=False),
                "content_type": core_schema.typed_dict_field(core_schema.str_schema(), required=False),
                "size": core_schema.typed_dict_field(core_schema.int_schema(), required=False),
                "last_modified": core_schema.typed_dict_field(core_schema.float_schema(), required=False),
                "checksum": core_schema.typed_dict_field(core_schema.str_schema(), required=False),
                "etag": core_schema.typed_dict_field(core_schema.str_schema(), required=False),
                "version_id": core_schema.typed_dict_field(core_schema.str_schema(), required=False),
                "metadata": core_schema.typed_dict_field(
                    core_schema.nullable_schema(
                        core_schema.dict_schema(core_schema.str_schema(), core_schema.any_schema())
                    ),
                    required=False,
                ),
            }
        )

        validation_schema = core_schema.union_schema(
            [
                core_schema.is_instance_schema(cls),
                core_schema.chain_schema(
                    [
                        typed_dict_schema,
                        core_schema.no_info_plain_validator_function(validate_from_dict),
                    ]
                ),
            ]
        )

        return core_schema.json_or_python_schema(
            json_schema=validation_schema,
            python_schema=validation_schema,
            serialization=core_schema.plain_serializer_function_ser_schema(
                lambda instance: instance.to_dict(),  # pyright: ignore
                info_arg=False,
                return_schema=typed_dict_schema,
            ),  # pyright: ignore
        )


FileObjectList: TypeAlias = MutableList[FileObject]
