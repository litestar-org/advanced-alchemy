# /// script
# dependencies = [
#   "advanced_alchemy[obstore,uuid]",
#   "aiosqlite",
#   "fastapi[standard]",
#   "orjson"
#   "obstore"
# ]
# ///
from typing import Annotated, Any, Optional, Union
from uuid import UUID

import uvicorn
from fastapi import APIRouter, Depends, FastAPI, File, Form, UploadFile
from pydantic import BaseModel, Field, computed_field
from sqlalchemy.orm import Mapped, mapped_column

from advanced_alchemy.extensions.fastapi import (
    AdvancedAlchemy,
    AsyncSessionConfig,
    SQLAlchemyAsyncConfig,
    base,
    filters,
    repository,
    service,
)
from advanced_alchemy.types import FileObject, storages
from advanced_alchemy.types.file_object.backends.obstore import ObstoreBackend
from advanced_alchemy.types.file_object.data_type import StoredObject

sqlalchemy_config = SQLAlchemyAsyncConfig(
    connection_string="sqlite+aiosqlite:///test.sqlite",
    session_config=AsyncSessionConfig(expire_on_commit=False),
    commit_mode="autocommit",
    create_all=True,
)
app = FastAPI()
alchemy = AdvancedAlchemy(config=sqlalchemy_config, app=app)
document_router = APIRouter()
s3_backend = ObstoreBackend(
    key="local",
    fs="s3://static-files/",
    aws_endpoint="http://localhost:9000",
    aws_access_key_id="minioadmin",
    aws_secret_access_key="minioadmin",  # noqa: S106
)
storages.register_backend(s3_backend)


class DocumentModel(base.UUIDBase):
    # we can optionally provide the table name instead of auto-generating it
    __tablename__ = "document"
    name: Mapped[str]
    file: Mapped[FileObject] = mapped_column(StoredObject(backend="local"))


class DocumentService(service.SQLAlchemyAsyncRepositoryService[DocumentModel]):
    """Document repository."""

    class Repo(repository.SQLAlchemyAsyncRepository[DocumentModel]):
        """Document repository."""

        model_type = DocumentModel

    repository_type = Repo


# Pydantic Models


class Document(BaseModel):
    id: Optional[UUID]
    name: str
    file: Optional[FileObject] = Field(default=None, exclude=True)

    @computed_field
    def file_url(self) -> Optional[Union[str, list[str]]]:
        if self.file is None:
            return None
        return self.file.sign()


@document_router.get(path="/documents", response_model=service.OffsetPagination[Document])
async def list_documents(
    documents_service: Annotated[
        DocumentService, Depends(alchemy.provide_service(DocumentService, load=[DocumentModel.file]))
    ],
    filters: Annotated[
        list[filters.FilterTypes],
        Depends(
            alchemy.provide_filters(
                {
                    "id_filter": UUID,
                    "pagination_type": "limit_offset",
                    "search": "name",
                    "search_ignore_case": True,
                }
            )
        ),
    ],
) -> service.OffsetPagination[Document]:
    results, total = await documents_service.list_and_count(*filters)
    return documents_service.to_schema(results, total, filters=filters, schema_type=Document)


@document_router.post(path="/documents")
async def create_document(
    documents_service: Annotated[DocumentService, Depends(alchemy.provide_service(DocumentService))],
    name: Annotated[str, Form()],
    file: Annotated[Optional[UploadFile], File()] = None,
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


@document_router.get(path="/documents/{document_id}")
async def get_document(
    documents_service: Annotated[DocumentService, Depends(alchemy.provide_service(DocumentService))],
    document_id: UUID,
) -> Document:
    obj = await documents_service.get(document_id)
    return documents_service.to_schema(obj, schema_type=Document)


@document_router.patch(path="/documents/{document_id}")
async def update_document(
    documents_service: Annotated[DocumentService, Depends(alchemy.provide_service(DocumentService))],
    document_id: UUID,
    name: Annotated[Optional[str], Form()] = None,
    file: Annotated[Optional[UploadFile], File()] = None,
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


@document_router.delete(path="/documents/{document_id}")
async def delete_document(
    documents_service: Annotated[DocumentService, Depends(alchemy.provide_service(DocumentService))],
    document_id: UUID,
) -> None:
    _ = await documents_service.delete(document_id)


app.include_router(document_router)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)  # noqa: S104
