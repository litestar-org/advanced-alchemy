========
Services
========

A **Repository** speaks in database tables (``BlogPost`` rows), while a **Service** speaks in your API's input and output shapes (``BlogPostCreate``, ``BlogPostResponse``) and gives you one clean home for business rules—such as creating missing tags or generating URL slugs before saving.

Setting Up a Service
--------------------

Let's connect a ``BlogPost`` table, Pydantic request/response schemas, and a ``BlogPostService``:

.. tab-set::

    .. tab-item:: 1. Database Models

        .. code-block:: python

            from typing import Optional
            from sqlalchemy.orm import Mapped, mapped_column
            from advanced_alchemy.base import BigIntAuditBase
            from advanced_alchemy.mixins import SlugKey

            class BlogPost(BigIntAuditBase):
                __tablename__ = "blog_service_post"
                title: Mapped[str] = mapped_column(index=True)
                content: Mapped[str]
                published: Mapped[bool] = mapped_column(default=False)

            class BlogTag(BigIntAuditBase, SlugKey):
                __tablename__ = "blog_service_tag"
                name: Mapped[str] = mapped_column(unique=True, index=True)

    .. tab-item:: 2. API Schemas

        .. code-block:: python

            from pydantic import BaseModel

            class BlogPostCreate(BaseModel):
                title: str
                content: str

            class BlogPostUpdate(BaseModel):
                title: Optional[str] = None
                content: Optional[str] = None
                published: Optional[bool] = None

            class BlogPostResponse(BaseModel):
                id: int
                title: str
                content: str
                published: bool
                model_config = {"from_attributes": True}

    .. tab-item:: 3. Service Class

        .. code-block:: python

            from advanced_alchemy.repository import SQLAlchemyAsyncRepository
            from advanced_alchemy.service import SQLAlchemyAsyncRepositoryService

            class BlogPostService(SQLAlchemyAsyncRepositoryService[BlogPost]):
                class Repo(SQLAlchemyAsyncRepository[BlogPost]):
                    model_type = BlogPost

                repository_type = Repo

Creating, Updating, and Returning Schemas
-----------------------------------------

Pass dictionaries, Pydantic models, ``msgspec`` structs, dataclasses, ``attrs`` classes, or ``SQLModel`` objects straight into ``create`` and ``update``, then call ``to_schema`` to format the response:

.. code-block:: python

    async def create_post(service: BlogPostService, payload: BlogPostCreate) -> BlogPostResponse:
        post = await service.create(data=payload, auto_commit=True)
        return service.to_schema(post, schema_type=BlogPostResponse)

    async def update_post(service: BlogPostService, post_id: int, payload: BlogPostUpdate) -> BlogPostResponse:
        post = await service.update(data=payload, item_id=post_id, auto_commit=True)
        return service.to_schema(post, schema_type=BlogPostResponse)

Adding Custom Business Rules
----------------------------

Need to auto-generate a unique URL slug whenever a tag is created or renamed? Override ``to_model`` (or ``to_model_on_create`` / ``to_model_on_update``):

.. code-block:: python

    from advanced_alchemy.repository import SQLAlchemyAsyncSlugRepository
    from advanced_alchemy.service import ModelDictT, is_dict_with_field, is_dict_without_field, schema_dump

    class BlogTagService(SQLAlchemyAsyncRepositoryService[BlogTag]):
        class Repo(SQLAlchemyAsyncSlugRepository[BlogTag]):
            model_type = BlogTag

        repository_type = Repo

        async def to_model(self, data: ModelDictT[BlogTag], operation: Optional[str] = None) -> BlogTag:
            dumped = schema_dump(data)
            if is_dict_without_field(dumped, "slug") and is_dict_with_field(dumped, "name"):
                dumped["slug"] = await self.repository.get_available_slug(dumped["name"])
            return await super().to_model(dumped, operation)

.. _using-msgspec-or-attrs-schemas:

Using Pydantic, Msgspec, Dataclasses, attrs, or SQLModel
--------------------------------------------------------

Services work with all five major Python schema libraries—normalizing partial updates (ignoring unset fields automatically) and converting rows into response schemas:

.. tab-set::

    .. tab-item:: Pydantic

        .. code-block:: python

            class BlogPostPatch(BaseModel):
                title: Optional[str] = None
                published: Optional[bool] = None

            def as_pydantic(service: BlogPostService, post: BlogPost) -> BlogPostResponse:
                return service.to_schema(post, schema_type=BlogPostResponse)

    .. tab-item:: Msgspec

        .. code-block:: python

            import msgspec

            class BlogPostStruct(msgspec.Struct):
                id: int
                title: str
                published: bool

            class BlogPostStructPatch(msgspec.Struct):
                title: str | msgspec.UnsetType = msgspec.UNSET
                published: bool | msgspec.UnsetType = msgspec.UNSET

            def as_msgspec(service: BlogPostService, post: BlogPost) -> BlogPostStruct:
                return service.to_schema(post, schema_type=BlogPostStruct)

    .. tab-item:: Dataclasses

        .. code-block:: python

            from dataclasses import dataclass
            from advanced_alchemy.utils.dataclass import Empty, EmptyType

            @dataclass
            class BlogPostDataPatch:
                title: str | EmptyType = Empty
                published: bool | EmptyType = Empty

            def dump_dataclass_patch(patch: BlogPostDataPatch) -> dict[str, object]:
                return schema_dump(patch)

    .. tab-item:: attrs

        .. code-block:: python

            from attrs import NOTHING, define

            @define
            class BlogPostAttrs:
                id: int
                title: str
                published: bool

            def as_attrs(service: BlogPostService, post: BlogPost) -> BlogPostAttrs:
                return service.to_schema(post, schema_type=BlogPostAttrs)

    .. tab-item:: SQLModel

        .. code-block:: python

            from sqlmodel import Field as SQLField, SQLModel

            class ArticleRow(SQLModel, table=True):
                __tablename__ = "service_doc_article_row"
                id: Optional[int] = SQLField(default=None, primary_key=True)
                title: str

            class ArticlePublic(SQLModel):
                id: int
                title: str

            class ArticleService(SQLAlchemyAsyncRepositoryService[ArticleRow]):
                class Repo(SQLAlchemyAsyncRepository[ArticleRow]):
                    model_type = ArticleRow
                repository_type = Repo

Related Guides
--------------

* :doc:`/usage/frameworks/litestar` — Inject services directly into Litestar controllers.
* :doc:`/usage/frameworks/fastapi` — Inject services into FastAPI routes with ``Depends``.
* :doc:`/reference/service` — Full service API reference.
