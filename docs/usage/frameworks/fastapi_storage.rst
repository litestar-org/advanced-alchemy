====================================
FastAPI File Storage and Multi-Binds
====================================

This guide shows how to attach uploaded files to SQLAlchemy models in FastAPI and how to connect a single FastAPI app to more than one database.

Storing Uploaded Files
----------------------

Register a local folder or cloud bucket (S3, GCS, Azure) in ``storages`` and add a ``StoredObject`` column to your model. In FastAPI routes that receive an ``UploadFile``, pass ``FileObject(backend=..., filename=file.filename, content=await file.read())`` to ``service.create(...)``—Advanced Alchemy saves the file when the transaction commits and deletes it if the row is deleted:

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

Connecting Multiple Databases
-----------------------------

Pass a list of configs with distinct ``bind_key`` names when your FastAPI app talks to more than one database (for example, an async main database and a sync reporting database):

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

Related Guides
--------------

* :doc:`/usage/frameworks/fastapi` — Core FastAPI setup, ``Depends`` services, and query filters.
* :doc:`/reference/extensions/fastapi/index` — FastAPI extension API reference.
