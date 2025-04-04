"""File object types for handling file metadata and operations using storage backends.

Provides `FileObject` for representing file metadata and `StoredObject` as the SQLAlchemy
type for database persistence. Includes support for various storage backends (`fsspec`, `obstore`).

The overall design, including concepts like storage backends and the separation of file
representation from the stored type, draws inspiration from the `sqlalchemy-file` library
[https://github.com/jowilf/sqlalchemy-file]. Special thanks to its contributors.
"""

from advanced_alchemy.types.file_object.base import AsyncDataLike, PathLike, StorageBackend, StorageBackendT
from advanced_alchemy.types.file_object.data_type import StoredObject
from advanced_alchemy.types.file_object.file import FileObject, FileObjectList
from advanced_alchemy.types.file_object.registry import StorageRegistry, storages
from advanced_alchemy.types.file_object.session_tracker import FileObjectSessionTracker

__all__ = [
    "AsyncDataLike",
    "FileObject",
    "FileObjectList",
    "FileObjectSessionTracker",
    "PathLike",
    "StorageBackend",
    "StorageBackendT",
    "StorageRegistry",
    "StoredObject",
    "storages",
]
