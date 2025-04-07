from typing import Any, Optional, Union, cast

from sqlalchemy import TypeDecorator

from advanced_alchemy._serialization import decode_json
from advanced_alchemy.types.file_object.base import StorageBackend
from advanced_alchemy.types.file_object.file import FileObject
from advanced_alchemy.types.file_object.registry import storages
from advanced_alchemy.types.json import JsonB
from advanced_alchemy.types.mutables import MutableList

# Define the type hint for the value this TypeDecorator handles
FileObjectOrList = Union[FileObject, list[FileObject], set[FileObject], MutableList[FileObject]]
OptionalFileObjectOrList = Optional[FileObjectOrList]


class StoredObject(TypeDecorator[OptionalFileObjectOrList]):
    """Custom SQLAlchemy type for storing single or multiple file metadata.

    Stores file metadata in JSONB and handles file validation, processing,
    and storage operations through a configured storage backend.
    """

    impl = JsonB
    cache_ok = True

    # Default settings
    multiple: bool
    _raw_backend: Union[str, StorageBackend]
    _resolved_backend: "Optional[StorageBackend]" = None

    @property
    def python_type(self) -> "type[OptionalFileObjectOrList]":
        """Specifies the Python type used, accounting for the `multiple` flag."""
        # This provides a hint to SQLAlchemy and type checkers
        return MutableList[FileObject] if self.multiple else Optional[FileObject]  # type: ignore

    @property
    def backend(self) -> "StorageBackend":
        """Resolves and returns the storage backend instance."""
        # Return cached version if available
        if self._resolved_backend is None:
            self._resolved_backend = (
                storages.get_backend(self._raw_backend) if isinstance(self._raw_backend, str) else self._raw_backend
            )
        return self._resolved_backend

    @property
    def storage_key(self) -> str:
        """Returns the storage key from the resolved backend."""
        return self.backend.key

    def __init__(
        self,
        backend: Union[str, StorageBackend],
        multiple: bool = False,
        *args: "Any",
        **kwargs: "Any",
    ) -> None:
        """Initialize StoredObject type.

        Args:
            backend: Key to retrieve the backend or from the storage registry or storage backend to use.
            multiple: If True, stores a list of files; otherwise, a single file.
            *args: Additional positional arguments for TypeDecorator.
            **kwargs: Additional keyword arguments for TypeDecorator.

        """
        super().__init__(*args, **kwargs)
        self.multiple = multiple
        self._raw_backend = backend

    def process_bind_param(
        self,
        value: "Optional[FileObjectOrList]",
        dialect: "Any",
    ) -> "Optional[Union[dict[str, Any], list[dict[str, Any]]]]":
        """Convert FileObject(s) to JSON representation for the database.

        Injects the configured backend into the FileObject before conversion.

        Note: This method expects an already processed FileInfo or its dict representation.
              Use handle_upload() or handle_upload_async() for processing raw uploads.

        Args:
            value: The value to process
            dialect: The SQLAlchemy dialect

        Raises:
            TypeError: If the input value is not a FileObject or a list of FileObjects.

        Returns:
            A dictionary representing the file metadata, or None if the input value is None.
        """
        if value is None:
            return None

        if self.multiple:
            if not isinstance(value, (list, MutableList, set)):
                return [value.to_dict()] if value else []
            return [item.to_dict() for item in value if item]

        if isinstance(value, (list, MutableList, set)):
            msg = f"Expected a single FileObject for multiple=False, got {type(value)}"
            raise TypeError(msg)

        return value.to_dict() if value else None

    def process_result_value(
        self, value: "Optional[Union[bytes, str, dict[str, Any], list[dict[str, Any]]]]", dialect: "Any"
    ) -> "Optional[FileObjectOrList]":
        """Convert database JSON back to FileObject or MutableList[FileObject].

        Args:
            value: The value to process
            dialect: The SQLAlchemy dialect

        Raises:
            TypeError: If the input value is not a list of dicts.

        Returns:
            FileObject or MutableList[FileObject] or None.
        """
        if value is None:
            return None

        if self.multiple:
            if isinstance(value, dict):
                # If the DB returns a single dict, wrap it in a list
                value = [value]
            elif isinstance(value, (str, bytes)):
                # Decode JSON string or bytes to dict
                value = [cast("dict[str, Any]", decode_json(value))]
            return MutableList[FileObject]([FileObject(**v) for v in value if v])  # pyright: ignore
        if isinstance(value, list):
            msg = f"Expected dict from DB for multiple=False, got {type(value)}"
            raise TypeError(msg)
        if isinstance(value, (bytes, str)):
            value = cast("dict[str,Any]", decode_json(value))
        return FileObject(**value)
