# FSSpec File Storage

Using Advanced Alchemy's FileObject type with fsspec backends for local, S3, GCS, Azure, and more.

## Installation

```bash
# Basic fsspec support
uv add "advanced-alchemy[fsspec]"

# With S3
uv add "advanced-alchemy[fsspec]" s3fs

# With GCS
uv add "advanced-alchemy[fsspec]" gcsfs

# With Azure
uv add "advanced-alchemy[fsspec]" adlfs
```

## FileObject Type

```python
from advanced_alchemy.types import FileObject

file_obj = FileObject(
    backend="local",
    filename="document.pdf",
    content_type="application/pdf",
    content=pdf_bytes,
)

# Save file
await file_obj.save_async()  # or file_obj.save() for sync

# Get content
content = await file_obj.get_content_async()

# Generate signed URL (if backend supports it)
url = file_obj.sign(expires_in=3600)

# Delete file
await file_obj.delete_async()
```

## Backend Configuration

### Register Backends Before Use

```python
from advanced_alchemy.types import storages
from advanced_alchemy.types.file_object.backends.fsspec import FSSpecBackend
```

### Local Filesystem

```python
local_backend = FSSpecBackend(
    key="local",
    fs="file",
    prefix="/var/app/uploads",  # Optional
)
storages.register_backend(local_backend)
```

### Amazon S3

```bash
uv add s3fs
```

```python
import fsspec

s3_fs = fsspec.filesystem(
    "s3",
    key="YOUR_ACCESS_KEY",
    secret="YOUR_SECRET_KEY",
    endpoint_url="https://s3.amazonaws.com",
)

s3_backend = FSSpecBackend(
    key="s3-documents",
    fs=s3_fs,
    prefix="my-bucket/documents",
)
storages.register_backend(s3_backend)
```

### Google Cloud Storage

```bash
uv add gcsfs
```

```python
import fsspec

gcs_fs = fsspec.filesystem(
    "gcs",
    token="/path/to/service-account.json",
    project="your-project-id",
)

gcs_backend = FSSpecBackend(
    key="gcs-files",
    fs=gcs_fs,
    prefix="my-bucket/files",
)
storages.register_backend(gcs_backend)
```

### Azure Blob Storage

```bash
uv add adlfs
```

```python
import fsspec

azure_fs = fsspec.filesystem(
    "abfs",
    connection_string="DefaultEndpointsProtocol=https;AccountName=...",
)

azure_backend = FSSpecBackend(
    key="azure-blobs",
    fs=azure_fs,
    prefix="mycontainer/files",
)
storages.register_backend(azure_backend)
```

## Using in Models

```python
from sqlalchemy.orm import Mapped, mapped_column
from advanced_alchemy.base import UUIDAuditBase
from advanced_alchemy.types import FileObject
from advanced_alchemy.types.file_object.data_type import StoredObject

class Document(UUIDAuditBase):
    __tablename__ = "documents"

    name: "Mapped[str]"

    # Single file
    file: "Mapped[Optional[FileObject]]" = mapped_column(
        StoredObject(backend="local")
    )

    # Multiple files
    attachments: "Mapped[Optional[list[FileObject]]]" = mapped_column(
        StoredObject(backend="local", multiple=True)
    )
```

## File Upload Pattern

```python
from litestar import post
from litestar.datastructures import UploadFile
from advanced_alchemy.types import FileObject

@post("/upload")
async def upload_file(
    data: UploadFile,
    documents_service: "DocumentService",
) -> "Document":
    """Upload file to storage."""
    obj = await documents_service.create(
        DocumentModel(
            name=data.filename or "uploaded_file",
            file=FileObject(
                backend="local",
                filename=data.filename or "uploaded_file",
                content_type=data.content_type,
                content=await data.read(),
            ),
        )
    )
    return documents_service.to_schema(obj, schema_type=Document)
```

## Testing

### In-Memory Backend

```python
import pytest
from advanced_alchemy.types import storages
from advanced_alchemy.types.file_object.backends.fsspec import FSSpecBackend

@pytest.fixture
def memory_storage():
    """Configure in-memory storage for tests."""
    backend = FSSpecBackend(
        key="test-storage",
        fs="memory",
    )
    storages.register_backend(backend)
    yield backend
    storages._backends.pop("test-storage", None)

async def test_file_upload(memory_storage, documents_service):
    """Test file upload with in-memory storage."""
    doc = await documents_service.create(
        DocumentModel(
            name="test.txt",
            file=FileObject(
                backend="test-storage",
                filename="test.txt",
                content_type="text/plain",
                content=b"Hello, World!",
            ),
        )
    )
    assert doc.file is not None
    content = await doc.file.get_content_async()
    assert content == b"Hello, World!"
```

## Common Patterns

### Unique Filenames

```python
from uuid import uuid4
from pathlib import Path

def generate_storage_path(original_filename: str) -> str:
    """Generate unique storage path."""
    ext = Path(original_filename).suffix
    return f"{uuid4()}{ext}"

file_obj = FileObject(
    backend="local",
    filename=data.filename or "file",  # Original name
    to_filename=generate_storage_path(data.filename or "file"),  # Stored name
    content=await data.read(),
)
```

### File Size Validation

```python
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

content = await data.read()
if len(content) > MAX_FILE_SIZE:
    raise ValidationException("file size exceeds maximum")
```

### File Type Validation

```python
ALLOWED_CONTENT_TYPES = {"application/pdf", "image/jpeg", "image/png"}

if data.content_type not in ALLOWED_CONTENT_TYPES:
    raise ValidationException(f"file type {data.content_type} not allowed")
```

## See Also

- [Obstore Storage Guide](obstore.md) - High-performance Rust-based alternative
- [Quick Reference](../quick-reference/quick-reference.md) - Common patterns
- [Testing Guide](../testing/testing.md) - Testing file storage
- [FSSpec Documentation](https://filesystem-spec.readthedocs.io/) - Official fsspec docs
