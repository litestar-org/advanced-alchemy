========
Services
========

Services in Advanced Alchemy build upon repositories to provide higher-level business logic, data transformation,
and schema validation. While repositories handle raw database operations, services handle the application's
business rules and data transformation needs.

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

Basic Service Usage
-------------------

Let's build upon our blog example by creating services for posts and tags:

.. code-block:: python

    import datetime
    from typing import Optional, List
    from uuid import UUID

    from advanced_alchemy.service import SQLAlchemyAsyncRepositoryService
    from pydantic import BaseModel

    # Pydantic schemas for validation
    class PostCreate(BaseModel):
        title: str
        content: str
        tag_names: List[str]

    class PostUpdate(BaseModel):
        title: Optional[str] = None
        content: Optional[str] = None
        published: Optional[bool] = None

    class PostResponse(BaseModel):
        id: int
        title: str
        content: str
        published: bool
        published_at: Optional[datetime.datetime]
        created_at: datetime.datetime
        updated_at: datetime.datetime
        tags: List["TagResponse"]

        model_config = {"from_attributes": True}

    class PostService(SQLAlchemyAsyncRepositoryService[Post]):
        """Service for managing blog posts with automatic schema validation."""

        repository_type = PostRepository

Service Operations
------------------

Services provide high-level methods for common operations:

.. code-block:: python

    async def create_post(
        post_service: PostService,
        data: PostCreate,
    ) -> PostResponse:
        """Create a post with associated tags."""
        post = await post_service.create(
            data,
            auto_commit=True,
        )
        return post_service.to_schema(post, schema_type=PostResponse)

    async def update_post(
        post_service: PostService,
        post_id: int,
        data: PostUpdate,
    ) -> PostResponse:
        """Update a post."""
        post = await post_service.update(
            item_id=post_id,
            data=data,
            auto_commit=True,
        )
        return post_service.to_schema(post, schema_type=PostResponse)

Complex Operations
-------------------

Services can handle complex business logic involving multiple models.
The code below shows a service coordinating posts and tags.

.. note::

    The following example assumes the existence of the
    ``Post`` model defined in :ref:`many_to_many_relationships` and the
    ``Tag`` model defined in :ref:`using_unique_mixin`.

.. code-block:: python

    from typing import List

    from advanced_alchemy.exceptions import ErrorMessages
    from advanced_alchemy.service import SQLAlchemyAsyncRepositoryService
    from advanced_alchemy.service.typing import ModelDictT

    from .models import Post, Tag

    class PostService(SQLAlchemyAsyncRepositoryService[Post, PostRepository]):

        default_load_options = [Post.tags]
        repository_type = PostRepository
        match_fields = ["name"]

        # Override creation behavior to handle tags
        async def create(self, data: ModelDictT[Post], **kwargs) -> Post:
            """Create a new post with tags, if provided."""
            tags_added: list[str] = []
            if isinstance(data, dict):
                data["id"] = data.get("id", uuid4())
                tags_added = data.pop("tags", [])
            data = await self.to_model(data, "create")
            if tags_added:
                data.tags.extend(
                    [
                        await Tag.as_unique_async(self.repository.session, name=tag_text, slug=slugify(tag_text))
                        for tag_text in tags_added
                    ],
                )
            return await super().create(data=data, **kwargs)

        # Override update behavior to handle tags
        async def update(
            self,
            data: ModelDictT[Post],
            item_id: Any | None = None,
            **kwargs,
        ) -> Post:
            """Update a post with tags, if provided."""
            tags_updated: list[str] = []
            if isinstance(data, dict):
                tags_updated.extend(data.pop("tags", None) or [])
                data["id"] = item_id
                data = await self.to_model(data, "update")
                existing_tags = [tag.name for tag in data.tags]
                tags_to_remove = [tag for tag in data.tags if tag.name not in tags_updated]
                tags_to_add = [tag for tag in tags_updated if tag not in existing_tags]
                for tag_rm in tags_to_remove:
                    data.tags.remove(tag_rm)
                data.tags.extend(
                    [
                        await Tag.as_unique_async(self.repository.session, name=tag_text, slug=slugify(tag_text))
                        for tag_text in tags_to_add
                    ],
                )
            return await super().update(
                data=data,
                item_id=item_id,
                **kwargs,
            )

        # A custom write operation
        async def publish_post(
            self,
            post_id: int,
            publish: bool = True,
        ) -> PostResponse:
            """Publish or unpublish a post with timestamp."""
            data = PostUpdate(
                published=publish,
                published_at=datetime.datetime.utcnow() if publish else None,
            )
            post = await self.repository.update(
                item_id=post_id,
                data=data,
                auto_commit=True,
            )
            return self.to_schema(post, schema_type=PostResponse)

        # A custom read operation
        async def get_trending_posts(
            self,
            days: int = 7,
            min_views: int = 100,
        ) -> List[PostResponse]:
            """Get trending posts based on view count and recency."""
            posts = await self.post_service.list(
                Post.published == True,
                Post.created_at > (datetime.datetime.utcnow() - timedelta(days=days)),
                Post.view_count >= min_views,
                order_by=[Post.view_count.desc()],
            )
            return self.post_service.to_schema(posts, schema_type=PostResponse)

        # Override the default `to_model` to handle slugs
        async def to_model(self, data: ModelDictT[Post], operation: str | None = None) -> Post:
            """Convert a dictionary, msgspec Struct, or Pydantic model to a Post model. """
            if (is_msgspec_struct(data) or is_pydantic_model(data)) and operation in {"create", "update"} and data.slug is None:
                data.slug = await self.repository.get_available_slug(data.name)
            if is_dict(data) and "slug" not in data and operation == "create":
                data["slug"] = await self.repository.get_available_slug(data["name"])
            if is_dict(data) and "slug" not in data and "name" in data and operation == "update":
                data["slug"] = await self.repository.get_available_slug(data["name"])
            return await super().to_model(data, operation)

