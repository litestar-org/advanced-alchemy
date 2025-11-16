===============
FSSpec Backend
===============

Python-based storage backend with broad filesystem support through the fsspec ecosystem.

Characteristics
---------------

- **Implementation**: Pure Python
- **Async Support**: Via fsspec.asyn wrappers
- **Supported Backends**: 60+ filesystem implementations
- **Installation**: ``pip install "advanced-alchemy[fsspec]"``

Supported Filesystems
---------------------

fsspec provides implementations for:

**Cloud Storage:**

- Amazon S3 (s3fs)
- Google Cloud Storage (gcsfs)
- Azure Blob Storage (adlfs)
- Dropbox (dropboxdrivefs)

**Network Protocols:**

- SFTP (sshfs)
- FTP (ftpfs)
- HTTP/HTTPS (http)
- WebDAV (webdavfs)

**Local & Other:**

- Local filesystem (file)
- In-memory (memory)
- GitHub (github)
- Archive files (zip, tar)

See `fsspec implementations <https://filesystem-spec.readthedocs.io/en/latest/api.html#implementations>`_ for complete list.

Installation
------------

Basic Installation
~~~~~~~~~~~~~~~~~~

.. code-block:: bash

    pip install "advanced-alchemy[fsspec]"

Cloud Provider Dependencies
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: bash

    # Amazon S3
    pip install s3fs

    # Google Cloud Storage
    pip install gcsfs

    # Azure Blob Storage
    pip install adlfs

    # SFTP
    pip install sshfs

Basic Usage
-----------

