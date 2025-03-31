"""File object types for handling file metadata and operations."""

from advanced_alchemy.types.file_object.base import AsyncDataLike, PathLike, StorageBackend, StorageBackendT
from advanced_alchemy.types.file_object.data_type import StoredObject
from advanced_alchemy.types.file_object.file import FileObject, FileObjectList
from advanced_alchemy.types.file_object.processors import FileExtensionProcessor, FileProcessor
from advanced_alchemy.types.file_object.registry import StorageRegistry, storages
from advanced_alchemy.types.file_object.tracker import FileObjectSessionTracker
from advanced_alchemy.types.file_object.validators import FileValidator, MaxSizeValidator

__all__ = [
    "AsyncDataLike",
    "FileExtensionProcessor",
    "FileObject",
    "FileObjectList",
    "FileObjectSessionTracker",
    "FileProcessor",
    "FileValidator",
    "MaxSizeValidator",
    "PathLike",
    "StorageBackend",
    "StorageBackendT",
    "StorageRegistry",
    "StoredObject",
    "storages",
]
