# ruff: noqa: PLR0904, PLR6301
"""Generic unified storage protocol compatible with multiple backend implementations."""

import hashlib
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Optional

if TYPE_CHECKING:
    from advanced_alchemy.types.file_object.file import FileObject


class FileProcessor:
    """Processor for file objects."""

    def process(self, file: "FileObject", file_data: Optional[bytes] = None, key: str = "") -> Optional[bytes]:
        """Process the file object. Can optionally use and return modified raw file data.

        Args:
            file: The file object to process
            file_data: The raw file data to process
            key: The key of the file object

        Returns:
            The modified raw file data
        """
        return file_data  # Default: return data unmodified


class FileExtensionProcessor(FileProcessor):
    """Processor to check the file extension."""

    def __init__(self, allowed_extensions: list[str]) -> None:
        # Normalize extensions to include dot and be lowercase
        self.allowed_extensions = {f".{ext.lstrip('.').lower()}" for ext in allowed_extensions}

    def process(self, file: "FileObject", file_data: "Optional[bytes]" = None, key: str = "") -> "Optional[bytes]":
        # Ensure filename is not None before creating Path object
        filename = file.filename or ""
        ext = Path(filename).suffix.lower()
        if not ext:
            msg = "File has no extension."
            raise ValueError(msg)
        if ext not in self.allowed_extensions:
            allowed_str = ", ".join(sorted(self.allowed_extensions))
            msg = f"File extension '{ext}' not allowed. Allowed: {allowed_str}"
            raise ValueError(msg)
        return file_data  # Return data unmodified


def default_checksum_handler(value: bytes) -> str:
    """Calculate the checksum of the file using MD5.

    Args:
        value: The file data to calculate the checksum of

    Returns:
        The MD5 checksum of the file
    """
    return hashlib.md5(value, usedforsecurity=False).hexdigest()


class ChecksumProcessor(FileProcessor):
    """Processor to calculate and add a checksum to the file object."""

    def __init__(self, checksum_handler: "Optional[Callable[[bytes], str]]" = None) -> None:
        """Initialize the ChecksumProcessor.

        Args:
            checksum_handler: Optional callable to compute the checksum. Defaults to MD5.
        """
        self.checksum_handler = checksum_handler or default_checksum_handler

    def process(self, file: "FileObject", file_data: "Optional[bytes]" = None, key: str = "") -> "Optional[bytes]":
        """Calculate checksum if data is available and add it to the file object.

        Args:
            file: The file object to process (metadata will be updated).
            file_data: The raw file data to calculate the checksum from.
            key: The key of the file object (unused here).

        Returns:
            The original file_data, unmodified.
        """
        if file_data is not None:
            checksum = self.checksum_handler(file_data)
            file.checksum = checksum  # Update the attribute directly
        # Note: This processor cannot calculate checksum for streams without buffering.
        # Checksum for streams might need to be handled by the backend during upload.
        return file_data