Schema Integration
------------------

Advanced Alchemy services support multiple schema libraries for data transformation and validation:

Pydantic Models
***************

.. code-block:: python

    from pydantic import BaseModel
    from typing import Optional

    class UserSchema(BaseModel):
        name: str
        email: str
        age: Optional[int] = None

        model_config = {"from_attributes": True}

    # Convert database model to Pydantic schema
    user_data = service.to_schema(user_model, schema_type=UserSchema)

Msgspec Structs
***************

.. code-block:: python

    from msgspec import Struct
    from typing import Optional

    class UserStruct(Struct):
        name: str
        email: str
        age: Optional[int] = None

    # Convert database model to Msgspec struct
    user_data = service.to_schema(user_model, schema_type=UserStruct)

Attrs Classes
*************

.. code-block:: python

    from attrs import define
    from typing import Optional

    @define
    class UserAttrs:
        name: str
        email: str
        age: Optional[int] = None

    # Convert database model to attrs class
    user_data = service.to_schema(user_model, schema_type=UserAttrs)

.. note::

    **Enhanced attrs Support with cattrs**: When both ``attrs`` and ``cattrs`` are installed,
    Advanced Alchemy automatically uses ``cattrs.structure()`` and ``cattrs.unstructure()``
    for improved performance and type-aware serialization. This provides better handling of
    complex types, nested structures, and custom converters.

SQLAlchemy Query Result Support
*******************************

Services now provide comprehensive support for SQLAlchemy query results:

.. code-block:: python

    from sqlalchemy import select

    # Direct support for SQLAlchemy Row objects
    query_results = await session.execute(select(User))
    rows = query_results.fetchall()  # Returns list[Row[Any]]

    # Convert Row objects to schema types
    user_data = service.to_schema(rows[0], schema_type=UserSchema)
    users_paginated = service.to_schema(rows, schema_type=UserSchema)

    # Also supports RowMapping objects
    row_mapping_results = await session.execute(select(User)).mappings()
    mapping_data = service.to_schema(row_mapping_results.first(), schema_type=UserSchema)


Framework Integration
---------------------

Services integrate seamlessly with both Litestar and FastAPI.

- :doc:`frameworks/litestar`
- :doc:`frameworks/fastapi`
