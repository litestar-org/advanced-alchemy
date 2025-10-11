# Obstore Storage Backend

Rust-based storage backend implementation.

**Characteristics:**
- Implementation: Rust via PyO3 bindings
- Async support: Native async/await
- Supported backends: S3, GCS, Azure, local filesystem, memory
- Additional features: Native multipart upload, metadata support

## Installation

```bash
uv add "advanced-alchemy[obstore]"
```

## FileObject Type

```python
from advanced_alchemy.types import FileObject

file_obj = FileObject(
    backend="s3",
    filename="documents/report.pdf",
    content_type="application/pdf",
    content=b"PDF content...",
    metadata={"author": "John", "version": "1.0"},
)

# Save file (async)
await file_obj.save_async()

# Get content
content = await file_obj.get_content_async()

# Generate signed URL
download_url = await file_obj.sign_async(expires_in=3600)
upload_url = await file_obj.sign_async(expires_in=3600, for_upload=True)

# Delete file
await file_obj.delete_async()
```

## Backend Configuration

### Register Backends

```python
from advanced_alchemy.types.file_object import storages
from advanced_alchemy.types.file_object.backends.obstore import ObstoreBackend
```

### Amazon S3

```python
s3_backend = ObstoreBackend(
    key="s3",
    fs="s3://my-bucket/",
    aws_access_key_id="AKIAIOSFODNN7EXAMPLE",
    aws_secret_access_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
    aws_region="us-west-2",
)
storages.register_backend(s3_backend)
```

**IAM Role (EC2/ECS/Lambda):**

```python
s3_backend = ObstoreBackend(
    key="s3",
    fs="s3://my-bucket/",
    aws_region="us-west-2",
)
storages.register_backend(s3_backend)
```

**S3-Compatible (MinIO, Spaces, R2):**

```python
# MinIO
minio_backend = ObstoreBackend(
    key="minio",
    fs="s3://my-bucket/",
    aws_endpoint="http://localhost:9000",
    aws_access_key_id="minioadmin",
    aws_secret_access_key="minioadmin",
    aws_region="us-east-1",
)
storages.register_backend(minio_backend)
```

### Google Cloud Storage

```python
gcs_backend = ObstoreBackend(
    key="gcs",
    fs="gs://my-bucket/",
    google_service_account="/path/to/service-account.json",
)
storages.register_backend(gcs_backend)
```

### Azure Blob Storage

```python
# Connection string
azure_backend = ObstoreBackend(
    key="azure",
    fs="az://my-container/",
    azure_storage_connection_string="DefaultEndpointsProtocol=https;AccountName=...",
)
storages.register_backend(azure_backend)

# Account key
azure_backend = ObstoreBackend(
    key="azure",
    fs="az://my-container/",
    azure_storage_account_name="mystorageaccount",
    azure_storage_account_key="account-key-here",
)
storages.register_backend(azure_backend)
```

### Local Filesystem

```python
local_backend = ObstoreBackend(
    key="local",
    fs="file:///var/storage/uploads/",
)
storages.register_backend(local_backend)
```

### In-Memory (Testing)

```python
memory_backend = ObstoreBackend(
    key="memory",
    fs="memory://",
)
storages.register_backend(memory_backend)
```

## Using in Models

```python
from sqlalchemy.orm import Mapped, mapped_column
from advanced_alchemy.base import UUIDAuditBase
from advanced_alchemy.types import FileObject, StoredObject

class Document(UUIDAuditBase):
    __tablename__ = "documents"

    name: "Mapped[str]"

    # Single file
    attachment: "Mapped[Optional[FileObject]]" = mapped_column(
        StoredObject(backend="s3"),
        nullable=True,
    )

    # Multiple files
    images: "Mapped[Optional[list[FileObject]]]" = mapped_column(
        StoredObject(backend="s3", multiple=True),
        nullable=True,
    )
```

## Metadata Handling

