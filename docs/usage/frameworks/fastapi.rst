===================
FastAPI Integration
===================

Advanced Alchemy's repository and service patterns work well within FastAPI applications.

Basic Setup
-----------

Configure SQLAlchemy with FastAPI:

.. code-block:: python

    from typing import AsyncGenerator

    from fastapi import FastAPI

    from advanced_alchemy.extensions.fastapi import AdvancedAlchemy, AsyncSessionConfig, SQLAlchemyAsyncConfig

    alchemy_config = SQLAlchemyAsyncConfig(
        connection_string="sqlite+aiosqlite:///test.sqlite",
        session_config=AsyncSessionConfig(expire_on_commit=False),
        create_all=True,
        commit_mode="autocommit",
    )

    app = FastAPI()
    alchemy = AdvancedAlchemy(config=alchemy_config, app=app)

Models and Schemas
------------------

Define your SQLAlchemy models and Pydantic schemas:

.. code-block:: python

    import datetime
    from datetime import date
    from typing import Optional, Union
    from uuid import UUID

    from pydantic import BaseModel as _BaseModel
    from sqlalchemy import ForeignKey
    from sqlalchemy.orm import Mapped, mapped_column, relationship

    from advanced_alchemy.base import UUIDAuditBase, UUIDBase

    class BaseModel(_BaseModel):
        """Extend Pydantic's BaseModel to enable ORM mode"""
        model_config = {"from_attributes": True}

    class AuthorModel(UUIDBase):
        __tablename__ = "author"
        name: Mapped[str]
        dob: Mapped[Optional[date]]
        books: Mapped[list["BookModel"]] = relationship(back_populates="author", lazy="selectin")

    class BookModel(UUIDAuditBase):
        __tablename__ = "book"
        title: Mapped[str]
        author_id: Mapped[UUID] = mapped_column(ForeignKey("author.id"))
        author: Mapped["AuthorModel"] = relationship(lazy="joined", innerjoin=True, viewonly=True)

    class Author(BaseModel):
        id: Optional[UUID]
        name: str
        dob: Optional[datetime.date] = None

    class AuthorCreate(BaseModel):
        name: str
        dob: Optional[datetime.date] = None

    class AuthorUpdate(BaseModel):
        name: Optional[str] = None
        dob: Optional[datetime.date] = None

Repository and Service
----------------------

Create repository and service classes:

.. code-block:: python

    from typing import Annotated, AsyncGenerator

    from fastapi import Depends, Query
    from sqlalchemy.ext.asyncio import AsyncSession

    from advanced_alchemy.extensions.fastapi import filters, repository, service


    class AuthorService(service.SQLAlchemyAsyncRepositoryService[AuthorModel]):
        """Author service."""

        class Repo(repository.SQLAlchemyAsyncRepository[AuthorModel]):
            """Author repository."""
            model_type = AuthorModel

        repository_type = Repo


Dependency Injection
--------------------

Set up dependency injected into the request context.

.. code-block:: python

    DatabaseSession = Annotated[AsyncSession, Depends(alchemy.provide_session())]
    Authors = Annotated[AuthorService, Depends(provide_authors_service)]

    async def provide_authors_service(db_session: DatabaseSession) -> AsyncGenerator[AuthorService, None]:
        """This provides the default Authors repository."""
        async with AuthorService.new(session=db_session) as service:
            yield service

    def provide_limit_offset_pagination(
        current_page: int = Query(default=1, ge=1, alias="currentPage"),
        page_size: int = Query(default=20, ge=1, alias="pageSize"),
    ) -> filters.LimitOffset:
        return filters.LimitOffset(limit=page_size, offset=page_size * (current_page - 1))

The session providers accept an optional bind key when you configure multiple database connections:

.. code-block:: python

    DatabaseSession = Annotated[AsyncSession, Depends(alchemy.provide_session())]
    ReportingSession = Annotated[AsyncSession, Depends(alchemy.provide_session("reporting"))]

The same optional key is available on ``provide_async_session()``, ``provide_sync_session()``, and ``provide_service(...)``
for multi-database setups.


Controllers
-----------

Create controllers using the service:

