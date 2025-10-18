========================
Storage Configuration
========================

Advanced configuration patterns for file storage backends.

Configuration Strategies
------------------------

Environment-Based
~~~~~~~~~~~~~~~~~

Store configuration in environment variables:

.. code-block:: python

    import os
    from advanced_alchemy.types.file_object import storages
    from advanced_alchemy.types.file_object.backends.obstore import ObstoreBackend

    def configure_storage_from_env():
        """Configure storage from environment variables."""
        storage_backend = os.environ.get("STORAGE_BACKEND", "local")

        if storage_backend == "s3":
            storages.register_backend(ObstoreBackend(
                key="default",
                fs=f"s3://{os.environ['S3_BUCKET']}/",
                aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
                aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
                aws_region=os.environ.get("AWS_REGION", "us-east-1"),
            ))
        elif storage_backend == "gcs":
            storages.register_backend(ObstoreBackend(
                key="default",
                fs=f"gs://{os.environ['GCS_BUCKET']}/",
                google_service_account=os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"),
            ))
        elif storage_backend == "azure":
            storages.register_backend(ObstoreBackend(
                key="default",
                fs=f"az://{os.environ['AZURE_CONTAINER']}/",
                azure_storage_connection_string=os.environ.get("AZURE_STORAGE_CONNECTION_STRING"),
            ))
        else:  # local
            from advanced_alchemy.types.file_object.backends.fsspec import FSSpecBackend
            storages.register_backend(FSSpecBackend(
                key="default",
                fs="file",
                prefix=os.environ.get("UPLOAD_DIR", "/var/app/uploads"),
            ))

Configuration File
~~~~~~~~~~~~~~~~~~

Load configuration from YAML/TOML/JSON:

.. code-block:: python

    import toml
    from advanced_alchemy.types.file_object.backends.obstore import ObstoreBackend

    def configure_storage_from_file(config_path: str):
        """Configure storage from TOML file."""
        config = toml.load(config_path)

        for backend_config in config["storage"]["backends"]:
            if backend_config["type"] == "s3":
                storages.register_backend(ObstoreBackend(
                    key=backend_config["key"],
                    fs=backend_config["bucket"],
                    aws_region=backend_config["region"],
                ))

.. code-block:: toml

    # config.toml
    [storage]
    [[storage.backends]]
    key = "documents"
    type = "s3"
    bucket = "s3://company-documents/"
    region = "us-west-2"

    [[storage.backends]]
    key = "images"
    type = "gcs"
    bucket = "gs://company-images/"

Pydantic Settings
~~~~~~~~~~~~~~~~~

Use Pydantic for configuration validation:

.. code-block:: python

    from pydantic import Field
    from pydantic_settings import BaseSettings

    class StorageSettings(BaseSettings):
        """Storage configuration settings."""

        backend: str = Field(default="local")
        s3_bucket: str | None = Field(default=None)
        s3_region: str = Field(default="us-east-1")
        aws_access_key_id: str | None = Field(default=None)
        aws_secret_access_key: str | None = Field(default=None)
        upload_dir: str = Field(default="/var/app/uploads")

        class Config:
            env_prefix = "STORAGE_"

    def configure_storage(settings: StorageSettings):
        """Configure storage from Pydantic settings."""
        if settings.backend == "s3":
            from advanced_alchemy.types.file_object.backends.obstore import ObstoreBackend
            storages.register_backend(ObstoreBackend(
                key="default",
                fs=f"s3://{settings.s3_bucket}/",
                aws_access_key_id=settings.aws_access_key_id,
                aws_secret_access_key=settings.aws_secret_access_key,
                aws_region=settings.s3_region,
            ))
        else:
            from advanced_alchemy.types.file_object.backends.fsspec import FSSpecBackend
            storages.register_backend(FSSpecBackend(
                key="default",
                fs="file",
                prefix=settings.upload_dir,
            ))

Framework Integration
---------------------

Litestar Lifespan
~~~~~~~~~~~~~~~~~

.. code-block:: python

    from contextlib import asynccontextmanager
    from litestar import Litestar

    @asynccontextmanager
    async def storage_lifespan(app: Litestar):
        """Configure storage on application startup."""
        configure_storage_from_env()
        yield
        # Cleanup if needed

    app = Litestar(
        route_handlers=[...],
        lifespan=[storage_lifespan],
    )

FastAPI Lifespan
~~~~~~~~~~~~~~~~

