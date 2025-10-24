================
Obstore Backend
================

Rust-based storage backend implementation with native async support.

Characteristics
---------------

- **Implementation**: Rust via PyO3 bindings
- **Async Support**: Native async/await
- **Supported Backends**: S3, GCS, Azure, local filesystem, memory
- **Installation**: ``pip install "advanced-alchemy[obstore]"``

Supported Backends
------------------

obstore provides native implementations for:

- **Amazon S3**: AWS S3, MinIO, DigitalOcean Spaces, Cloudflare R2
- **Google Cloud Storage**: GCS with service account or default credentials
- **Azure Blob Storage**: Azure with connection string or account key
- **Local Filesystem**: Local file storage
- **Memory**: In-memory storage for testing

Installation
------------

.. code-block:: bash

    pip install "advanced-alchemy[obstore]"

Basic Usage
-----------

Backend Registration
~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    from advanced_alchemy.types.file_object import storages
    from advanced_alchemy.types.file_object.backends.obstore import ObstoreBackend

    # Register backend
    storages.register_backend(ObstoreBackend(
        key="local",
        fs="file:///var/app/uploads/",
    ))

Using in Models
~~~~~~~~~~~~~~~

.. code-block:: python

    from sqlalchemy.orm import Mapped, mapped_column
    from advanced_alchemy.base import UUIDAuditBase
    from advanced_alchemy.types import FileObject, StoredObject

    class Document(UUIDAuditBase):
        __tablename__ = "documents"

        title: "Mapped[str]"
        file: "Mapped[Optional[FileObject]]" = mapped_column(
            StoredObject(backend="local")
        )

Local Filesystem
----------------

Basic Setup
~~~~~~~~~~~

.. code-block:: python

    from advanced_alchemy.types.file_object.backends.obstore import ObstoreBackend

    storages.register_backend(ObstoreBackend(
        key="local",
        fs="file:///var/app/uploads/",
    ))

Relative Paths
~~~~~~~~~~~~~~

.. code-block:: python

    import os

    # Absolute path
    upload_dir = os.path.abspath("/var/app/uploads")

    storages.register_backend(ObstoreBackend(
        key="local",
        fs=f"file://{upload_dir}/",
    ))

Amazon S3
---------

Access Key Authentication
~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    from advanced_alchemy.types.file_object.backends.obstore import ObstoreBackend

    storages.register_backend(ObstoreBackend(
        key="s3",
        fs="s3://my-bucket/",
        aws_access_key_id="AKIAIOSFODNN7EXAMPLE",
        aws_secret_access_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        aws_region="us-west-2",
    ))

IAM Role Authentication
~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    # Use IAM role (EC2, ECS, Lambda)
    storages.register_backend(ObstoreBackend(
        key="s3",
        fs="s3://my-bucket/",
        aws_region="us-west-2",
        # No credentials - uses IAM role
    ))

S3-Compatible Services
~~~~~~~~~~~~~~~~~~~~~~

MinIO
^^^^^

MinIO provides S3-compatible object storage for local development and production:

.. code-block:: python

    # Local development
    storages.register_backend(ObstoreBackend(
        key="minio",
        fs="s3://my-bucket/",
        aws_endpoint="http://localhost:9000",
        aws_access_key_id="minioadmin",
        aws_secret_access_key="minioadmin",
        aws_region="us-east-1",
        aws_allow_http=True,  # HTTP for local development
    ))

    # Production deployment
    storages.register_backend(ObstoreBackend(
        key="minio-prod",
        fs="s3://production-bucket/",
        aws_endpoint="https://minio.example.com",
        aws_access_key_id="production-key",
        aws_secret_access_key="production-secret",
        aws_region="us-east-1",
        aws_allow_http=False,  # HTTPS in production
    ))

For Docker Compose setup and multi-bucket configuration, see :ref:`minio_configuration`.

Cloudflare R2
^^^^^^^^^^^^^

.. code-block:: python

    storages.register_backend(ObstoreBackend(
        key="r2",
        fs="s3://my-bucket/",
        aws_endpoint="https://account-id.r2.cloudflarestorage.com",
        aws_access_key_id="R2_ACCESS_KEY_ID",
        aws_secret_access_key="R2_SECRET_ACCESS_KEY",
    ))

DigitalOcean Spaces
^^^^^^^^^^^^^^^^^^^

