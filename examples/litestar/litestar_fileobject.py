from typing import Annotated, Any, Optional, Union
from uuid import UUID

import uvicorn
from litestar import Controller, Litestar, delete, get, patch, post
from litestar.datastructures import UploadFile
from litestar.params import Dependency
from pydantic import BaseModel, Field, computed_field
from sqlalchemy.orm import Mapped, mapped_column

from advanced_alchemy.extensions.litestar import (
    AsyncSessionConfig,
    SQLAlchemyAsyncConfig,
    SQLAlchemyPlugin,
    base,
    filters,
    providers,
    repository,
    service,
)
from advanced_alchemy.types import FileObject, storages
from advanced_alchemy.types.file_object.backends.obstore import ObstoreBackend
from advanced_alchemy.types.file_object.data_type import StoredObject

# Object storage backend
s3_backend = ObstoreBackend(
    key="local",
    fs="s3://static-files/",
    aws_endpoint="http://localhost:9000",
    aws_access_key_id="minioadmin",
    aws_secret_access_key="minioadmin",  # noqa: S106
)
storages.register_backend(s3_backend)


# SQLAlchemy Model
class DocumentModel(base.UUIDBase):
    __tablename__ = "document"

    name: Mapped[str]
    file: Mapped[FileObject] = mapped_column(StoredObject(backend="local"))


# Pydantic Schema
class Document(BaseModel):
    id: Optional[UUID]
    name: str
    file: Optional[FileObject] = Field(default=None, exclude=True)

    @computed_field
    def file_url(self) -> Optional[Union[str, list[str]]]:
        if self.file is None:
            return None
        return self.file.sign()


# Advanced Alchemy Service
class DocumentService(service.SQLAlchemyAsyncRepositoryService[DocumentModel]):
    """Document repository."""

    class Repo(repository.SQLAlchemyAsyncRepository[DocumentModel]):
        """Document repository."""

        model_type = DocumentModel

    repository_type = Repo


# Litestar Controller
class DocumentController(Controller):
    path = "/documents"
    dependencies = providers.create_service_dependencies(
        DocumentService,
        "documents_service",
        load=[DocumentModel.file],
        filters={"pagination_type": "limit_offset", "id_filter": UUID, "search": "name", "search_ignore_case": True},
    )

    @get(path="/", response_model=service.OffsetPagination[Document])
    async def list_documents(
        self,
        documents_service: DocumentService,
        filters: Annotated[list[filters.FilterTypes], Dependency(skip_validation=True)],
    ) -> service.OffsetPagination[Document]:
        results, total = await documents_service.list_and_count(*filters)
        return documents_service.to_schema(results, total, filters=filters, schema_type=Document)

    @post(path="/")
    async def create_document(
        self,
        documents_service: DocumentService,
        name: str,
        file: Annotated[Optional[UploadFile], None] = None,
    ) -> Document:
        obj = await documents_service.create(
            DocumentModel(
                name=name,
                file=FileObject(
                    backend="local",
                    filename=file.filename or "uploaded_file",
                    content_type=file.content_type,
                    content=await file.read(),
                )
                if file
                else None,
            )
        )
        return documents_service.to_schema(obj, schema_type=Document)

    @get(path="/{document_id:uuid}")
    async def get_document(
        self,
        documents_service: DocumentService,
        document_id: UUID,
    ) -> Document:
        obj = await documents_service.get(document_id)
        return documents_service.to_schema(obj, schema_type=Document)

    @patch(path="/{document_id:uuid}")
    async def update_document(
        self,
        documents_service: DocumentService,
        document_id: UUID,
        name: Optional[str] = None,
        file: Annotated[Optional[UploadFile], None] = None,
    ) -> Document:
        update_data: dict[str, Any] = {}
        if name is not None:
            update_data["name"] = name
        if file is not None:
            update_data["file"] = FileObject(
                backend="local",
                filename=file.filename or "uploaded_file",
                content_type=file.content_type,
                content=await file.read(),
            )

        obj = await documents_service.update(update_data, item_id=document_id)
        return documents_service.to_schema(obj, schema_type=Document)

    @delete(path="/{document_id:uuid}")
    async def delete_document(
        self,
        documents_service: DocumentService,
        document_id: UUID,
    ) -> None:
        _ = await documents_service.delete(document_id)


sqlalchemy_config = SQLAlchemyAsyncConfig(
    connection_string="sqlite+aiosqlite:///test.sqlite",
    session_config=AsyncSessionConfig(expire_on_commit=False),
    before_send_handler="autocommit",
    create_all=True,
)
app = Litestar(route_handlers=[DocumentController], plugins=[SQLAlchemyPlugin(config=sqlalchemy_config)])

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)  # noqa: S104
