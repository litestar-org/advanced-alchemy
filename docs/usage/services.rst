========
Services
========

Services in Advanced Alchemy build on repositories to provide higher-level business logic, data transformation,
and schema validation. While repositories handle raw database operations, services coordinate application rules
and schema conversion.

Understanding Services
----------------------

Services provide:

- Business logic abstraction
- Data transformation using Pydantic, Msgspec, or attrs models
- Input validation and type-safe schema conversion
- Complex operations involving multiple repositories
- Consistent error handling
- Automatic schema validation and transformation
- Support for SQLAlchemy query results (Row types) and RowMapping objects

.. note::

    The examples below define a minimal ``Post`` / ``Tag`` model inline so the service examples stay self-contained.

Basic Service Usage
-------------------

Let's build upon a blog example by creating services for posts:

.. code-block:: python

    import datetime
    from typing import Hashable, Optional

    from pydantic import BaseModel, Field
    from sqlalchemy import Column, ForeignKey, Table
    from sqlalchemy.orm import Mapped, mapped_column, relationship
    from sqlalchemy.sql.elements import ColumnElement

    from advanced_alchemy.base import BigIntAuditBase, orm_registry
    from advanced_alchemy.mixins import SlugKey, UniqueMixin
    from advanced_alchemy.repository import SQLAlchemyAsyncRepository, SQLAlchemyAsyncSlugRepository
    from advanced_alchemy.service import (
        SQLAlchemyAsyncRepositoryService,
        is_dict_with_field,
        is_dict_without_field,
        schema_dump,
    )
    from advanced_alchemy.utils.serialization import ModelDictT
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
            secondary=blog_post_tag,
            back_populates="posts",
            lazy="selectin",
        )


    class BlogTag(BigIntAuditBase, SlugKey, UniqueMixin):
        __tablename__ = "blog_service_tag"

        name: Mapped[str] = mapped_column(unique=True, index=True)
        posts: Mapped[list["BlogPost"]] = relationship(
            secondary=blog_post_tag,
            back_populates="tags",
            viewonly=True,
        )

        @classmethod
        def unique_hash(cls, name: str, slug: Optional[str] = None) -> Hashable:
            return slugify(name)

        @classmethod
        def unique_filter(
            cls,
            name: str,
            slug: Optional[str] = None,
        ) -> ColumnElement[bool]:
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

Services provide high-level methods for common operations:

.. code-block:: python

    async def create_post(post_service: BlogPostService, data: BlogPostCreate) -> BlogPostResponse:
        post = await post_service.create(data=data, auto_commit=True)
        return post_service.to_schema(post, schema_type=BlogPostResponse)


    async def update_post(
        post_service: BlogPostService,
        post_id: int,
        data: BlogPostUpdate,
    ) -> BlogPostResponse:
        post = await post_service.update(data=data, item_id=post_id, auto_commit=True)
        return post_service.to_schema(post, schema_type=BlogPostResponse)

.. versionadded:: 1.9.0

Advanced Alchemy's service layer automatically handles recursive model creation from nested dictionaries. When you pass a
dictionary containing nested dictionaries that match a model's relationships, the service will instantiate the related models.

.. code-block:: python

    from typing import Any


    async def create_user_with_profile(user_service: Any) -> Any:
        user_data = {
            "username": "cody",
            "email": "cody@litestar.dev",
            "profile": {
                "bio": "Software Engineer",
                "twitter": "@cofin",
            },
        }
        return await user_service.create(data=user_data)

Row Locking (FOR UPDATE)
************************

.. versionadded:: 1.9.0

Service retrieval methods like ``get`` support the ``with_for_update`` parameter, which is passed through to the underlying repository.

.. code-block:: python

    from typing import Any


    async def get_user_for_update(user_service: Any, user_id: Any) -> Any:
        return await user_service.get(item_id=user_id, with_for_update=True)

Composite Primary Keys
**********************

Services fully support models with composite primary keys using the same formats as repositories.
Pass primary key values as tuples or dictionaries when using ``get``, ``update``, or ``delete`` methods:

.. code-block:: python

    from typing import Any, Sequence


    async def update_user_role_permissions(user_role_service: Any, user_id: int, role_id: int) -> Any:
        _current = await user_role_service.get((user_id, role_id))
        return await user_role_service.update(
            data={"permissions": "admin"},
            item_id={"user_id": user_id, "role_id": role_id},
        )


    async def delete_user_roles(user_role_service: Any) -> Sequence[Any]:
        return await user_role_service.delete_many([(1, 5), (1, 6), (2, 5)])

