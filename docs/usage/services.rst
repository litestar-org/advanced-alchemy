========
Services
========

Services in Advanced Alchemy wrap repositories to coordinate business rules, lifecycle hooks, pagination, and schema conversion across Pydantic, ``msgspec``, ``attrs`` / ``cattrs``, dataclasses, and SQLModel.

Defining Models and Services
----------------------------

Bind a repository class to :class:`~advanced_alchemy.service.SQLAlchemyAsyncRepositoryService` (or :class:`~advanced_alchemy.service.SQLAlchemySyncRepositoryService`) via ``repository_type``:

.. code-block:: python

    import datetime
    from collections.abc import Hashable
    from typing import Optional

    from pydantic import BaseModel, Field
    from sqlalchemy import Column, ForeignKey, Table
    from sqlalchemy.orm import Mapped, mapped_column, relationship
    from sqlalchemy.sql.elements import ColumnElement

    from advanced_alchemy.base import BigIntAuditBase, orm_registry
    from advanced_alchemy.mixins import SlugKey, UniqueMixin
    from advanced_alchemy.repository import SQLAlchemyAsyncRepository, SQLAlchemyAsyncSlugRepository
    from advanced_alchemy.service import (
        ModelDictT,
        SQLAlchemyAsyncRepositoryService,
        is_dict_with_field,
        is_dict_without_field,
        schema_dump,
    )
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
        tags: Mapped[list["BlogTag"]] = relationship(secondary=blog_post_tag, back_populates="posts", lazy="selectin")

    class BlogTag(BigIntAuditBase, SlugKey, UniqueMixin):
        __tablename__ = "blog_service_tag"

        name: Mapped[str] = mapped_column(unique=True, index=True)
        posts: Mapped[list["BlogPost"]] = relationship(secondary=blog_post_tag, back_populates="tags", viewonly=True)

        @classmethod
        def unique_hash(cls, name: str, slug: Optional[str] = None) -> Hashable:
            return slugify(name)

        @classmethod
        def unique_filter(cls, name: str, slug: Optional[str] = None) -> ColumnElement[bool]:
            return cls.slug == slugify(name)

    class BlogPostCreate(BaseModel):
        title: str
        content: str
        tags: list[str] = Field(default_factory=list)

    class BlogPostUpdate(BaseModel):
        title: Optional[str] = None
        content: Optional[str] = None
        published: Optional[bool] = None
        tags: Optional[list[str]] = None

    class BlogPostResponse(BaseModel):
        id: int
        title: str
        content: str
        published: bool
        created_at: datetime.datetime
        updated_at: datetime.datetime
        model_config = {"from_attributes": True}

    class BlogPostService(SQLAlchemyAsyncRepositoryService[BlogPost]):
        """Post service."""

        class Repo(SQLAlchemyAsyncRepository[BlogPost]):
            model_type = BlogPost

        repository_type = Repo

Service Operations
------------------

Services accept dictionaries, ORM instances, or schema objects directly in ``create``, ``update``, and ``upsert`` methods, and convert results via ``to_schema`` or ``to_list_schema``. They also support recursive nested dictionary creation, row locking via ``with_for_update=True``, and composite primary keys (see :ref:`composite-primary-keys`):

.. code-block:: python

    from collections.abc import Sequence
    from typing import Any

    async def create_post(post_service: BlogPostService, data: BlogPostCreate) -> BlogPostResponse:
        post = await post_service.create(data=data, auto_commit=True)
        return post_service.to_schema(post, schema_type=BlogPostResponse)

    async def update_post(post_service: BlogPostService, post_id: int, data: BlogPostUpdate) -> BlogPostResponse:
        post = await post_service.update(data=data, item_id=post_id, auto_commit=True)
        return post_service.to_schema(post, schema_type=BlogPostResponse)

    async def get_and_lock_post(post_service: BlogPostService, post_id: int) -> BlogPost:
        return await post_service.get(item_id=post_id, with_for_update=True)

    async def delete_composite_roles(user_role_service: Any) -> Sequence[Any]:
        return await user_role_service.delete_many([(1, 5), (1, 6), (2, 5)])

Lifecycle Hooks and Slugs
-------------------------

Override ``to_model_on_create``, ``to_model_on_update``, or ``to_model_on_upsert`` to customize relational hydration or generate slugs before persistence:

.. code-block:: python

    class TaggedBlogPostService(SQLAlchemyAsyncRepositoryService[BlogPost]):
        """Post service with automatic tag resolution."""

        class Repo(SQLAlchemyAsyncRepository[BlogPost]):
            model_type = BlogPost

        loader_options = [BlogPost.tags]
        repository_type = Repo
        match_fields = ["title"]

        async def to_model_on_create(self, data: "ModelDictT[BlogPost]") -> "ModelDictT[BlogPost]":
            dumped = schema_dump(data)
            tags_added = dumped.pop("tags", [])
            post = await super().to_model(dumped)
            if tags_added:
                post.tags.extend(
                    [await BlogTag.as_unique_async(self.repository.session, name=t, slug=slugify(t)) for t in tags_added],
                )
            return post

    class BlogTagService(SQLAlchemyAsyncRepositoryService[BlogTag]):
        """Tag service with automatic slug generation."""

        class Repo(SQLAlchemyAsyncSlugRepository[BlogTag]):
            model_type = BlogTag

        repository_type = Repo
        match_fields = ["name"]

        async def to_model(self, data: "ModelDictT[BlogTag]", operation: Optional[str] = None) -> BlogTag:
            dumped = schema_dump(data)
            if is_dict_without_field(dumped, "slug") and is_dict_with_field(dumped, "name"):
                dumped["slug"] = await self.repository.get_available_slug(dumped["name"])
            return await super().to_model(dumped, operation)

Schema Integration
------------------

``to_schema`` and ``to_list_schema`` convert ORM instances and SQLAlchemy rows into Pydantic models, ``msgspec.Struct`` types, or ``attrs`` classes (using ``cattrs`` automatically when installed):

.. code-block:: python

    from attrs import define
    import msgspec

    class BlogPostStruct(msgspec.Struct):
        id: int
        title: str
        content: str
        published: bool

    @define
    class BlogPostAttrs:
        id: int
        title: str
        content: str
        published: bool

    def to_msgspec_schema(post_service: BlogPostService, post_model: BlogPost) -> BlogPostStruct:
        return post_service.to_schema(post_model, schema_type=BlogPostStruct)

    def to_attrs_schema(post_service: BlogPostService, post_model: BlogPost) -> BlogPostAttrs:
        return post_service.to_schema(post_model, schema_type=BlogPostAttrs)

Framework Integration
---------------------

- :doc:`/usage/frameworks/litestar`
- :doc:`/usage/frameworks/fastapi`