```python
file_obj = FileObject(
    backend="s3",
    filename="invoice.pdf",
    content_type="application/pdf",
    metadata={
        "invoice_number": "INV-2025-001",
        "customer_id": "12345",
        "amount": "1500.00",
    },
    content=pdf_bytes,
)
await file_obj.save_async()

# Retrieve metadata
content = await file_obj.get_content_async()
print(file_obj.metadata["invoice_number"])

# Update metadata
file_obj.update_metadata({"status": "paid"})
await file_obj.save_async()
```

**Note:** LocalStore doesn't support metadata - use cloud storage (S3/GCS/Azure) for metadata persistence.

## Multipart Upload

Obstore automatically uses multipart for large files:

```python
# Default settings
await file_obj.save_async(
    use_multipart=True,
    chunk_size=5 * 1024 * 1024,  # 5MB
    max_concurrency=12,
)

# Large files (>1GB)
await file_obj.save_async(
    chunk_size=50 * 1024 * 1024,  # 50MB
    max_concurrency=20,
)

# Disable for small files
await file_obj.save_async(use_multipart=False)
```

## Migration from FSSpec

**Before (FSSpec):**

```python
from advanced_alchemy.types.file_object.backends.fsspec import FSSpecBackend
import fsspec

s3fs = fsspec.filesystem("s3", key="KEY", secret="SECRET")
storages.register_backend(FSSpecBackend(
    key="s3",
    fs=s3fs,
    prefix="my-bucket",
))
```

**After (Obstore):**

```python
from advanced_alchemy.types.file_object.backends.obstore import ObstoreBackend

storages.register_backend(ObstoreBackend(
    key="s3",
    fs="s3://my-bucket/",
    aws_access_key_id="KEY",
    aws_secret_access_key="SECRET",
))
```

The `FileObject` API remains identical - only backend registration changes.

## Testing

```python
import pytest
from advanced_alchemy.types import FileObject

@pytest.mark.asyncio
async def test_obstore_upload():
    """Test obstore backend upload."""
    file_obj = FileObject(
        backend="s3",
        filename="test/migration.txt",
        content=b"Migration test",
    )

    await file_obj.save_async()
    content = await file_obj.get_content_async()
    assert content == b"Migration test"
    await file_obj.delete_async()
```

## Configuration Patterns

### Environment Variables

```python
import os

storages.register_backend(ObstoreBackend(
    key="s3",
    fs="s3://my-bucket/",
    aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
    aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
    aws_region=os.environ.get("AWS_REGION", "us-east-1"),
))
```

### Startup Configuration

```python
from contextlib import asynccontextmanager
from litestar import Litestar

@asynccontextmanager
async def lifespan(app: Litestar):
    storages.register_backend(ObstoreBackend(
        key="s3",
        fs=f"s3://{os.environ['S3_BUCKET']}/",
        aws_region=os.environ["AWS_REGION"],
    ))
    yield

app = Litestar(route_handlers=[...], lifespan=[lifespan])
```

### Signed URLs

```python
# Generate signed URL for download
download_url = await file_obj.sign_async(expires_in=3600)

# Generate signed URL for upload
upload_url = await file_obj.sign_async(expires_in=300, for_upload=True)
```

### Chunk Size Configuration

```python
# Small files (<10MB): disable multipart
await small_file.save_async(use_multipart=False)

# Medium files (10MB-1GB): defaults work
await medium_file.save_async()

# Large files (>1GB): increase chunk size
await large_file.save_async(
    chunk_size=50 * 1024 * 1024,
    max_concurrency=20,
)
```

## Common Issues

### LocalStore Doesn't Support Metadata

LocalStore silently ignores content-type and metadata. Use S3/GCS/Azure for metadata support.

### Authentication Failures

Some backends (like LocalStore) don't support signed URLs. Use cloud storage for signed URL support.

### Endpoint URL Format

Use full URL with protocol:

```python
aws_endpoint="http://localhost:9000"  # With protocol
```

## See Also

- [FSSpec Storage Guide](fsspec.md) - Alternative storage backend
- [Quick Reference](../quick-reference/quick-reference.md) - Common patterns
- [Testing Guide](../testing/testing.md) - Testing file storage
- [Obstore Documentation](https://github.com/roeap/obstore) - Official obstore docs