See :ref:`composite-primary-keys` in the Repositories documentation for more details on supported formats.

Complex Operations
------------------

Services can handle complex business logic involving multiple models.
The code below shows a service coordinating posts and tags.

.. code-block:: python

    class TaggedBlogPostService(SQLAlchemyAsyncRepositoryService[BlogPost]):
        """Post service for handling post operations with tag management."""

        class Repo(SQLAlchemyAsyncRepository[BlogPost]):
            model_type = BlogPost

        loader_options = [BlogPost.tags]
        repository_type = Repo
        match_fields = ["title"]

        async def to_model_on_create(self, data: "ModelDictT[BlogPost]") -> "ModelDictT[BlogPost]":
            data = schema_dump(data)
            tags_added = data.pop("tags", [])
            post = await super().to_model(data)

            if tags_added:
                post.tags.extend(
                    [
                        await BlogTag.as_unique_async(self.repository.session, name=tag, slug=slugify(tag))
                        for tag in tags_added
                    ],
                )
            return post

        async def to_model_on_update(self, data: "ModelDictT[BlogPost]") -> "ModelDictT[BlogPost]":
            data = schema_dump(data)
            tags_updated = data.pop("tags", [])
            post = await super().to_model(data)

            if tags_updated is not None:
                existing_tags = [tag.name for tag in post.tags]
                tags_to_remove = [tag for tag in post.tags if tag.name not in tags_updated]
                tags_to_add = [tag for tag in tags_updated if tag not in existing_tags]

                for tag_to_remove in tags_to_remove:
                    post.tags.remove(tag_to_remove)

                post.tags.extend(
                    [
                        await BlogTag.as_unique_async(self.repository.session, name=tag, slug=slugify(tag))
                        for tag in tags_to_add
                    ],
                )
            return post

Working with Slugs
------------------

Services can automatically generate URL-friendly slugs using the ``SQLAlchemyAsyncSlugRepository``.
Here's an example service for managing tags with automatic slug generation:

.. code-block:: python

    class BlogTagService(SQLAlchemyAsyncRepositoryService[BlogTag]):
        """Tag service with automatic slug generation."""

        class Repo(SQLAlchemyAsyncSlugRepository[BlogTag]):
            model_type = BlogTag

        repository_type = Repo
        match_fields = ["name"]

        async def to_model_on_create(self, data: "ModelDictT[BlogTag]") -> "ModelDictT[BlogTag]":
            data = schema_dump(data)
            if is_dict_without_field(data, "slug") and is_dict_with_field(data, "name"):
                data["slug"] = await self.repository.get_available_slug(data["name"])
            return data

        async def to_model_on_update(self, data: "ModelDictT[BlogTag]") -> "ModelDictT[BlogTag]":
            data = schema_dump(data)
            if is_dict_without_field(data, "slug") and is_dict_with_field(data, "name"):
                data["slug"] = await self.repository.get_available_slug(data["name"])
            return data

        async def to_model_on_upsert(self, data: "ModelDictT[BlogTag]") -> "ModelDictT[BlogTag]":
            data = schema_dump(data)
            if is_dict_without_field(data, "slug") and is_dict_with_field(data, "name"):
                data["slug"] = await self.repository.get_available_slug(data["name"])
            return data

Schema Integration
------------------

Advanced Alchemy services support multiple schema libraries for data transformation and validation:

Pydantic Models
***************

.. code-block:: python

    class BlogPostSchema(BaseModel):
        id: int
        title: str
        content: str
        published: bool

        model_config = {"from_attributes": True}


    def to_pydantic_schema(post_service: BlogPostService, post_model: BlogPost) -> BlogPostSchema:
        return post_service.to_schema(post_model, schema_type=BlogPostSchema)

Msgspec Structs
***************

.. code-block:: python

    try:
        from msgspec import Struct
    except ModuleNotFoundError:  # pragma: no cover - optional dependency in docs examples
        class Struct:  # type: ignore[no-redef]
            pass


    class BlogPostStruct(Struct):
        id: int
        title: str
        content: str
        published: bool


    def to_msgspec_schema(post_service: BlogPostService, post_model: BlogPost) -> BlogPostStruct:
        return post_service.to_schema(post_model, schema_type=BlogPostStruct)