.. code-block:: python

    storages.register_backend(ObstoreBackend(
        key="spaces",
        fs="s3://my-space/",
        aws_endpoint="https://nyc3.digitaloceanspaces.com",
        aws_access_key_id="SPACES_ACCESS_KEY",
        aws_secret_access_key="SPACES_SECRET_KEY",
        aws_region="us-east-1",
    ))

Google Cloud Storage
--------------------

Service Account
~~~~~~~~~~~~~~~

.. code-block:: python

    from advanced_alchemy.types.file_object.backends.obstore import ObstoreBackend

    storages.register_backend(ObstoreBackend(
        key="gcs",
        fs="gs://my-bucket/",
        google_service_account="/path/to/service-account.json",
    ))

Default Credentials
~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    # Use application default credentials
    storages.register_backend(ObstoreBackend(
        key="gcs",
        fs="gs://my-bucket/",
        # No credentials - uses default credentials
    ))

Azure Blob Storage
------------------

Connection String
~~~~~~~~~~~~~~~~~

.. code-block:: python

    from advanced_alchemy.types.file_object.backends.obstore import ObstoreBackend

    storages.register_backend(ObstoreBackend(
        key="azure",
        fs="az://my-container/",
        azure_storage_connection_string="DefaultEndpointsProtocol=https;AccountName=...;AccountKey=...;EndpointSuffix=core.windows.net",
    ))

Account Key
~~~~~~~~~~~

.. code-block:: python

    storages.register_backend(ObstoreBackend(
        key="azure",
        fs="az://my-container/",
        azure_storage_account_name="mystorageaccount",
        azure_storage_account_key="account-key-here",
    ))

SAS Token
~~~~~~~~~

.. code-block:: python

    storages.register_backend(ObstoreBackend(
        key="azure",
        fs="az://my-container/",
        azure_storage_account_name="mystorageaccount",
        azure_storage_sas_token="sas-token-here",
    ))

Memory (Testing)
----------------

In-Memory Storage
~~~~~~~~~~~~~~~~~

.. code-block:: python

    from advanced_alchemy.types.file_object.backends.obstore import ObstoreBackend

    storages.register_backend(ObstoreBackend(
        key="memory",
        fs="memory://",
    ))

File Operations
---------------

Upload with Metadata
~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    from advanced_alchemy.types import FileObject

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

Signed URLs
~~~~~~~~~~~

.. code-block:: python

    # Download URL (expires in 1 hour)
    download_url = await file_obj.sign_async(expires_in=3600)

    # Upload URL (expires in 5 minutes)
    upload_url = await file_obj.sign_async(expires_in=300, for_upload=True)

Multipart Upload
~~~~~~~~~~~~~~~~

obstore automatically uses multipart for large files:

.. code-block:: python

    # Default settings (automatic)
    await large_file.save_async()

    # Custom chunk size and concurrency
    await large_file.save_async(
        use_multipart=True,
        chunk_size=50 * 1024 * 1024,  # 50 MB chunks
        max_concurrency=20,
    )

    # Disable multipart for small files
    await small_file.save_async(use_multipart=False)

Advanced Configuration
----------------------

Environment Variables
~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    import os
    from advanced_alchemy.types.file_object.backends.obstore import ObstoreBackend

    storages.register_backend(ObstoreBackend(
        key="s3",
        fs="s3://my-bucket/",
        aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
        aws_region=os.environ.get("AWS_REGION", "us-east-1"),
    ))

Startup Configuration
~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    from contextlib import asynccontextmanager
    from litestar import Litestar

    @asynccontextmanager
    async def configure_storage(app: Litestar):
        """Configure obstore on startup."""
        from advanced_alchemy.types.file_object.backends.obstore import ObstoreBackend

        storages.register_backend(ObstoreBackend(
            key="documents",
            fs=f"s3://{os.environ['S3_BUCKET']}/",
            aws_region=os.environ["AWS_REGION"],
        ))

        yield

    app = Litestar(route_handlers=[...], lifespan=[configure_storage])

Multiple Backends
~~~~~~~~~~~~~~~~~

