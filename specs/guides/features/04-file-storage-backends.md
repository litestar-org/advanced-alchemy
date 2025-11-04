# Guide: File Storage Backends

`advanced-alchemy` includes a powerful system for handling file uploads and associating them with your SQLAlchemy models. It abstracts the actual file storage into backends, allowing you to store files in various locations (like local disk, S3, GCS, etc.) while only storing metadata in your database.

The core components of this system are:
-   **`StoredObject`**: A custom SQLAlchemy type that you map in your model. It stores file metadata as JSON in the database.
-   **`FileObject`**: A Pydantic-like model that represents a file. You interact with this object in your application code.
-   **`StorageBackend`**: The interface for different storage providers (e.g., S3, local filesystem).
-   **`storages` Registry**: A global registry to configure and access your storage backends.

## 1. Configure Storage Backends

First, you need to configure and register one or more storage backends. `advanced-alchemy` uses the `obstore` library, which provides a unified API for many object storage services.

### Example 1: Local Filesystem Backend

This is the simplest backend, useful for local development or applications that store files on the same server.

```python
from advanced_alchemy.types import storages
from advanced_alchemy.types.file_object.backends.obstore import ObstoreBackend

# Create a backend instance that stores files in the './storage/local' directory
local_backend = ObstoreBackend(
    key="local_fs",  # A unique key for this backend
    fs="osfs://./storage/local", # A URL indicating the local filesystem
)

# Register it with the global registry
storages.register_backend(local_backend)
```

### Example 2: S3-Compatible Backend (MinIO)

This example configures a backend to connect to a local MinIO S3-compatible server. This pattern is ideal for cloud-native or distributed applications.

```python
from advanced_alchemy.types import storages
from advanced_alchemy.types.file_object.backends.obstore import ObstoreBackend

# Create a backend instance
s3_backend = ObstoreBackend(
    key="s3_media",  # A unique key for this backend
    fs="s3://static-files/",  # The S3 bucket
    aws_endpoint="http://localhost:9000",
    aws_access_key_id="minioadmin",
    aws_secret_access_key="minioadmin",
)

# Register it with the global registry
storages.register_backend(s3_backend)
```

## 2. Map the `StoredObject` Type in Your Model

Next, use the `StoredObject` type in your SQLAlchemy model to define a file attribute. You must tell it which backend to use by passing the key you registered in the previous step.

```python
from sqlalchemy.orm import Mapped, mapped_column
from advanced_alchemy.base import UUIDBase
from advanced_alchemy.types import FileObject
from advanced_alchemy.types.file_object.data_type import StoredObject

class DocumentModel(UUIDBase):
    __tablename__ = "document"

    name: Mapped[str]
    
    # This column will store file metadata as JSON in the 's3_media' backend
    file: Mapped[FileObject] = mapped_column(StoredObject(backend="s3_media"))
```

## 3. Full Litestar Integration Example

This complete example demonstrates how to integrate the file storage system into a Litestar application, from the model to the controller.

### Model and Schema Definition

The Pydantic schema includes a `computed_field` to automatically generate a temporary, signed URL for accessing the file. This is the recommended way to serve files to a client.

```python
from pydantic import BaseModel, Field, computed_field

# ... DocumentModel from above ...

class DocumentSchema(BaseModel):
    id: UUID
    name: str
    file: FileObject | None = Field(default=None, exclude=True) # Exclude raw data

    @computed_field
    @property
    def file_url(self) -> str | None:
        """Generate a temporary download URL for the file."""
        if self.file is None:
            return None
        # The sign() method generates a temporary, secure URL
        return self.file.sign()

class CreateDocument(BaseModel):
    model_config = {"arbitrary_types_allowed": True}
    name: str
    file: UploadFile | None = None
```

### Service Definition

The service is a standard `advanced-alchemy` service. No special configuration is needed.

```python
from advanced_alchemy.service import SQLAlchemyAsyncRepositoryService
from advanced_alchemy.repository import SQLAlchemyAsyncRepository

class DocumentService(SQLAlchemyAsyncRepositoryService[DocumentModel]):
    repository_type = SQLAlchemyAsyncRepository[DocumentModel]
```

### Controller for Handling Uploads

The Litestar controller handles the HTTP requests. Note the use of `RequestEncodingType.MULTI_PART` for the `create` and `update` endpoints to handle file uploads.

When creating or updating, a `FileObject` is instantiated with the raw content from the `UploadFile`. `advanced-alchemy` automatically intercepts this object, saves its content to the configured backend, and stores the resulting metadata in the database.

```python
from typing import Annotated
from litestar import Controller, post, get, patch, delete
from litestar.datastructures import UploadFile
from litestar.enums import RequestEncodingType
from litestar.params import Body

class DocumentController(Controller):
    path = "/documents"
    # ... dependencies setup ...

    @post("/")
    async def create_document(
        self,
        data: Annotated[CreateDocument, Body(media_type=RequestEncodingType.MULTI_PART)],
        documents_service: DocumentService,
    ) -> DocumentSchema:
        # Instantiate the SQLAlchemy model
        db_obj = DocumentModel(
            name=data.name,
            # Create a FileObject from the upload
            file=FileObject(
                backend="s3_media", # Must match the registered backend key
                filename=data.file.filename,
                content_type=data.file.content_type,
                content=await data.file.read(), # The raw file bytes
            ) if data.file else None,
        )
        
        # The service handles saving the file and the model
        created_obj = await documents_service.create(db_obj)
        return documents_service.to_schema(created_obj, schema_type=DocumentSchema)

    @get("/{document_id:uuid}")
    async def get_document(
        self,
        documents_service: DocumentService,
        document_id: UUID,
    ) -> DocumentSchema:
        obj = await documents_service.get(document_id)
        # The response will include the auto-generated 'file_url'
        return documents_service.to_schema(obj, schema_type=DocumentSchema)
    
    # ... other endpoints (list, update, delete) ...
```

This complete workflow shows how the storage backend system provides a powerful and abstracted way to handle file uploads, database persistence, and secure access, all with minimal boilerplate.