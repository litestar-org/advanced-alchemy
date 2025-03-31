# ruff: noqa: PLR0904, PLR6301


from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from advanced_alchemy.types.file_object.file import FileObject


class FileValidator:
    """Validator for file objects."""

    def validate(self, file: "FileObject", file_data: Optional[bytes] = None, key: str = "") -> None:
        """Validate the file object. Can optionally use raw file data."""


class MaxSizeValidator(FileValidator):
    """Validator to check the size of the file."""

    def __init__(self, max_size: int) -> None:
        self.max_size = max_size

    def validate(self, file: "FileObject", file_data: Optional[bytes] = None, key: str = "") -> None:
        file_size = file.size
        if file_size is None:
            # If size isn't available (e.g., stream), this validator might need file_data
            if file_data is not None and len(file_data) > self.max_size:
                msg = f"File size {len(file_data)} bytes exceeds maximum size of {self.max_size} bytes"
                raise ValueError(msg)
            # Cannot validate size if not provided in metadata and no raw data given
            # Alternatively, could raise an error here if size is mandatory for validation
        elif file_size > self.max_size:
            msg = f"File size {file_size} bytes exceeds maximum size of {self.max_size} bytes"
            raise ValueError(msg)
