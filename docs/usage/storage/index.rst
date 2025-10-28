================
Storage Backends
================

Advanced Alchemy's FileObject type supports multiple storage backends for file storage. Storage backends handle file content persistence while file metadata is stored in the database.

Available Backends
------------------

Two storage backend implementations are available:

.. list-table::
   :header-rows: 1
   :widths: 20 40 40

   * - Backend
     - Implementation
     - Supported Services
   * - **fsspec**
     - Python-based filesystem abstraction
     - S3, GCS, Azure, SFTP, HTTP, local, and 50+ others
   * - **obstore**
     - Rust-based via PyO3 bindings
     - S3, GCS, Azure, local, memory

Backend Characteristics
-----------------------

.. list-table::
   :header-rows: 1
   :widths: 20 25 25 30

   * - Characteristic
     - fsspec
     - obstore
     - Notes
   * - Implementation
     - Pure Python
     - Rust (PyO3)
     - obstore uses native Rust async
   * - Async Support
     - Via fsspec.asyn wrappers
     - Native async/await
     - Both support async operations
   * - Ecosystem
     - 60+ filesystem implementations
     - 5 core backends
     - fsspec has broader ecosystem
   * - Installation
     - ``pip install "advanced-alchemy[fsspec]"``
     - ``pip install "advanced-alchemy[obstore]"``
     - Both have minimal dependencies
   * - Metadata Support
     - Varies by filesystem
     - S3/GCS/Azure only
     - LocalStore doesn't support metadata
   * - Signed URLs
     - Varies by filesystem
     - S3/GCS/Azure only
     - Not supported on local storage
   * - Multipart Upload
     - Via fsspec implementation
     - Native, automatic
     - obstore optimizes large files

Quick Start
-----------

Basic fsspec Setup
~~~~~~~~~~~~~~~~~~

.. code-block:: python

    from advanced_alchemy.types.file_object import storages
    from advanced_alchemy.types.file_object.backends.fsspec import FSSpecBackend

    # Local filesystem
    storages.register_backend(FSSpecBackend(
        key="local",
        fs="file",
        prefix="/var/app/uploads",
    ))

Basic obstore Setup
~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    from advanced_alchemy.types.file_object import storages
    from advanced_alchemy.types.file_object.backends.obstore import ObstoreBackend

    # Local filesystem
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

Backend Registration
--------------------

Storage backends must be registered before use:

.. code-block:: python

    from advanced_alchemy.types.file_object import storages

    # Register backend with unique key
    storages.register_backend(backend_instance)

    # Access registered backend
    backend = storages.get("local")

    # List all backends
    all_backends = storages.all()

Startup Registration
~~~~~~~~~~~~~~~~~~~~

Register backends during application startup:

.. code-block:: python

    from contextlib import asynccontextmanager
    from litestar import Litestar

    @asynccontextmanager
    async def configure_storage(app: Litestar):
        """Configure storage backends on startup."""
        # Register fsspec backend
        from advanced_alchemy.types.file_object.backends.fsspec import FSSpecBackend

        storages.register_backend(FSSpecBackend(
            key="documents",
            fs="file",
            prefix="/var/app/uploads",
        ))

        # Register obstore backend
        from advanced_alchemy.types.file_object.backends.obstore import ObstoreBackend

        storages.register_backend(ObstoreBackend(
            key="images",
            fs="s3://my-bucket/images/",
            aws_region="us-west-2",
        ))

        yield

    app = Litestar(route_handlers=[...], lifespan=[configure_storage])

Common Storage Services
-----------------------

Amazon S3
~~~~~~~~~

.. code-block:: python

    # fsspec
    import fsspec
    from advanced_alchemy.types.file_object.backends.fsspec import FSSpecBackend

    s3_fs = fsspec.filesystem(
        "s3",
        key="AWS_ACCESS_KEY",
        secret="AWS_SECRET_KEY",
        endpoint_url="https://s3.amazonaws.com",
    )
    storages.register_backend(FSSpecBackend(
        key="s3-documents",
        fs=s3_fs,
        prefix="my-bucket/documents",
    ))

    # obstore
    from advanced_alchemy.types.file_object.backends.obstore import ObstoreBackend

    storages.register_backend(ObstoreBackend(
        key="s3-documents",
        fs="s3://my-bucket/documents/",
        aws_access_key_id="AWS_ACCESS_KEY",
        aws_secret_access_key="AWS_SECRET_KEY",
        aws_region="us-west-2",
    ))

Google Cloud Storage
~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    # fsspec
    import fsspec
    from advanced_alchemy.types.file_object.backends.fsspec import FSSpecBackend

    gcs_fs = fsspec.filesystem(
        "gcs",
        token="/path/to/service-account.json",
        project="your-project",
    )
    storages.register_backend(FSSpecBackend(
        key="gcs-files",
        fs=gcs_fs,
        prefix="my-bucket/files",
    ))

    # obstore
    from advanced_alchemy.types.file_object.backends.obstore import ObstoreBackend

    storages.register_backend(ObstoreBackend(
        key="gcs-files",
        fs="gs://my-bucket/files/",
        google_service_account="/path/to/service-account.json",
    ))

Azure Blob Storage
~~~~~~~~~~~~~~~~~~

