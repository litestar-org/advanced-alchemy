from typing import TYPE_CHECKING, Any, Optional, Union

from sqlalchemy import TypeDecorator

from advanced_alchemy.types.file_object.file import FileObject
from advanced_alchemy.types.file_object.registry import storages
from advanced_alchemy.types.json import JsonB
from advanced_alchemy.types.mutables import MutableList

if TYPE_CHECKING:
    from advanced_alchemy.types.file_object.base import StorageBackend
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
    storage_key: str
    multiple: bool
    default_expires_in: int = 3600  # 1 hour
    backend: "StorageBackend"
    validators: "list[FileValidator]"
    processors: "list[FileProcessor]"

    @property
    def python_type(self) -> "type[OptionalFileObjectOrList]":
        """Specifies the Python type used, accounting for the `multiple` flag."""
        # This provides a hint to SQLAlchemy and type checkers
        return MutableList[FileObject] if self.multiple else Optional[FileObject]  # type: ignore

    def __init__(
        self,
        storage_key: str,
        multiple: bool = False,
        default_expires_in: "Optional[int]" = None,
        validators: "Optional[list[FileValidator]]" = None,
        processors: "Optional[list[FileProcessor]]" = None,
        *args: "Any",
        **kwargs: "Any",
    ) -> None:
        """Initialize StoredObject type.

        Args:
            storage_key: Key to retrieve the backend from the storage registry.
            multiple: If True, stores a list of files; otherwise, a single file.
            default_expires_in: Default expiration time for signed URLs.
            validators: List of FileValidator instances.
            processors: List of FileProcessor instances.
            *args: Additional positional arguments for TypeDecorator.
            **kwargs: Additional keyword arguments for TypeDecorator.

        """
        super().__init__(*args, **kwargs)
        self.storage_key = storage_key
        self.multiple = multiple
        self.backend = storages.get_backend(storage_key)
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

        def _ensure_backend(obj: "FileObject") -> "FileObject":
            if obj and obj.backend is None:
                obj.backend = self.backend
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

        if self.multiple:
            if not isinstance(value, list):
                value = [value]
            return MutableList([FileObject(**item, backend=self.backend) for item in value])
        if isinstance(value, list):
            msg = f"Expected dict from DB for multiple=False, got {type(value)}"
            raise TypeError(msg)
        return FileObject(**value, backend=self.backend)
