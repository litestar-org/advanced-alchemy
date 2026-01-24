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

.. note::

    The following example assumes the existence of the
    ``Post`` model defined in :ref:`many_to_many_relationships` and the
    ``Tag`` model defined in :ref:`using_unique_mixin`.

Basic Service Usage
-------------------

Let's build upon our blog example by creating services for posts:

.. code-block:: python

    import datetime
    from typing import Optional

    from advanced_alchemy.repository import SQLAlchemyAsyncRepository
    from advanced_alchemy.service import SQLAlchemyAsyncRepositoryService
    from pydantic import BaseModel

    # Pydantic schemas for validation
    class PostCreate(BaseModel):
        title: str
        content: str
        tag_names: list[str]


    class PostUpdate(BaseModel):
        title: Optional[str] = None
        content: Optional[str] = None
        published: Optional[bool] = None


    class PostResponse(BaseModel):
        id: int
        title: str
        content: str
        published: bool
        created_at: datetime.datetime
        updated_at: datetime.datetime

        model_config = {"from_attributes": True}


    class PostService(SQLAlchemyAsyncRepositoryService[Post]):
        """Post Service."""

        class PostRepository(SQLAlchemyAsyncRepository[Post]):
            """Post repository."""

            model_type = Post

        repository_type = PostRepository

Service Operations
------------------

Services provide high-level methods for common operations:

.. code-block:: python

    async def create_post(post_service: PostService, data: PostCreate) -> PostResponse:
        post = await post_service.create(data=data, auto_commit=True)
        return post_service.to_schema(post, schema_type=PostResponse)


    async def update_post(
        post_service: PostService,
        post_id: int,
        data: PostUpdate,
    ) -> PostResponse:
        post = await post_service.update(item_id=post_id, data=data, auto_commit=True)
        return post_service.to_schema(post, schema_type=PostResponse)

Complex Operations
-------------------

Services can handle complex business logic involving multiple models.
The code below shows a service coordinating posts and tags.

.. code-block:: python

    import datetime
    from typing import Any
    from advanced_alchemy.repository import SQLAlchemyAsyncRepository
    from advanced_alchemy.service import SQLAlchemyAsyncRepositoryService, schema_dump
    from advanced_alchemy.service.typing import ModelDictT
    from advanced_alchemy.filters import LimitOffset
    from advanced_alchemy.service.pagination import OffsetPagination
    from advanced_alchemy.utils.text import slugify

    class PostService(SQLAlchemyAsyncRepositoryService[Post]):
        """Post service for handling post operations with tag management."""

        class Repo(SQLAlchemyAsyncRepository[Post]):
            """Post repository."""

            model_type = Post

        loader_options = [Post.tags]
        repository_type = Repo
        match_fields = ["title"]

        async def to_model_on_create(self, data: ModelDictT[Post]) -> ModelDictT[Post]:
            """Convert and enrich data for post creation, handling tags."""
            data = schema_dump(data)
            tags_added = data.pop("tags", [])
            data = await super().to_model(data)

            if tags_added:
                data.tags.extend(
                    [
                        await Tag.as_unique_async(self.repository.session, name=tag, slug=slugify(tag))
                        for tag in tags_added
                    ],
                )
            return data

        async def to_model_on_update(self, data: ModelDictT[Post]) -> ModelDictT[Post]:
            """Convert and enrich data for post update, handling tags."""
            data = schema_dump(data)
            tags_updated = data.pop("tags", [])
            post = await super().to_model(data)

            if tags_updated:
                existing_tags = [tag.name for tag in post.tags]
                tags_to_remove = [tag for tag in post.tags if tag.name not in tags_updated]
                tags_to_add = [tag for tag in tags_updated if tag not in existing_tags]

                for tag_rm in tags_to_remove:
                    post.tags.remove(tag_rm)

                post.tags.extend(
                    [
                        await Tag.as_unique_async(self.repository.session, name=tag, slug=slugify(tag))
                        for tag in tags_to_add
                    ],
                )
            return post

Working with Slugs
------------------

Services can automatically generate URL-friendly slugs using the ``SQLAlchemyAsyncSlugRepository``.
Here's an example service for managing tags with automatic slug generation:

.. code-block:: python

    from advanced_alchemy.repository import SQLAlchemyAsyncSlugRepository
    from advanced_alchemy.service import SQLAlchemyAsyncRepositoryService, schema_dump, is_dict_without_field, is_dict_with_field
    from advanced_alchemy.service.typing import ModelDictT

    class TagService(SQLAlchemyAsyncRepositoryService[Tag]):
        """Tag service with automatic slug generation."""

        class Repo(SQLAlchemyAsyncSlugRepository[Tag]):
            """Tag repository."""

            model_type = Tag

        repository_type = Repo
        match_fields = ["name"]

        async def to_model_on_create(self, data: ModelDictT[Tag]) -> ModelDictT[Tag]:
            """Generate slug on tag creation if not provided."""
            data = schema_dump(data)
            if is_dict_without_field(data, "slug") and is_dict_with_field(data, "name"):
                data["slug"] = await self.repository.get_available_slug(data["name"])
            return data

        async def to_model_on_update(self, data: ModelDictT[Tag]) -> ModelDictT[Tag]:
            """Update slug if name changes."""
            data = schema_dump(data)
            if is_dict_without_field(data, "slug") and is_dict_with_field(data, "name"):
                data["slug"] = await self.repository.get_available_slug(data["name"])
            return data

        async def to_model_on_upsert(self, data: ModelDictT[Tag]) -> ModelDictT[Tag]:
            """Generate slug on upsert if needed."""
            data = schema_dump(data)
            if is_dict_without_field(data, "slug") and (tag_name := data.get("name")) is not None:
                data["slug"] = await self.repository.get_available_slug(tag_name)
            return data

Schema Integration
------------------

Advanced Alchemy services support multiple schema libraries for data transformation and validation:

Pydantic Models
***************

.. code-block:: python

    from pydantic import BaseModel
    from typing import Optional

    class PostSchema(BaseModel):
        id: int
        title: str
        content: str
        published: bool

        model_config = {"from_attributes": True}

    # Convert database model to Pydantic schema
    post_data = post_service.to_schema(post_model, schema_type=PostSchema)

Msgspec Structs
***************

.. code-block:: python

    from msgspec import Struct
    from typing import Optional

    class PostStruct(Struct):
        id: int
        title: str
        content: str
        published: bool

    # Convert database model to Msgspec struct
    post_data = post_service.to_schema(post_model, schema_type=PostStruct)

Attrs Classes
*************

.. code-block:: python

    from attrs import define
    from typing import Optional

    @define
    class PostAttrs:
        id: int
        title: str
        content: str
        published: bool

    # Convert database model to attrs class
    post_data = post_service.to_schema(post_model, schema_type=PostAttrs)

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
    result = await db_session.execute(select(Post))
    post = result.scalar_one()  # Returns Post model

    # Convert model to schema type
    post_data = post_service.to_schema(post, schema_type=PostSchema)

    # Working with multiple results
    result = await db_session.execute(select(Post))
    posts = result.scalars().all()  # Returns list of Post models
    posts_list = post_service.to_schema(posts, schema_type=PostSchema)

    # Also supports RowMapping objects
    result = await db_session.execute(select(Post))
    row_mapping = result.mappings().first()
    mapping_data = post_service.to_schema(row_mapping["Post"], schema_type=PostSchema)


Framework Integration
---------------------

Services integrate seamlessly with both Litestar and FastAPI.

- :doc:`frameworks/litestar`
- :doc:`frameworks/fastapi`
