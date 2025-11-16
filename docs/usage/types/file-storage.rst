============
File Storage
============

SQLAlchemy type for storing file objects with automatic cloud storage integration.

FileObject Type
---------------

The FileObject type stores file metadata in the database while delegating file content to configurable storage backends.

**Characteristics:**

- Python type: :class:`~advanced_alchemy.types.FileObject` or :class:`~advanced_alchemy.types.FileObjectList`
- Database storage: JSON/JSONB (metadata only)
- File content: External storage backend (S3, GCS, Azure, local)
- Automatic cleanup: Files deleted when records removed

StoredObject Column Type
-------------------------

Use StoredObject to define file storage columns:

.. code-block:: python

    from typing import Optional
    from sqlalchemy.orm import Mapped, mapped_column
    from advanced_alchemy.base import UUIDAuditBase
    from advanced_alchemy.types import FileObject, FileObjectList, StoredObject

    class Document(UUIDAuditBase):
        __tablename__ = "documents"

        title: "Mapped[str]"

        # Single file
        attachment: "Mapped[Optional[FileObject]]" = mapped_column(
            StoredObject(backend="documents"),
            nullable=True,
        )

        # Multiple files
        images: "Mapped[Optional[FileObjectList]]" = mapped_column(
            StoredObject(backend="documents", multiple=True),
            nullable=True,
        )

FileObject Attributes
---------------------

FileObject instances contain file metadata and provide file operations:

.. code-block:: python

    file_obj = FileObject(
        backend="s3",
        filename="report.pdf",
        content_type="application/pdf",
        metadata={"author": "John", "version": "1.0"},
        content=pdf_bytes,
    )

    # Attributes
    print(file_obj.backend)        # "s3"
    print(file_obj.filename)       # "report.pdf"
    print(file_obj.content_type)   # "application/pdf"
    print(file_obj.size)           # File size in bytes
    print(file_obj.metadata)       # {"author": "John", "version": "1.0"}

File Operations
---------------

Saving Files
~~~~~~~~~~~~

.. code-block:: python

    from advanced_alchemy.types import FileObject

    # Create file object
    file_obj = FileObject(
        backend="s3",
        filename="document.pdf",
        content_type="application/pdf",
        content=pdf_bytes,
    )

    # Async save
    await file_obj.save_async()

    # Sync save
    file_obj.save()

Retrieving Content
~~~~~~~~~~~~~~~~~~

.. code-block:: python

    # Async get content
    content = await file_obj.get_content_async()

    # Sync get content
    content = file_obj.get_content()

Deleting Files
~~~~~~~~~~~~~~

.. code-block:: python

    # Async delete
    await file_obj.delete_async()

    # Sync delete
    file_obj.delete()

Signed URLs
~~~~~~~~~~~

Generate temporary URLs for direct upload/download:

.. code-block:: python

    # Download URL (expires in 1 hour)
    download_url = await file_obj.sign_async(expires_in=3600)

    # Upload URL
    upload_url = await file_obj.sign_async(expires_in=300, for_upload=True)

    # Sync version
    download_url = file_obj.sign(expires_in=3600)

Metadata Management
~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    # Set metadata during creation
    file_obj = FileObject(
        backend="s3",
        filename="invoice.pdf",
        metadata={"invoice_number": "INV-001", "amount": "1500.00"},
        content=pdf_bytes,
    )

    # Update metadata
    file_obj.update_metadata({"status": "paid"})
    await file_obj.save_async()

    # Access metadata
    invoice_number = file_obj.metadata["invoice_number"]

Storage Backend Configuration
------------------------------

Storage backends must be registered before use. See :doc:`../storage/index` for detailed backend configuration.

Quick Example
~~~~~~~~~~~~~

.. code-block:: python

    from advanced_alchemy.types.file_object import storages
    from advanced_alchemy.types.file_object.backends.fsspec import FSSpecBackend

    # Register local filesystem backend
    storages.register_backend(FSSpecBackend(
        key="documents",
        fs="file",
        prefix="/var/app/uploads",
    ))

    # Now use in models
    class Document(UUIDAuditBase):
        attachment: "Mapped[Optional[FileObject]]" = mapped_column(
            StoredObject(backend="documents")
        )

Automatic File Cleanup
----------------------

When using framework integrations, file cleanup is automatic:

.. code-block:: python

    # Update file - old file deleted automatically
    doc.attachment = FileObject(
        backend="documents",
        filename="updated.pdf",
        content=new_pdf_bytes,
    )
    await session.commit()  # Old file deleted, new file saved

    # Clear file - file deleted automatically
    doc.attachment = None
    await session.commit()  # File deleted from storage

    # Delete model - all files deleted automatically
    await session.delete(doc)
    await session.commit()  # All associated files deleted

Manual Cleanup Configuration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

For non-framework applications, configure cleanup manually:

.. code-block:: python

    from advanced_alchemy.config import SQLAlchemyAsyncConfig

    config = SQLAlchemyAsyncConfig(
        connection_string="postgresql+asyncpg://user:pass@localhost/db",
    )

    # Configure file cleanup listeners
    config.configure_listeners()

Framework Integration
---------------------

File upload patterns for web frameworks.

Litestar
~~~~~~~~

.. code-block:: python

    from litestar import post
    from litestar.datastructures import UploadFile
    from advanced_alchemy.types import FileObject

    @post("/documents")
    async def upload_document(
        data: UploadFile,
        documents_service: "DocumentService",
    ) -> "Document":
        """Upload document file."""
        doc = await documents_service.create(
            DocumentModel(
                title=data.filename or "untitled",
                attachment=FileObject(
                    backend="documents",
                    filename=data.filename or "file",
                    content_type=data.content_type,
                    content=await data.read(),
                ),
            )
        )
        return documents_service.to_schema(doc, schema_type=DocumentSchema)