.. code-block:: python

    # Documents on S3
    storages.register_backend(ObstoreBackend(
        key="documents",
        fs="s3://company-documents/",
        aws_region="us-west-2",
    ))

    # Images on GCS
    storages.register_backend(ObstoreBackend(
        key="images",
        fs="gs://company-images/",
        google_service_account="/path/to/sa.json",
    ))

    # Temporary files locally
    storages.register_backend(ObstoreBackend(
        key="temp",
        fs="file:///tmp/uploads/",
    ))

Framework Integration
---------------------

File Upload Handling
~~~~~~~~~~~~~~~~~~~~

.. tab-set::

    .. tab-item:: Litestar

        .. code-block:: python

            from litestar import post
            from litestar.datastructures import UploadFile
            from litestar.enums import RequestEncodingType
            from litestar.params import Body
            from advanced_alchemy.types import FileObject
            from typing import Annotated

            @post("/upload", signature_namespace={"DocumentService": DocumentService})
            async def upload_file(
                data: Annotated[UploadFile, Body(media_type=RequestEncodingType.MULTI_PART)],
                service: DocumentService,
            ) -> Document:
                """Upload file to storage backend."""
                # Create document with file
                doc_data = {
                    "title": data.filename or "untitled",
                    "file": FileObject(
                        backend="s3",
                        filename=data.filename or "file",
                        content_type=data.content_type or "application/octet-stream",
                        content=await data.read(),
                    ),
                }
                return await service.create(doc_data)

    .. tab-item:: FastAPI

        .. code-block:: python

            from fastapi import APIRouter, UploadFile, Depends
            from advanced_alchemy.types import FileObject

            router = APIRouter()

            @router.post("/upload")
            async def upload_file(
                file: UploadFile,
                service: DocumentService = Depends(get_document_service),
            ) -> Document:
                """Upload file to storage backend."""
                # Create document with file
                doc_data = {
                    "title": file.filename or "untitled",
                    "file": FileObject(
                        backend="s3",
                        filename=file.filename or "file",
                        content_type=file.content_type or "application/octet-stream",
                        content=await file.read(),
                    ),
                }
                return await service.create(doc_data)

Signed URL Generation
~~~~~~~~~~~~~~~~~~~~~

.. tab-set::

    .. tab-item:: Litestar

        .. code-block:: python

            from litestar import post
            from advanced_alchemy.types import FileObject

            @post("/upload-url")
            async def generate_upload_url(filename: str, content_type: str) -> dict[str, str]:
                """Generate signed upload URL for client-side upload."""
                file_obj = FileObject(
                    backend="s3",
                    filename=filename,
                    content_type=content_type,
                )

                upload_url = await file_obj.sign_async(expires_in=3600, for_upload=True)

                return {
                    "upload_url": upload_url,
                    "filename": filename,
                    "expires_in": 3600,
                }

    .. tab-item:: FastAPI

        .. code-block:: python

            from fastapi import APIRouter
            from advanced_alchemy.types import FileObject

            router = APIRouter()

            @router.post("/upload-url")
            async def generate_upload_url(filename: str, content_type: str) -> dict[str, str]:
                """Generate signed upload URL for client-side upload."""
                file_obj = FileObject(
                    backend="s3",
                    filename=filename,
                    content_type=content_type,
                )

                upload_url = await file_obj.sign_async(expires_in=3600, for_upload=True)

                return {
                    "upload_url": upload_url,
                    "filename": filename,
                    "expires_in": 3600,
                }

Testing
-------

Memory Backend
~~~~~~~~~~~~~~

.. code-block:: python

    import pytest
    from advanced_alchemy.types.file_object import storages
    from advanced_alchemy.types.file_object.backends.obstore import ObstoreBackend

    @pytest.fixture
    def memory_storage():
        """Configure in-memory obstore storage."""
        backend = ObstoreBackend(key="test", fs="memory://")
        storages.register_backend(backend)
        yield backend
        storages._backends.pop("test", None)

    async def test_file_upload(memory_storage):
        """Test file upload with obstore memory backend."""
        from advanced_alchemy.types import FileObject

        file_obj = FileObject(
            backend="test",
            filename="test.txt",
            content=b"Test content",
        )

        await file_obj.save_async()
        content = await file_obj.get_content_async()
        assert content == b"Test content"

Test Fixtures
~~~~~~~~~~~~~