.. code-block:: python

    # fsspec
    import fsspec
    from advanced_alchemy.types.file_object.backends.fsspec import FSSpecBackend

    azure_fs = fsspec.filesystem(
        "abfs",
        connection_string="DefaultEndpointsProtocol=https;...",
    )
    storages.register_backend(FSSpecBackend(
        key="azure-blobs",
        fs=azure_fs,
        prefix="container/files",
    ))

    # obstore
    from advanced_alchemy.types.file_object.backends.obstore import ObstoreBackend

    storages.register_backend(ObstoreBackend(
        key="azure-blobs",
        fs="az://container/files/",
        azure_storage_account_name="account",
        azure_storage_account_key="key",
    ))

Local Filesystem
~~~~~~~~~~~~~~~~

.. code-block:: python

    # fsspec
    from advanced_alchemy.types.file_object.backends.fsspec import FSSpecBackend

    storages.register_backend(FSSpecBackend(
        key="local",
        fs="file",
        prefix="/var/app/uploads",
    ))

    # obstore
    from advanced_alchemy.types.file_object.backends.obstore import ObstoreBackend

    storages.register_backend(ObstoreBackend(
        key="local",
        fs="file:///var/app/uploads/",
    ))

Backend Selection
-----------------

When to Use fsspec
~~~~~~~~~~~~~~~~~~

Use fsspec when:

- Ecosystem compatibility is required (SFTP, HTTP, FTP, etc.)
- Using specialized filesystems (WebDAV, Dropbox, etc.)
- Integration with existing fsspec-based code

When to Use obstore
~~~~~~~~~~~~~~~~~~~

Use obstore when:

- Using S3, GCS, Azure, or local storage
- Native async performance is important
- Multipart upload optimization is needed

Both Backends Support
~~~~~~~~~~~~~~~~~~~~~

Both backends support:

- Async and sync file operations
- S3, GCS, Azure, and local storage
- FileObject integration
- Automatic cleanup

Configuration Patterns
----------------------

Environment Variables
~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    import os
    from advanced_alchemy.types.file_object.backends.obstore import ObstoreBackend

    storages.register_backend(ObstoreBackend(
        key="s3",
        fs=f"s3://{os.environ['S3_BUCKET']}/",
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
        aws_region=os.environ.get("AWS_REGION", "us-east-1"),
    ))

Multiple Backends
~~~~~~~~~~~~~~~~~

Register multiple backends for different use cases:

.. code-block:: python

    # Documents on S3
    storages.register_backend(ObstoreBackend(
        key="documents",
        fs="s3://company-documents/",
        aws_region="us-west-2",
    ))

    # User uploads on GCS
    storages.register_backend(ObstoreBackend(
        key="uploads",
        fs="gs://user-uploads/",
        google_service_account="/path/to/service-account.json",
    ))

    # Temporary files locally
    storages.register_backend(FSSpecBackend(
        key="temp",
        fs="file",
        prefix="/tmp/uploads",
    ))

IAM Roles (AWS)
~~~~~~~~~~~~~~~

Use IAM roles instead of credentials:

.. code-block:: python

    # obstore uses AWS SDK credential chain
    storages.register_backend(ObstoreBackend(
        key="s3",
        fs="s3://my-bucket/",
        aws_region="us-west-2",
        # No credentials needed - uses IAM role
    ))

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
        """Configure in-memory storage for tests."""
        backend = FSSpecBackend(key="test-storage", fs="memory")
        storages.register_backend(backend)
        yield backend
        storages._backends.pop("test-storage", None)

    async def test_file_operations(memory_storage):
        """Test file upload with in-memory backend."""
        from advanced_alchemy.types import FileObject

        file_obj = FileObject(
            backend="test-storage",
            filename="test.txt",
            content=b"Test content",
        )

        await file_obj.save_async()
        content = await file_obj.get_content_async()
        assert content == b"Test content"

Common Issues
-------------

Authentication Errors
~~~~~~~~~~~~~~~~~~~~~

Verify credentials are correct and have necessary permissions:

.. code-block:: python

    # S3 bucket policy example
    {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "s3:GetObject",
                    "s3:PutObject",
                    "s3:DeleteObject"
                ],
                "Resource": "arn:aws:s3:::my-bucket/*"
            }
        ]
    }

Path Separator Issues
~~~~~~~~~~~~~~~~~~~~~

Ensure correct path format for each backend:

.. code-block:: python

    # Correct
    fs="s3://bucket/"           # obstore (with trailing slash)
    fs="file"                   # fsspec (no path)
    prefix="bucket/path"        # fsspec (no leading slash)

    # Incorrect
    fs="s3://bucket"            # obstore (missing trailing slash)
    fs="file://path"            # fsspec (don't use file:// scheme)

Missing Dependencies
~~~~~~~~~~~~~~~~~~~~

Install backend-specific dependencies:

.. code-block:: bash

    # fsspec with S3
    pip install "advanced-alchemy[fsspec]" s3fs

    # fsspec with GCS
    pip install "advanced-alchemy[fsspec]" gcsfs

    # fsspec with Azure
    pip install "advanced-alchemy[fsspec]" adlfs

    # obstore (includes all backends)
    pip install "advanced-alchemy[obstore]"

Detailed Documentation
----------------------

.. toctree::
   :maxdepth: 2

   fsspec
   obstore
   configuration

See Also
--------

- :doc:`../types/file-storage` - FileObject type documentation
- :doc:`configuration` - Advanced configuration patterns
- `fsspec Documentation <https://filesystem-spec.readthedocs.io/>`_
- `obstore Documentation <https://github.com/roeap/obstore>`_
