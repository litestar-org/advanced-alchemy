from typing import Any, Optional, Union

from sqlalchemy import TypeDecorator

from advanced_alchemy.types.file_object.base import (
    FileObject,
    FileProcessor,
    FileValidator,
    StorageBackend,
    storages,
)
from advanced_alchemy.types.json import JsonB


class StoredObject(TypeDecorator[FileObject]):
    """Custom SQLAlchemy type for storing file metadata and handling uploads.

    Stores file metadata in JSONB and handles file validation, processing,
    and storage operations through a configured storage backend.
    """

    impl = JsonB
    cache_ok = True

    # Default settings
    storage_key: str
    default_expires_in: int = 3600  # 1 hour
    backend: "StorageBackend"
    validators: list[FileValidator]
    processors: list[FileProcessor]

    def __init__(
        self,
        storage_key: str,
        default_expires_in: Optional[int] = None,
        validators: Optional[list[FileValidator]] = None,
        processors: Optional[list[FileProcessor]] = None,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """Initialize StorageBucket type.

        Args:
            key: The name of the storage bucket.  This is used a referenced to fetch the backend from the storage registry.
            backend: Storage backend to use
            default_expires_in: Default expiration time for signed URLs
            validators: List of FileValidator instances to run before processing/storage.
            processors: List of FileProcessor instances to run before storage.
            *args: Additional positional arguments for TypeDecorator
            **kwargs: Additional keyword arguments for TypeDecorator

        Raises:
            ValueError: If backend is invalid or required parameters are missing
        """
        super().__init__(*args, **kwargs)
        self.storage_key = storage_key
        self.backend = storages.get_backend(storage_key)
        self.default_expires_in = default_expires_in or self.default_expires_in
        self.validators = validators or []
        self.processors = processors or []

    def process_bind_param(
        self, value: "Optional[Union[FileObject, dict[str, Any]]]", dialect: Any
    ) -> "Optional[dict[str, Any]]":
        """Convert FileInfo object/dict to database JSON format.

        Note: This method expects an already processed FileInfo or its dict representation.
              Use handle_upload() or handle_upload_async() for processing raw uploads.

        Args:
            value: The value to process
            dialect: The SQLAlchemy dialect

        Returns:
            A dictionary representing the file metadata, or None if the input value is None.
        """
        if value is None:
            return None
        if isinstance(value, FileObject):
            return value.to_dict()
        # Assuming it's already a dict suitable for JSONB
        return value

    def process_result_value(self, value: "Optional[dict[str, Any]]", dialect: Any) -> "Optional[FileObject]":
        """Convert database JSON format back to FileInfo object.

        Args:
            value: The value to process
            dialect: The SQLAlchemy dialect

        Returns:
            FileInfo object or None.
        """
        if value is None:
            return None

        # Inject the backend into the file info - crucial for functionality
        value["backend"] = self.backend
        return FileObject.from_dict(value)
