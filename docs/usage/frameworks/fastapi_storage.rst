====================================
FastAPI File Storage and Multi-Binds
====================================

Advanced Alchemy's :class:`~advanced_alchemy.types.StoredObject` and :class:`~advanced_alchemy.types.FileObject` types integrate with FastAPI multipart form uploads and Pydantic computed fields.

Registering Backends and Mapping Columns
----------------------------------------

Register a storage backend in :data:`~advanced_alchemy.types.storages` and map a :class:`~advanced_alchemy.types.StoredObject` column on your model:

.. code-block:: python

    from pathlib import Path
    import tempfile
    from typing import Optional
    from uuid import UUID

    from pydantic import BaseModel, Field
    from sqlalchemy.orm import Mapped, mapped_column

    from advanced_alchemy.extensions.fastapi import base, repository, service
    from advanced_alchemy.types import FileObject, StoredObject, storages

    storage_tmp = tempfile.mkdtemp()
    storages.register_backend(f"file://{Path(storage_tmp)}", key="fastapi_documents")


    class DocumentModel(base.UUIDBase):
        __tablename__ = "fastapi_document"

        name: Mapped[str]
        file: Mapped[Optional[FileObject]] = mapped_column(
            StoredObject(backend="fastapi_documents"),
            nullable=True,
        )


    class DocumentRepository(repository.SQLAlchemyAsyncRepository[DocumentModel]):
        model_type = DocumentModel


    class DocumentService(service.SQLAlchemyAsyncRepositoryService[DocumentModel, DocumentRepository]):
        repository_type = DocumentRepository


    class DocumentResponse(BaseModel):
        model_config = {"from_attributes": True}

        id: Optional[UUID] = None
        name: str
        file: Optional[FileObject] = Field(default=None, exclude=True)

    storages.clear_backends()

Multipart Uploads in FastAPI Routes
-----------------------------------

In route handlers that accept ``UploadFile`` and ``Form`` fields, construct a :class:`~advanced_alchemy.types.FileObject` with ``content=await file.read()`` and pass it to ``service.create(...)`` or ``service.update(...)``. The session tracker persists the file payload to the configured storage backend when the database transaction commits.

Multi-Database Bind Keys
------------------------

Pass a sequence of :class:`~advanced_alchemy.extensions.fastapi.SQLAlchemyAsyncConfig` or :class:`~advanced_alchemy.extensions.fastapi.SQLAlchemySyncConfig` instances to :class:`~advanced_alchemy.extensions.fastapi.AdvancedAlchemy` to manage multiple database binds within a single FastAPI application:

.. code-block:: python

    from fastapi import FastAPI
    from advanced_alchemy.extensions.fastapi import (
        AdvancedAlchemy,
        SQLAlchemyAsyncConfig,
        SQLAlchemySyncConfig,
    )

    app = FastAPI()
    alchemy = AdvancedAlchemy(
        config=[
            SQLAlchemyAsyncConfig(connection_string="sqlite+aiosqlite:///:memory:"),
            SQLAlchemySyncConfig(
                connection_string="sqlite+pysqlite:///:memory:",
                bind_key="reporting",
            ),
        ],
        app=app,
    )
    assert alchemy.get_async_config().bind_key == "default"
    assert alchemy.get_sync_config("reporting").bind_key == "reporting"

Related Documentation
---------------------

- :doc:`/usage/frameworks/fastapi` — Core FastAPI setup, dependency injection, and route handlers.
- :doc:`/reference/extensions/fastapi/index` — FastAPI extension API reference.
- :doc:`/reference/types` — :class:`~advanced_alchemy.types.StoredObject` and :class:`~advanced_alchemy.types.FileObject` API reference.