.. code-block:: python

    from contextlib import asynccontextmanager
    from fastapi import FastAPI

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Configure storage on application startup."""
        configure_storage_from_env()
        yield

    app = FastAPI(lifespan=lifespan)

Flask Application Factory
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    from flask import Flask

    def create_app(config_name: str = "development"):
        """Flask application factory."""
        app = Flask(__name__)

        # Configure storage
        with app.app_context():
            configure_storage_from_env()

        return app

Multiple Backend Strategies
----------------------------

Backend per Use Case
~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    from advanced_alchemy.types.file_object.backends.obstore import ObstoreBackend
    from advanced_alchemy.types.file_object.backends.fsspec import FSSpecBackend

    def configure_multiple_backends():
        """Configure different backends for different use cases."""
        # User uploads on S3
        storages.register_backend(ObstoreBackend(
            key="user-uploads",
            fs="s3://user-uploads/",
            aws_region="us-west-2",
        ))

        # Product images on GCS
        storages.register_backend(ObstoreBackend(
            key="product-images",
            fs="gs://product-images/",
        ))

        # Documents on Azure
        storages.register_backend(ObstoreBackend(
            key="documents",
            fs="az://documents/",
            azure_storage_connection_string=os.environ["AZURE_STORAGE_CONNECTION_STRING"],
        ))

        # Temporary files locally
        storages.register_backend(FSSpecBackend(
            key="temp",
            fs="file",
            prefix="/tmp/uploads",
        ))

Backend per Environment
~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    def configure_environment_backends(environment: str):
        """Configure backends based on environment."""
        if environment == "production":
            # Production: cloud storage
            storages.register_backend(ObstoreBackend(
                key="default",
                fs="s3://production-uploads/",
                aws_region="us-west-2",
            ))
        elif environment == "staging":
            # Staging: separate bucket
            storages.register_backend(ObstoreBackend(
                key="default",
                fs="s3://staging-uploads/",
                aws_region="us-west-2",
            ))
        else:
            # Development/testing: local storage
            from advanced_alchemy.types.file_object.backends.fsspec import FSSpecBackend
            storages.register_backend(FSSpecBackend(
                key="default",
                fs="file",
                prefix="/tmp/dev-uploads",
            ))

Security Configuration
----------------------

Credential Management
~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    # Environment variables (recommended)
    AWS_ACCESS_KEY_ID=your-access-key
    AWS_SECRET_ACCESS_KEY=your-secret-key

    # AWS credentials file (~/.aws/credentials)
    [default]
    aws_access_key_id = your-access-key
    aws_secret_access_key = your-secret-key

    # IAM roles (EC2, ECS, Lambda)
    # No credentials needed - automatically provided

Secrets Management
~~~~~~~~~~~~~~~~~~

.. code-block:: python

    # AWS Secrets Manager
    import boto3
    import json

    def get_storage_credentials():
        """Retrieve credentials from AWS Secrets Manager."""
        client = boto3.client("secretsmanager", region_name="us-west-2")
        response = client.get_secret_value(SecretId="storage-credentials")
        return json.loads(response["SecretString"])

    credentials = get_storage_credentials()
    storages.register_backend(ObstoreBackend(
        key="s3",
        fs="s3://my-bucket/",
        aws_access_key_id=credentials["access_key_id"],
        aws_secret_access_key=credentials["secret_access_key"],
        aws_region="us-west-2",
    ))

Encryption at Rest
~~~~~~~~~~~~~~~~~~

.. code-block:: python

    # S3 server-side encryption
    import fsspec

    s3_fs = fsspec.filesystem(
        "s3",
        key="AWS_ACCESS_KEY_ID",
        secret="AWS_SECRET_ACCESS_KEY",
        s3_additional_kwargs={
            "ServerSideEncryption": "AES256",
        },
    )

    from advanced_alchemy.types.file_object.backends.fsspec import FSSpecBackend
    storages.register_backend(FSSpecBackend(
        key="s3-encrypted",
        fs=s3_fs,
        prefix="my-bucket",
    ))

CORS Configuration
------------------

S3 CORS for Direct Upload
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: json

    {
        "CORSRules": [
            {
                "AllowedOrigins": ["https://app.example.com"],
                "AllowedMethods": ["GET", "PUT", "POST"],
                "AllowedHeaders": ["*"],
                "ExposeHeaders": ["ETag"],
                "MaxAgeSeconds": 3000
            }
        ]
    }

Signed URL Pattern
~~~~~~~~~~~~~~~~~~

.. code-block:: python

    from litestar import post
    from advanced_alchemy.types import FileObject

    @post("/upload-url")
    async def generate_upload_url(
        filename: str,
        content_type: str,
    ) -> "dict[str, str]":
        """Generate signed upload URL with CORS support."""
        file_obj = FileObject(
            backend="s3",
            filename=filename,
            content_type=content_type,
        )

        upload_url = await file_obj.sign_async(expires_in=300, for_upload=True)

        return {
            "upload_url": upload_url,
            "filename": filename,
            "content_type": content_type,
            "expires_in": 300,
        }

Performance Optimization
------------------------

Connection Pooling
~~~~~~~~~~~~~~~~~~

.. code-block:: python

    import fsspec

    # fsspec: configure connection pool
    s3_fs = fsspec.filesystem(
        "s3",
        key="AWS_ACCESS_KEY_ID",
        secret="AWS_SECRET_ACCESS_KEY",
        config_kwargs={
            "max_pool_connections": 50,
            "connect_timeout": 60,
            "read_timeout": 60,
        },
    )

Caching
~~~~~~~

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

    from advanced_alchemy.types.file_object.backends.fsspec import FSSpecBackend
    storages.register_backend(FSSpecBackend(
        key="s3-cached",
        fs=cached_fs,
        prefix="my-bucket",
    ))

Multipart Configuration
~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    # obstore: configure multipart thresholds
    from advanced_alchemy.types import FileObject

    # Large files: increase chunk size
    large_file = FileObject(
        backend="s3",
        filename="video.mp4",
        content=video_bytes,
    )

    await large_file.save_async(
        chunk_size=50 * 1024 * 1024,  # 50 MB chunks
        max_concurrency=20,
    )

Monitoring and Logging
----------------------

Storage Metrics
~~~~~~~~~~~~~~~

.. code-block:: python

    import logging
    from advanced_alchemy.types import FileObject

    logger = logging.getLogger(__name__)

    async def upload_with_metrics(file_obj: FileObject):
        """Upload file with metrics logging."""
        start = time.time()

        try:
            await file_obj.save_async()
            duration = time.time() - start

            logger.info(
                "file uploaded",
                extra={
                    "filename": file_obj.filename,
                    "size": file_obj.size,
                    "backend": file_obj.backend,
                    "duration_ms": duration * 1000,
                }
            )
        except Exception as e:
            logger.error(
                "file upload failed",
                extra={
                    "filename": file_obj.filename,
                    "backend": file_obj.backend,
                    "error": str(e),
                }
            )
            raise

Error Handling
~~~~~~~~~~~~~~

.. code-block:: python

    from advanced_alchemy.types import FileObject

    async def safe_upload(file_obj: FileObject, max_retries: int = 3):
        """Upload file with retry logic."""
        for attempt in range(max_retries):
            try:
                await file_obj.save_async()
                return
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                logger.warning(
                    f"upload attempt {attempt + 1} failed, retrying",
                    extra={"error": str(e)}
                )
                await asyncio.sleep(2 ** attempt)  # Exponential backoff

Testing Configuration
---------------------

Test Fixtures
~~~~~~~~~~~~~

.. code-block:: python

    import pytest
    from advanced_alchemy.types.file_object import storages
    from advanced_alchemy.types.file_object.backends.fsspec import FSSpecBackend

    @pytest.fixture(autouse=True)
    def configure_test_storage():
        """Configure memory storage for all tests."""
        backend = FSSpecBackend(key="test", fs="memory")
        storages.register_backend(backend)
        yield
        storages._backends.clear()

Environment-Specific Tests
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    import pytest
    import os

    @pytest.fixture
    def configure_storage_for_environment():
        """Configure storage based on test environment."""
        if os.environ.get("USE_REAL_S3") == "true":
            # Integration tests with real S3
            from advanced_alchemy.types.file_object.backends.obstore import ObstoreBackend
            storages.register_backend(ObstoreBackend(
                key="test",
                fs="s3://test-bucket/",
                aws_region="us-west-2",
            ))
        else:
            # Unit tests with memory storage
            from advanced_alchemy.types.file_object.backends.fsspec import FSSpecBackend
            storages.register_backend(FSSpecBackend(
                key="test",
                fs="memory"
            ))

        yield
        storages._backends.clear()

Migration Strategies
--------------------

Gradual Migration
~~~~~~~~~~~~~~~~~

.. code-block:: python

    # Register both old and new backends
    def configure_migration_backends():
        """Configure both local and S3 for gradual migration."""
        # Old backend (local)
        from advanced_alchemy.types.file_object.backends.fsspec import FSSpecBackend
        storages.register_backend(FSSpecBackend(
            key="local-legacy",
            fs="file",
            prefix="/var/app/uploads",
        ))

        # New backend (S3)
        from advanced_alchemy.types.file_object.backends.obstore import ObstoreBackend
        storages.register_backend(ObstoreBackend(
            key="s3-new",
            fs="s3://new-uploads/",
            aws_region="us-west-2",
        ))

    # Use feature flag or gradual rollout
    def get_storage_backend(user_id: UUID) -> str:
        """Determine storage backend for user."""
        if is_migrated_user(user_id):
            return "s3-new"
        return "local-legacy"

Data Migration Script
~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    async def migrate_files_to_s3():
        """Migrate files from local to S3."""
        from sqlalchemy import select
        from advanced_alchemy.types import FileObject

        stmt = select(Document).where(
            Document.file.isnot(None)
        )
        result = await session.execute(stmt)
        documents = list(result.scalars())

        for doc in documents:
            if doc.file.backend == "local-legacy":
                # Get file content
                content = await doc.file.get_content_async()

                # Create new file on S3
                new_file = FileObject(
                    backend="s3-new",
                    filename=doc.file.filename,
                    content_type=doc.file.content_type,
                    metadata=doc.file.metadata,
                    content=content,
                )

                # Save to S3
                await new_file.save_async()

                # Delete old file
                await doc.file.delete_async()

                # Update document
                doc.file = new_file
                await session.commit()

                logger.info(f"migrated file: {doc.file.filename}")

See Also
--------

- :doc:`index` - Storage backend overview
- :doc:`fsspec` - FSSpec backend details
- :doc:`obstore` - Obstore backend details
- :doc:`../types/file-storage` - FileObject type documentation