FastAPI
~~~~~~~

.. code-block:: python

    from fastapi import UploadFile
    from advanced_alchemy.types import FileObject

    @app.post("/documents")
    async def upload_document(
        file: UploadFile,
        service: "DocumentService" = Depends(get_document_service),
    ) -> "Document":
        """Upload document file."""
        content = await file.read()

        doc = await service.create(
            DocumentModel(
                title=file.filename or "untitled",
                attachment=FileObject(
                    backend="documents",
                    filename=file.filename or "file",
                    content_type=file.content_type,
                    content=content,
                ),
            )
        )
        return doc

Flask
~~~~~

.. code-block:: python

    from flask import request
    from advanced_alchemy.types import FileObject

    @app.route("/documents", methods=["POST"])
    def upload_document():
        """Upload document file."""
        file = request.files["file"]

        doc = document_service.create(
            DocumentModel(
                title=file.filename or "untitled",
                attachment=FileObject(
                    backend="documents",
                    filename=file.filename or "file",
                    content_type=file.content_type,
                    content=file.read(),
                ),
            )
        )
        return doc.to_dict()

Common Patterns
---------------

Unique Filenames
~~~~~~~~~~~~~~~~

Prevent filename collisions with UUID-based names:

.. code-block:: python

    from uuid import uuid4
    from pathlib import Path

    def generate_storage_path(original_filename: str) -> str:
        """Generate unique storage path preserving extension."""
        ext = Path(original_filename).suffix
        return f"{uuid4()}{ext}"

    file_obj = FileObject(
        backend="documents",
        filename=data.filename or "file",  # Display name
        to_filename=generate_storage_path(data.filename or "file"),  # Storage name
        content=await data.read(),
    )

File Validation
~~~~~~~~~~~~~~~

Validate file size and type before storage:

.. code-block:: python

    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
    ALLOWED_TYPES = {"application/pdf", "image/jpeg", "image/png"}

    async def upload_validated(
        data: UploadFile,
        service: "DocumentService",
    ) -> "Document":
        """Upload file with validation."""
        # Validate content type
        if data.content_type not in ALLOWED_TYPES:
            raise ValueError(f"file type {data.content_type} not allowed")

        # Read and validate size
        content = await data.read()
        if len(content) > MAX_FILE_SIZE:
            raise ValueError("file size exceeds 10 MB limit")

        # Create document
        doc = await service.create(
            DocumentModel(
                title=data.filename or "untitled",
                attachment=FileObject(
                    backend="documents",
                    filename=data.filename or "file",
                    content_type=data.content_type,
                    content=content,
                ),
            )
        )
        return doc

Multiple File Upload
~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    @post("/galleries")
    async def upload_gallery(
        files: "list[UploadFile]",
        service: "GalleryService",
    ) -> "Gallery":
        """Upload multiple images."""
        images = []
        for file in files:
            images.append(FileObject(
                backend="images",
                filename=file.filename or "image",
                content_type=file.content_type,
                content=await file.read(),
            ))

        gallery = await service.create(
            GalleryModel(
                title="New Gallery",
                images=images,
            )
        )
        return service.to_schema(gallery, schema_type=GallerySchema)

Direct Upload URLs
~~~~~~~~~~~~~~~~~~

Generate signed URLs for client-side direct upload:

.. code-block:: python

    @post("/documents/upload-url")
    async def create_upload_url(filename: str) -> "dict[str, str]":
        """Generate signed upload URL."""
        file_obj = FileObject(
            backend="documents",
            filename=filename,
        )

        upload_url = await file_obj.sign_async(expires_in=300, for_upload=True)

        return {
            "upload_url": upload_url,
            "filename": filename,
        }

Testing
-------

In-Memory Storage
~~~~~~~~~~~~~~~~~

Use memory backend for tests:

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

    async def test_file_upload(memory_storage, document_service):
        """Test file upload with in-memory storage."""
        doc = await document_service.create(
            DocumentModel(
                title="Test",
                attachment=FileObject(
                    backend="test-storage",
                    filename="test.txt",
                    content=b"Hello, World!",
                ),
            )
        )

        assert doc.attachment is not None
        content = await doc.attachment.get_content_async()
        assert content == b"Hello, World!"

Performance Considerations
--------------------------

Database Field Size
~~~~~~~~~~~~~~~~~~~

FileObject metadata is stored as JSON in the database. Limit metadata size:

.. code-block:: python

    # Minimal metadata
    file_obj = FileObject(
        backend="documents",
        filename="report.pdf",
        content=pdf_bytes,
    )

    # Avoid large metadata
    file_obj = FileObject(
        backend="documents",
        filename="report.pdf",
        metadata={
            "preview": base64_encoded_thumbnail,  # Don't store large data
        },
        content=pdf_bytes,
    )

Batch Operations
~~~~~~~~~~~~~~~~

Use batch operations for multiple files:

.. code-block:: python

    # Save multiple files in parallel
    import asyncio

    files = [
        FileObject(backend="documents", filename=f"file{i}.txt", content=b"data")
        for i in range(100)
    ]

    await asyncio.gather(*[f.save_async() for f in files])

See Also
--------

- :doc:`../storage/index` - Storage backend configuration
- :doc:`../storage/fsspec` - FSSpec backend details
- :doc:`../storage/obstore` - Obstore backend details
- :doc:`basic-types` - Other custom types
- :doc:`/reference/types` - Complete API reference