Backend Registration
~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    from advanced_alchemy.types.file_object import storages
    from advanced_alchemy.types.file_object.backends.fsspec import FSSpecBackend

    # Register backend
    storages.register_backend(FSSpecBackend(
        key="local",
        fs="file",
        prefix="/var/app/uploads",
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

    from advanced_alchemy.types.file_object.backends.fsspec import FSSpecBackend

    storages.register_backend(FSSpecBackend(
        key="local",
        fs="file",
        prefix="/var/app/uploads",
    ))

Auto-Create Directories
~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    import fsspec

    fs = fsspec.filesystem("file", auto_mkdir=True)

    storages.register_backend(FSSpecBackend(
        key="local",
        fs=fs,
        prefix="/var/app/uploads",
    ))

Amazon S3
---------

Basic Configuration
~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    import fsspec
    from advanced_alchemy.types.file_object.backends.fsspec import FSSpecBackend

    s3_fs = fsspec.filesystem(
        "s3",
        key="AWS_ACCESS_KEY_ID",
        secret="AWS_SECRET_ACCESS_KEY",
        endpoint_url="https://s3.amazonaws.com",
    )

    storages.register_backend(FSSpecBackend(
        key="s3-documents",
        fs=s3_fs,
        prefix="my-bucket/documents",
    ))

IAM Role Authentication
~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    # Use IAM role (EC2, ECS, Lambda)
    s3_fs = fsspec.filesystem("s3")

    storages.register_backend(FSSpecBackend(
        key="s3-documents",
        fs=s3_fs,
        prefix="my-bucket/documents",
    ))

S3-Compatible Services
~~~~~~~~~~~~~~~~~~~~~~

MinIO, DigitalOcean Spaces, Cloudflare R2:

.. code-block:: python

    # MinIO
    minio_fs = fsspec.filesystem(
        "s3",
        key="minioadmin",
        secret="minioadmin",
        endpoint_url="http://localhost:9000",
        use_ssl=False,
    )

    storages.register_backend(FSSpecBackend(
        key="minio",
        fs=minio_fs,
        prefix="my-bucket",
    ))

    # Cloudflare R2
    r2_fs = fsspec.filesystem(
        "s3",
        key="R2_ACCESS_KEY_ID",
        secret="R2_SECRET_ACCESS_KEY",
        endpoint_url="https://account-id.r2.cloudflarestorage.com",
    )

    storages.register_backend(FSSpecBackend(
        key="r2",
        fs=r2_fs,
        prefix="my-bucket",
    ))

Google Cloud Storage
--------------------

Service Account
~~~~~~~~~~~~~~~

.. code-block:: python

    import fsspec
    from advanced_alchemy.types.file_object.backends.fsspec import FSSpecBackend

    gcs_fs = fsspec.filesystem(
        "gcs",
        token="/path/to/service-account.json",
        project="your-project-id",
    )

    storages.register_backend(FSSpecBackend(
        key="gcs-files",
        fs=gcs_fs,
        prefix="my-bucket/files",
    ))

Default Credentials
~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    # Use application default credentials
    gcs_fs = fsspec.filesystem("gcs", token="google_default")

    storages.register_backend(FSSpecBackend(
        key="gcs-files",
        fs=gcs_fs,
        prefix="my-bucket/files",
    ))

Azure Blob Storage
------------------

Connection String
~~~~~~~~~~~~~~~~~

.. code-block:: python

    import fsspec
    from advanced_alchemy.types.file_object.backends.fsspec import FSSpecBackend

    azure_fs = fsspec.filesystem(
        "abfs",
        connection_string="DefaultEndpointsProtocol=https;AccountName=...;AccountKey=...;EndpointSuffix=core.windows.net",
    )

    storages.register_backend(FSSpecBackend(
        key="azure-blobs",
        fs=azure_fs,
        prefix="container/files",
    ))

Account Key
~~~~~~~~~~~

.. code-block:: python

    azure_fs = fsspec.filesystem(
        "abfs",
        account_name="mystorageaccount",
        account_key="account-key-here",
    )

    storages.register_backend(FSSpecBackend(
        key="azure-blobs",
        fs=azure_fs,
        prefix="container/files",
    ))

SFTP
----

Password Authentication
~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    import fsspec
    from advanced_alchemy.types.file_object.backends.fsspec import FSSpecBackend

    sftp_fs = fsspec.filesystem(
        "sftp",
        host="sftp.example.com",
        username="user",
        password="password",
    )

    storages.register_backend(FSSpecBackend(
        key="sftp-uploads",
        fs=sftp_fs,
        prefix="/remote/path",
    ))

SSH Key Authentication
~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    sftp_fs = fsspec.filesystem(
        "sftp",
        host="sftp.example.com",
        username="user",
        client_keys=["/path/to/private_key"],
    )

    storages.register_backend(FSSpecBackend(
        key="sftp-uploads",
        fs=sftp_fs,
        prefix="/remote/path",
    ))

HTTP/HTTPS
----------

Public Files
~~~~~~~~~~~~

.. code-block:: python

    import fsspec
    from advanced_alchemy.types.file_object.backends.fsspec import FSSpecBackend

    http_fs = fsspec.filesystem("http")

    storages.register_backend(FSSpecBackend(
        key="cdn",
        fs=http_fs,
        prefix="https://cdn.example.com/files",
    ))

Authenticated
~~~~~~~~~~~~~

.. code-block:: python

    http_fs = fsspec.filesystem(
        "http",
        client_kwargs={"headers": {"Authorization": "Bearer token"}},
    )

    storages.register_backend(FSSpecBackend(
        key="api-storage",
        fs=http_fs,
        prefix="https://api.example.com/storage",
    ))

Advanced Configuration
----------------------

Custom fsspec Options
~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    import fsspec

    # S3 with custom configuration
    s3_fs = fsspec.filesystem(
        "s3",
        key="AWS_ACCESS_KEY_ID",
        secret="AWS_SECRET_ACCESS_KEY",
        config_kwargs={
            "max_pool_connections": 50,
            "connect_timeout": 60,
            "read_timeout": 60,
        },
        use_ssl=True,
        s3_additional_kwargs={
            "ServerSideEncryption": "AES256",
        },
    )

    storages.register_backend(FSSpecBackend(
        key="s3-encrypted",
        fs=s3_fs,
        prefix="my-bucket/encrypted",
    ))

Caching
~~~~~~~

fsspec supports caching for remote filesystems:

.. code-block:: python

    import fsspec

    # Cache remote files locally
    s3_fs = fsspec.filesystem(
        "s3",
        key="AWS_ACCESS_KEY_ID",
        secret="AWS_SECRET_ACCESS_KEY",
    )

    cached_fs = fsspec.filesystem(
        "filecache",
        target_protocol="s3",
        cache_storage="/tmp/fsspec_cache",
        fs=s3_fs,
    )

    storages.register_backend(FSSpecBackend(
        key="s3-cached",
        fs=cached_fs,
        prefix="my-bucket",
    ))

File Operations
---------------

Upload Pattern
~~~~~~~~~~~~~~

.. code-block:: python

    from litestar import post
    from litestar.datastructures import UploadFile
    from advanced_alchemy.types import FileObject

    @post("/upload")
    async def upload_file(
        data: UploadFile,
        service: "DocumentService",
    ) -> "Document":
        """Upload file to fsspec storage."""
        doc = await service.create(
            DocumentModel(
                title=data.filename or "untitled",
                file=FileObject(
                    backend="s3-documents",
                    filename=data.filename or "file",
                    content_type=data.content_type,
                    content=await data.read(),
                ),
            )
        )
        return service.to_schema(doc, schema_type=DocumentSchema)

Download Pattern
~~~~~~~~~~~~~~~~

.. code-block:: python

    from litestar import get
    from litestar.response import Stream

    @get("/download/{document_id:uuid}")
    async def download_file(
        document_id: UUID,
        service: "DocumentService",
    ) -> Stream:
        """Download file from fsspec storage."""
        doc = await service.get(document_id)

        if doc.file is None:
            raise NotFoundException("file not found")

        content = await doc.file.get_content_async()

        return Stream(
            content=content,
            media_type=doc.file.content_type or "application/octet-stream",
            headers={
                "Content-Disposition": f'attachment; filename="{doc.file.filename}"'
            },
        )

Testing
-------

In-Memory Backend
~~~~~~~~~~~~~~~~~

.. code-block:: python

    import pytest
    from advanced_alchemy.types.file_object import storages
    from advanced_alchemy.types.file_object.backends.fsspec import FSSpecBackend

    @pytest.fixture
    def memory_storage():
        """Configure in-memory fsspec storage."""
        backend = FSSpecBackend(key="test", fs="memory")
        storages.register_backend(backend)
        yield backend
        storages._backends.pop("test", None)

    async def test_file_upload(memory_storage):
        """Test file upload with in-memory fsspec."""
        from advanced_alchemy.types import FileObject

        file_obj = FileObject(
            backend="test",
            filename="test.txt",
            content=b"Test content",
        )

        await file_obj.save_async()
        content = await file_obj.get_content_async()
        assert content == b"Test content"

Mock S3 (moto)
~~~~~~~~~~~~~~

.. code-block:: python

    import pytest
    from moto import mock_aws
    import fsspec
    from advanced_alchemy.types.file_object.backends.fsspec import FSSpecBackend

    @pytest.fixture
    def mock_s3():
        """Mock S3 for testing."""
        with mock_aws():
            # Create bucket
            import boto3
            s3 = boto3.client("s3", region_name="us-east-1")
            s3.create_bucket(Bucket="test-bucket")

            # Register fsspec backend
            s3_fs = fsspec.filesystem("s3")
            storages.register_backend(FSSpecBackend(
                key="test-s3",
                fs=s3_fs,
                prefix="test-bucket",
            ))

            yield

            storages._backends.pop("test-s3", None)

Performance Considerations
--------------------------

Buffering
~~~~~~~~~

fsspec uses buffering for remote filesystems:

.. code-block:: python

    import fsspec

    # Increase buffer size for large files
    s3_fs = fsspec.filesystem(
        "s3",
        key="AWS_ACCESS_KEY_ID",
        secret="AWS_SECRET_ACCESS_KEY",
        default_block_size=10 * 1024 * 1024,  # 10 MB blocks
    )

Async Operations
~~~~~~~~~~~~~~~~

fsspec provides async wrappers:

.. code-block:: python

    # FileObject automatically uses async when available
    content = await file_obj.get_content_async()  # Uses fsspec async

Connection Pooling
~~~~~~~~~~~~~~~~~~

Configure connection pools for better performance:

.. code-block:: python

    import fsspec

    s3_fs = fsspec.filesystem(
        "s3",
        key="AWS_ACCESS_KEY_ID",
        secret="AWS_SECRET_ACCESS_KEY",
        config_kwargs={"max_pool_connections": 50},
    )

Common Issues
-------------

Import Errors
~~~~~~~~~~~~~

Missing filesystem-specific packages:

.. code-block:: bash

    # Error: No module named 's3fs'
    pip install s3fs

    # Error: No module named 'gcsfs'
    pip install gcsfs

    # Error: No module named 'adlfs'
    pip install adlfs

Path Issues
~~~~~~~~~~~

Ensure correct path format:

.. code-block:: python

    # Correct
    prefix="bucket/path"          # No leading slash
    prefix="/local/absolute/path" # Absolute for local

    # Incorrect
    prefix="/bucket/path"         # Leading slash for cloud
    prefix="local/relative/path"  # Relative for local (use absolute)

Authentication Failures
~~~~~~~~~~~~~~~~~~~~~~~

Verify credentials and permissions:

.. code-block:: python

    # Test filesystem directly
    import fsspec

    fs = fsspec.filesystem(
        "s3",
        key="AWS_ACCESS_KEY_ID",
        secret="AWS_SECRET_ACCESS_KEY",
    )

    # List bucket contents
    files = fs.ls("my-bucket")
    print(files)

Migration from Other Backends
------------------------------

From Local to S3
~~~~~~~~~~~~~~~~

.. code-block:: python

    # Before (local)
    storages.register_backend(FSSpecBackend(
        key="files",
        fs="file",
        prefix="/var/app/uploads",
    ))

    # After (S3)
    import fsspec

    s3_fs = fsspec.filesystem("s3", key="...", secret="...")
    storages.register_backend(FSSpecBackend(
        key="files",
        fs=s3_fs,
        prefix="my-bucket/uploads",
    ))

    # Models unchanged - only backend registration changes

See Also
--------

- :doc:`index` - Storage backend overview
- :doc:`obstore` - Rust-based alternative backend
- :doc:`configuration` - Advanced configuration
- :doc:`../types/file-storage` - FileObject type
- `fsspec Documentation <https://filesystem-spec.readthedocs.io/>`_