.. code-block:: python

    @pytest.fixture
    async def sample_file(memory_storage):
        """Create sample file for testing."""
        from advanced_alchemy.types import FileObject

        file_obj = FileObject(
            backend="test",
            filename="sample.txt",
            content_type="text/plain",
            content=b"Sample content",
        )
        await file_obj.save_async()
        return file_obj

    async def test_file_operations(sample_file):
        """Test file operations."""
        content = await sample_file.get_content_async()
        assert content == b"Sample content"

        await sample_file.delete_async()

Performance Optimization
------------------------

Chunk Size Configuration
~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    # Small files (<10MB): disable multipart
    await small_file.save_async(use_multipart=False)

    # Medium files (10MB-1GB): use defaults
    await medium_file.save_async()

    # Large files (>1GB): increase chunk size
    await large_file.save_async(
        chunk_size=50 * 1024 * 1024,  # 50MB
        max_concurrency=20,
    )

Concurrent Operations
~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    import asyncio

    # Upload multiple files concurrently
    files = [
        FileObject(backend="s3", filename=f"file{i}.txt", content=b"data")
        for i in range(100)
    ]

    await asyncio.gather(*[f.save_async() for f in files])

Connection Reuse
~~~~~~~~~~~~~~~~

obstore reuses connections automatically:

.. code-block:: python

    # Same backend = reused connections
    backend = ObstoreBackend(key="s3", fs="s3://my-bucket/")
    storages.register_backend(backend)

    # All operations reuse the same connection pool
    await file1.save_async()
    await file2.save_async()
    await file3.save_async()

Common Issues
-------------

LocalStore Metadata Support
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

LocalStore doesn't support content-type or metadata:

.. code-block:: python

    # Metadata ignored on local filesystem
    file_obj = FileObject(
        backend="local",
        filename="test.txt",
        content_type="text/plain",  # Ignored
        metadata={"key": "value"},  # Ignored
        content=b"data",
    )

Use S3/GCS/Azure for metadata support.

Signed URL Support
~~~~~~~~~~~~~~~~~~

Not all backends support signed URLs:

.. code-block:: python

    # S3/GCS/Azure: supported
    url = await file_obj.sign_async(expires_in=3600)

    # LocalStore: NotImplementedError
    # Use cloud storage for signed URLs

Authentication Errors
~~~~~~~~~~~~~~~~~~~~~

Verify credentials and permissions:

.. code-block:: bash

    # AWS credentials
    export AWS_ACCESS_KEY_ID=your-access-key
    export AWS_SECRET_ACCESS_KEY=your-secret-key
    export AWS_REGION=us-west-2

    # GCP credentials
    export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json

Endpoint Format
~~~~~~~~~~~~~~~

Use correct URL format:

.. code-block:: python

    # Correct
    aws_endpoint="http://localhost:9000"      # With protocol
    fs="s3://bucket/"                         # With trailing slash

    # Incorrect
    aws_endpoint="localhost:9000"             # Missing protocol
    fs="s3://bucket"                          # Missing trailing slash

Migration from FSSpec
---------------------

Configuration Changes
~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    # Before (fsspec)
    import fsspec
    from advanced_alchemy.types.file_object.backends.fsspec import FSSpecBackend

    s3_fs = fsspec.filesystem(
        "s3",
        key="AWS_ACCESS_KEY",
        secret="AWS_SECRET_KEY",
    )
    storages.register_backend(FSSpecBackend(
        key="s3",
        fs=s3_fs,
        prefix="my-bucket",
    ))

    # After (obstore)
    from advanced_alchemy.types.file_object.backends.obstore import ObstoreBackend

    storages.register_backend(ObstoreBackend(
        key="s3",
        fs="s3://my-bucket/",
        aws_access_key_id="AWS_ACCESS_KEY",
        aws_secret_access_key="AWS_SECRET_KEY",
    ))

Model Code Unchanged
~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    # Models don't change
    class Document(UUIDAuditBase):
        file: "Mapped[Optional[FileObject]]" = mapped_column(
            StoredObject(backend="s3")
        )

    # FileObject API identical
    await file_obj.save_async()
    content = await file_obj.get_content_async()
    await file_obj.delete_async()

See Also
--------

- :doc:`index` - Storage backend overview
- :doc:`fsspec` - Python-based alternative backend
- :doc:`configuration` - Advanced configuration
- :doc:`../types/file-storage` - FileObject type
- `obstore Documentation <https://github.com/roeap/obstore>`_