Attrs Classes
*************

.. code-block:: python

    try:
        from attrs import define
    except ModuleNotFoundError:  # pragma: no cover - optional dependency in docs examples
        def define(cls):  # type: ignore[misc]
            return cls


    @define
    class BlogPostAttrs:
        id: int
        title: str
        content: str
        published: bool


    def to_attrs_schema(post_service: BlogPostService, post_model: BlogPost) -> BlogPostAttrs:
        return post_service.to_schema(post_model, schema_type=BlogPostAttrs)

.. note::

    **Enhanced attrs Support with cattrs**: When both ``attrs`` and ``cattrs`` are installed,
    Advanced Alchemy automatically uses ``cattrs.structure()`` and ``cattrs.unstructure()``
    for improved performance and type-aware serialization. This provides better handling of
    complex types, nested structures, and custom converters.


Multi-Service Acquisition and Composition
-----------------------------------------

When workflows require multiple services operating on the same transaction boundaries, ``provide_services`` and
``ServiceGroup`` allow coordinating multiple services over a single shared SQLAlchemy session.

Key capabilities include:

- **Unified Interface**: Accepts either service classes (``BlogPostService``) or provider callables (generators or functions) as positional specifications.
- **Sync and Async Parity**: Supports both ``async with provide_services(...)`` and ``with provide_services(...)``.
- **Flexible Session Resolution**:
  - ``session=``: Use an existing session without managing its lifecycle.
  - ``config=``: Automatically acquires a new session via ``config.get_session()`` and commits/closes it upon block exit (ideal for CLI commands and background tasks).
  - ``connection=``: Resolves the request-scoped session from an active ASGI connection (e.g. Litestar ``Request`` or ``ASGIConnection``) via ``config.provide_session()``.
- **LIFO Teardown**: Cleans up generator providers in reverse order of entry, ensuring dependent resources are released safely.

Using ``provide_services``
**************************

Acquire multiple services inside an ``async with`` block:

.. code-block:: python

    from advanced_alchemy.service import provide_services


    async def publish_post_with_audit(
        session: AsyncSession,
        post_id: int,
    ) -> None:
        async with provide_services(
            BlogPostService,
            BlogTagService,
            session=session,
        ) as (post_service, tag_service):
            post = await post_service.get(post_id)
            tag = await tag_service.get_one_or_none(name="announcements")
            assert post_service.session is tag_service.session

Session Resolution with ``config=`` (CLI & Workers)
***************************************************

For standalone scripts, CLI commands, or background task runners where an active session does not yet exist, pass ``config=`` to automatically open, provide, and tear down the session:

.. code-block:: python

    from advanced_alchemy.service import provide_services


    async def run_nightly_batch(config: SQLAlchemyAsyncConfig) -> None:
        async with provide_services(
            BlogPostService,
            BlogTagService,
            config=config,
        ) as (posts, tags):
            ...

ASGI Connection Resolution (Guards & Middleware)
************************************************

In Litestar guards, middleware, and request interceptors, access the request-scoped session by providing both ``connection=`` and ``config=``:

.. code-block:: python

    from litestar.connection import ASGIConnection
    from advanced_alchemy.service import provide_services


    async def auth_guard(
        connection: ASGIConnection,
        config: SQLAlchemyAsyncConfig,
    ) -> None:
        async with provide_services(
            BlogPostService,
            BlogTagService,
            connection=connection,
            config=config,
        ) as (posts, tags):
            ...

Reusable Composition with ``ServiceGroup``
******************************************

``ServiceGroup`` defines a reusable group of services with shared default loading options and configurations:

.. code-block:: python

    from advanced_alchemy.service import ServiceGroup

    blog_group = ServiceGroup(BlogPostService, BlogTagService)

    # Use .new() for explicit context acquisition:
    async with blog_group.new(session=session) as (posts, tags):
        ...

    # Use .provide() for dependency injection:
    # Litestar:
    # dependencies = {"blog_services": Provide(blog_group.provide(config=config))}
    #
    # Route handler:
    # async def handler(blog_services: tuple[BlogPostService, BlogTagService]) -> ...:
    #     posts, tags = blog_services


Framework Integration
---------------------

Services integrate seamlessly with both Litestar and FastAPI.

- :doc:`frameworks/litestar`
- :doc:`frameworks/fastapi`
