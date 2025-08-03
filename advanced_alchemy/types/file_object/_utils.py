"""Utility functions for file object types."""

from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional
from zlib import adler32

if TYPE_CHECKING:
    from advanced_alchemy.types.file_object.base import PathLike
    from advanced_alchemy.types.file_object.file import FileObject


def get_mtime_equivalent(info: dict[str, Any]) -> Optional[float]:
    """Return standardized mtime from different implementations.

    Args:
        info: Dictionary containing file metadata

    Returns:
        Standardized timestamp or None if not available
    """
    # Check these keys in order of preference
    mtime_keys = (
        "mtime",
        "last_modified",
        "uploaded_at",
        "timestamp",
        "Last-Modified",
        "modified_at",
        "modification_time",
    )
    mtime = next((info[key] for key in mtime_keys if key in info), None)

    if mtime is None or isinstance(mtime, float):
        return mtime
    if isinstance(mtime, datetime):
        return mtime.timestamp()
    if isinstance(mtime, str):
        try:
            return datetime.fromisoformat(mtime.replace("Z", "+00:00")).timestamp()
        except ValueError:
            pass
    return None


def get_or_generate_etag(file_object: "FileObject", info: dict[str, Any], modified_time: Optional[float] = None) -> str:
    """Return standardized etag from different implementations.

    Args:
        file_object: Path to the file
        info: Dictionary containing file metadata
        modified_time: Optional modified time for the file

    Returns:
        Standardized etag or None if not available
    """
    # Check these keys in order of preference
    etag_keys = (
        "e_tag",
        "etag",
        "etag_key",
    )
    etag = next((info[key] for key in etag_keys if key in info), None)
    if etag is not None:
        return str(etag)
    if file_object.etag is not None:
        return file_object.etag
    return create_etag_for_file(file_object.path, modified_time, info.get("size", file_object.size))  # type: ignore[arg-type]


def create_etag_for_file(path: "PathLike", modified_time: Optional[float], file_size: int) -> str:
    """Create an etag.

    Notes:
        - Function is derived from flask.

    Returns:
        An etag.
    """
    check = adler32(str(path).encode("utf-8")) & 0xFFFFFFFF
    parts = [str(file_size), str(check)]
    if modified_time:
        parts.insert(0, str(modified_time))
    return f'"{"-".join(parts)}"'
