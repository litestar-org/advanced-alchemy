"""Utility functions for file object types."""

from datetime import datetime
from typing import Any, Optional


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


def get_etag_equivalent(info: dict[str, Any]) -> Optional[str]:
    """Return standardized etag from different implementations.

    Args:
        info: Dictionary containing file metadata

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
    if etag is None:
        return None
    return str(etag)