.. code-block:: python

    from fastapi import APIRouter, Depends
    from uuid import UUID

    from advanced_alchemy.extensions.fastapi import filters

    author_router = APIRouter()

    @author_router.get(path="/authors", response_model=filters.OffsetPagination[Author])
    async def list_authors(
        authors_service: Authors,
        limit_offset: Annotated[filters.LimitOffset, Depends(provide_limit_offset_pagination)],
    ) -> filters.OffsetPagination[Author]:
        """List authors."""
        results, total = await authors_service.get_many_and_count(limit_offset)
        return authors_service.to_schema(results, total, filters=[limit_offset], schema_type=Author)

    @author_router.post(path="/authors", response_model=Author)
    async def create_author(
        authors_service: Authors,
        data: AuthorCreate,
    ) -> Author:
        """Create a new author."""
        obj = await authors_service.create(data)
        return authors_service.to_schema(obj, schema_type=Author)

    @author_router.get(path="/authors/{author_id}", response_model=Author)
    async def get_author(
        authors_service: Authors,
        author_id: UUID,
    ) -> Author:
        """Get an existing author."""
        obj = await authors_service.get(author_id)
        return authors_service.to_schema(obj, schema_type=Author)

    @author_router.patch(path="/authors/{author_id}", response_model=Author)
    async def update_author(
        authors_service: Authors,
        data: AuthorUpdate,
        author_id: UUID,
    ) -> Author:
        """Update an author."""
        obj = await authors_service.update(data, item_id=author_id)
        return authors_service.to_schema(obj, schema_type=Author)

    @author_router.delete(path="/authors/{author_id}")
    async def delete_author(
        authors_service: Authors,
        author_id: UUID,
    ) -> None:
        """Delete an author from the system."""
        _ = await authors_service.delete(author_id)

Application Configuration
-------------------------

Finally, configure your FastAPI application with the router:

.. code-block:: python

    app.include_router(author_router)

File Object Storage
-------------------

FastAPI works well with ``FileObject``-backed models when you keep the upload flow explicit:

1. Register a storage backend
2. Map a ``StoredObject`` column on the model
3. Expose a signed URL from the response schema
4. Translate multipart uploads into ``FileObject`` values before they reach the repository service

Start by registering a backend and mapping the file column:

.. code-block:: python

    from typing import Optional
    from uuid import UUID

    from pydantic import BaseModel, Field, computed_field
    from sqlalchemy.orm import Mapped, mapped_column

    from advanced_alchemy.extensions.fastapi import base, repository, service
    from advanced_alchemy.types import FileObject, storages
    from advanced_alchemy.types.file_object.backends.obstore import ObstoreBackend
    from advanced_alchemy.types.file_object.data_type import StoredObject

    documents_backend = ObstoreBackend(
        key="documents",
        fs="s3://company-documents-prod/",
    )
    storages.register_backend(documents_backend)

    class DocumentModel(base.UUIDBase):
        __tablename__ = "document"

        name: Mapped[str]
        file: Mapped[FileObject] = mapped_column(StoredObject(backend="documents"))

    class DocumentService(service.SQLAlchemyAsyncRepositoryService[DocumentModel]):
        class Repo(repository.SQLAlchemyAsyncRepository[DocumentModel]):
            model_type = DocumentModel

        repository_type = Repo

Use a response schema that hides the raw ``FileObject`` but exposes a signed URL:

.. code-block:: python

    class Document(BaseModel):
        id: Optional[UUID] = None
        name: str
        file: Optional[FileObject] = Field(default=None, exclude=True)

        @computed_field
        def file_url(self) -> Optional[Union[str, list[str]]]:
            if self.file is None:
                return None
            return self.file.sign()

Then accept multipart form data and construct ``FileObject`` values explicitly:

.. code-block:: python

    from typing import Annotated

    from fastapi import APIRouter, Depends, File, Form, UploadFile

    document_router = APIRouter()

    Documents = Annotated[DocumentService, Depends(alchemy.provide_service(DocumentService))]

    @document_router.post(path="/documents", response_model=Document)
    async def create_document(
        documents_service: Documents,
        name: Annotated[str, Form()],
        file: Annotated[Optional[UploadFile], File()] = None,
    ) -> Document:
        obj = await documents_service.create(
            DocumentModel(
                name=name,
                file=FileObject(
                    backend="documents",
                    filename=file.filename or "uploaded_file",
                    content_type=file.content_type,
                    content=await file.read(),
                )
                if file is not None
                else None,
            )
        )
        return documents_service.to_schema(obj, schema_type=Document)

    @document_router.patch(path="/documents/{document_id}", response_model=Document)
    async def update_document(
        documents_service: Documents,
        document_id: UUID,
        name: Annotated[Optional[str], Form()] = None,
        file: Annotated[Optional[UploadFile], File()] = None,
    ) -> Document:
        update_data: dict[str, object] = {}
        if name is not None:
            update_data["name"] = name
        if file is not None:
            update_data["file"] = FileObject(
                backend="documents",
                filename=file.filename or "uploaded_file",
                content_type=file.content_type,
                content=await file.read(),
            )

        obj = await documents_service.update(update_data, item_id=document_id)
        return documents_service.to_schema(obj, schema_type=Document)

In production, keep object storage credentials out of application code. Point ``ObstoreBackend`` at
the real bucket or prefix you use in production and let the runtime provide credentials through the
platform's normal mechanism, such as an IAM role, IRSA, ECS task role, or other ambient credentials.

The storage backend key must match in both places: the ``StoredObject(backend="...")`` column
definition and the ``FileObject(backend="...")`` values you create from incoming uploads.
