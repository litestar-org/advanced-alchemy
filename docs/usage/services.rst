========
Services
========

Why add a **Service** if you already have a Repository?

* A **Repository** speaks in database tables (``BlogPost`` rows).
* A **Service** speaks in your API's input and output shapes (like ``BlogPostCreate`` and ``BlogPostResponse``) and gives you one clean home for business rules—such as creating missing tags or generating URL slugs before saving.

Setting Up a Service
--------------------

Let's connect a ``BlogPost`` table, Pydantic request/response schemas, and a ``BlogPostService``:

.. tab-set::

    .. tab-item:: 1. Database Models

        .. code-block:: python

            import datetime
            from collections.abc import Hashable
            from typing import Optional
            from sqlalchemy import Column, ForeignKey, Table
            from sqlalchemy.orm import Mapped, mapped_column, relationship
            from sqlalchemy.sql.elements import ColumnElement
            from advanced_alchemy.base import BigIntAuditBase, orm_registry
            from advanced_alchemy.mixins import SlugKey, UniqueMixin
            from advanced_alchemy.utils.text import slugify

            blog_post_tag = Table(
                "blog_service_post_tag",
                orm_registry.metadata,
                Column("post_id", ForeignKey("blog_service_post.id", ondelete="CASCADE"), primary_key=True),
                Column("tag_id", ForeignKey("blog_service_tag.id", ondelete="CASCADE"), primary_key=True),
            )

            class BlogPost(BigIntAuditBase):
                __tablename__ = "blog_service_post"
                title: Mapped[str] = mapped_column(index=True)
                content: Mapped[str]
                published: Mapped[bool] = mapped_column(default=False)
                tags: Mapped[list["BlogTag"]] = relationship(
                    secondary=blog_post_tag, back_populates="posts", lazy="selectin"
                )

            class BlogTag(BigIntAuditBase, SlugKey, UniqueMixin):
                __tablename__ = "blog_service_tag"
                name: Mapped[str] = mapped_column(unique=True, index=True)
                posts: Mapped[list["BlogPost"]] = relationship(
                    secondary=blog_post_tag, back_populates="tags", viewonly=True
                )

                @classmethod
                def unique_hash(cls, name: str, slug: Optional[str] = None) -> Hashable:
                    return slugify(name)

                @classmethod
                def unique_filter(cls, name: str, slug: Optional[str] = None) -> ColumnElement[bool]:
                    return cls.slug == slugify(name)

    .. tab-item:: 2. API Schemas

        .. code-block:: python

            from pydantic import BaseModel, Field

            class BlogPostCreate(BaseModel):
                title: str
                content: str
                tags: list[str] = Field(default_factory=list)

            class BlogPostUpdate(BaseModel):
                title: Optional[str] = None
                content: Optional[str] = None
                published: Optional[bool] = None

            class BlogPostResponse(BaseModel):
                id: int
                title: str
                content: str
                published: bool
                created_at: datetime.datetime
                updated_at: datetime.datetime
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

Pass dictionaries, Pydantic models, or ``msgspec`` structs straight into ``create`` and ``update``, then call ``to_schema`` (or ``to_list_schema`` for paginated results) to format the response:

.. code-block:: python

    async def create_post(service: BlogPostService, payload: BlogPostCreate) -> BlogPostResponse:
        post = await service.create(data=payload, auto_commit=True)
        return service.to_schema(post, schema_type=BlogPostResponse)

    async def update_post(service: BlogPostService, post_id: int, payload: BlogPostUpdate) -> BlogPostResponse:
        post = await service.update(data=payload, item_id=post_id, auto_commit=True)
        return service.to_schema(post, schema_type=BlogPostResponse)

Adding Custom Business Rules
----------------------------

Need to turn a list of tag strings (``["Python", "SQL"]``) into ``BlogTag`` rows whenever a post is created, or auto-generate a unique URL slug? Override ``to_model_on_create`` or ``to_model``:

.. code-block:: python

    from advanced_alchemy.repository import SQLAlchemyAsyncSlugRepository
    from advanced_alchemy.service import ModelDictT, is_dict_with_field, is_dict_without_field, schema_dump

    class TaggedBlogPostService(SQLAlchemyAsyncRepositoryService[BlogPost]):
        class Repo(SQLAlchemyAsyncRepository[BlogPost]):
            model_type = BlogPost

        repository_type = Repo
        loader_options = [BlogPost.tags]

        async def to_model_on_create(self, data: ModelDictT[BlogPost]) -> ModelDictT[BlogPost]:
            dumped = schema_dump(data)
            tag_names = dumped.pop("tags", [])
            post = await super().to_model(dumped)
            for name in tag_names:
                tag = await BlogTag.as_unique_async(self.repository.session, name=name, slug=slugify(name))
                post.tags.append(tag)
            return post

    class BlogTagService(SQLAlchemyAsyncRepositoryService[BlogTag]):
        class Repo(SQLAlchemyAsyncSlugRepository[BlogTag]):
            model_type = BlogTag

        repository_type = Repo

        async def to_model(self, data: ModelDictT[BlogTag], operation: Optional[str] = None) -> BlogTag:
            dumped = schema_dump(data)
            if is_dict_without_field(dumped, "slug") and is_dict_with_field(dumped, "name"):
                dumped["slug"] = await self.repository.get_available_slug(dumped["name"])
            return await super().to_model(dumped, operation)

Using Msgspec or attrs Schemas
------------------------------

``to_schema`` works the exact same way with ``msgspec.Struct`` and ``attrs`` classes—no extra adapters needed:

.. tab-set::

    .. tab-item:: Msgspec

        .. code-block:: python

            import msgspec

            class BlogPostStruct(msgspec.Struct):
                id: int
                title: str
                content: str
                published: bool

            def as_msgspec(service: BlogPostService, post: BlogPost) -> BlogPostStruct:
                return service.to_schema(post, schema_type=BlogPostStruct)

    .. tab-item:: attrs

        .. code-block:: python

            from attrs import define

            @define
            class BlogPostAttrs:
                id: int
                title: str
                content: str
                published: bool

            def as_attrs(service: BlogPostService, post: BlogPost) -> BlogPostAttrs:
                return service.to_schema(post, schema_type=BlogPostAttrs)

Related Guides
--------------

* :doc:`/usage/frameworks/litestar` — Inject services directly into Litestar controllers.
* :doc:`/usage/frameworks/fastapi` — Inject services into FastAPI routes with ``Depends``.
* :doc:`/reference/service` — Full service API reference.
