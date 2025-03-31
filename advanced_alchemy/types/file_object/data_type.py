from typing import TYPE_CHECKING, Any, Optional, Union

from sqlalchemy import TypeDecorator

from advanced_alchemy.types.file_object.base import StorageBackend
from advanced_alchemy.types.file_object.file import FileObject
from advanced_alchemy.types.file_object.registry import storages
from advanced_alchemy.types.json import JsonB
from advanced_alchemy.types.mutables import MutableList

if TYPE_CHECKING:
    from advanced_alchemy.types.file_object.processors import FileProcessor
    from advanced_alchemy.types.file_object.validators import FileValidator

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
    default_expires_in: int = 3600  # 1 hour
    _raw_backend: Union[str, StorageBackend]  # Store the initial argument
    _resolved_backend: "Optional[StorageBackend]" = None  # Cache for resolved backend
    validators: "list[FileValidator]"
    processors: "list[FileProcessor]"

    @property
    def python_type(self) -> "type[OptionalFileObjectOrList]":
        """Specifies the Python type used, accounting for the `multiple` flag."""
        # This provides a hint to SQLAlchemy and type checkers
        return MutableList[FileObject] if self.multiple else Optional[FileObject]  # type: ignore

    @property
    def backend(self) -> "StorageBackend":
        """Resolves and returns the storage backend instance.

        Raises:
            ValueError: If the backend key is not found in the storages registry.


        Returns:
            StorageBackend: The resolved storage backend instance.

        """
        # Return cached version if available
        if self._resolved_backend is not None:
            return self._resolved_backend

        # Resolve the backend
        resolved: StorageBackend
        if isinstance(self._raw_backend, str):
            try:
                resolved = storages.get_backend(self._raw_backend)
            except KeyError as e:
                # Raise a more specific error if the key isn't found at access time
                msg = f"Storage backend key '{self._raw_backend}' not found in registry."
                raise ValueError(msg) from e
        else:
            resolved = self._raw_backend

        # Cache the resolved backend and return it
        self._resolved_backend = resolved
        return resolved

    @property
    def storage_key(self) -> str:
        """Returns the storage key from the resolved backend."""
        return self.backend.key

    def __init__(
        self,
        backend: Union[str, StorageBackend],
        multiple: bool = False,
        default_expires_in: "Optional[int]" = None,
        validators: "Optional[list[FileValidator]]" = None,
        processors: "Optional[list[FileProcessor]]" = None,
        *args: "Any",
        **kwargs: "Any",
    ) -> None:
        """Initialize StoredObject type.

        Args:
            backend: Key to retrieve the backend or from the storage registry or storage backend to use.
            multiple: If True, stores a list of files; otherwise, a single file.
            default_expires_in: Default expiration time for signed URLs.
            validators: List of FileValidator instances.
            processors: List of FileProcessor instances.
            *args: Additional positional arguments for TypeDecorator.
            **kwargs: Additional keyword arguments for TypeDecorator.

        """
        super().__init__(*args, **kwargs)

        self.multiple = multiple
        # Store the raw backend reference without resolving it yet
        self._raw_backend = backend
        self.default_expires_in = default_expires_in or self.default_expires_in
        self.validators = validators or []
        self.processors = processors or []

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

        # Access backend via the property to ensure it's resolved
        resolved_backend = self.backend

        def _ensure_backend(obj: "FileObject") -> "FileObject":
            if obj and obj.backend is None:
                obj.backend = resolved_backend  # Use resolved backend
            return obj

        if self.multiple:
            if not isinstance(value, (list, MutableList, set)):
                # Handle case where single object is assigned to a multiple=True field
                file_obj = _ensure_backend(value)
                return [file_obj.to_dict()] if file_obj else []

            # Ensure backend is set and convert each FileObject in the list to its dict representation
            return [_ensure_backend(item).to_dict() for item in value if item]

        if isinstance(value, (list, MutableList, set)):
            msg = f"Expected a single FileObject for multiple=False, got {type(value)}"
            raise TypeError(msg)

        # Ensure backend is set and convert the single FileObject to its dict representation
        file_obj = _ensure_backend(value)
        return file_obj.to_dict() if file_obj else None

    def process_result_value(
        self, value: "Optional[Union[dict[str, Any], list[dict[str, Any]]]]", dialect: "Any"
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

        # Access backend via the property to ensure it's resolved
        resolved_backend = self.backend

        if self.multiple:
            if not isinstance(value, list):
                # Ensure value is a list even if DB returns single dict for some reason
                value = [value]
            # Pass the resolved backend when creating FileObject instances
            return MutableList([FileObject(**item, backend=resolved_backend) for item in value])
        if isinstance(value, list):
            msg = f"Expected dict from DB for multiple=False, got {type(value)}"
            raise TypeError(msg)
        # Pass the resolved backend when creating FileObject instance
        return FileObject(**value, backend=resolved_backend)
