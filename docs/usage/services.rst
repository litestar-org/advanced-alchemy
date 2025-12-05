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

    from advanced_alchemy.repository import SQLAlchemyAsyncRepository
    from advanced_alchemy.service import SQLAlchemyAsyncRepositoryService
    from pydantic import BaseModel

    # Pydantic schemas for validation
    class PostCreate(BaseModel):
        title: str
        content: str
        tag_names: list[str]


    class PostUpdate(BaseModel):
        title: str | None = None
        content: str | None = None
        published: bool | None = None


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

        class PostRepository(SQLAlchemyAsyncRepository[Post]):
            """Post repository."""

            model_type = Post

        loader_options = [Post.tags]
        repository_type = PostRepository
        match_fields = ["title"]

        # Override creation behavior to handle tags
        async def create(self, data: ModelDictT[Post], **kwargs: Any) -> Post:
            """Create a new post with tags, if provided."""
            data_dict = schema_dump(data)
            tags_added = data_dict.pop("tags", [])
            data = data_dict

            post = await self.to_model(data, "create")

            if tags_added:
                tags_added = [schema_dump(tag) for tag in tags_added]
                post.tags.extend(
                    [
                        await Tag.as_unique_async(self.repository.session, name=tag["name"], slug=slugify(tag["name"]))
                        for tag in tags_added
                    ],
                )
            return await super().create(data=post, **kwargs)

        # Override update behavior to handle tags
        async def update(
            self,
            data: ModelDictT[Post],
            item_id: Any | None = None,
            **kwargs: Any,
        ) -> Post:
            """Update a post with tags, if provided."""
            data_dict = schema_dump(data)
            tags_updated = data_dict.pop("tags", [])

            # Determine the effective item_id - either from parameter or from the data itself
            effective_item_id = item_id if item_id is not None else data_dict.get("id")

            # Get existing post to access current tags
            if effective_item_id is not None:
                existing_post = await self.get(effective_item_id)
                existing_tags = [tag.name for tag in existing_post.tags]
            else:
                existing_tags = []

            post = await self.to_model(data_dict, "update")

            if tags_updated:
                tags_updated = [schema_dump(tag) for tag in tags_updated]
                # Determine tags to remove and add
                tags_to_remove = [tag for tag in post.tags if tag.name not in [t["name"] for t in tags_updated]]
                tags_to_add = [tag for tag in tags_updated if tag["name"] not in existing_tags]

                for tag_rm in tags_to_remove:
                    post.tags.remove(tag_rm)

                post.tags.extend(
                    [
                        await Tag.as_unique_async(self.repository.session, name=tag["name"], slug=slugify(tag["name"]))
                        for tag in tags_to_add
                    ],
                )

            return await super().update(data=post, item_id=effective_item_id, **kwargs)

        # A custom write operation
        async def publish_post(
            self,
            post_id: int,
            publish: bool = True,
        ) -> PostResponse:
            """Publish or unpublish a post."""
            post = await self.update(
                item_id=post_id,
                data={"published": publish},
                auto_commit=True,
            )
            return self.to_schema(post, schema_type=PostResponse)

        # A custom read operation
        async def get_recent_posts(
            self,
            days: int = 7,
            limit: int = 10,
            offset: int = 0,
        ) -> OffsetPagination[PostResponse]:
            """Get recent published posts."""
            posts = await self.list(
                Post.published.is_(True),
                Post.created_at > (datetime.datetime.now(tz=datetime.timezone.utc) - datetime.timedelta(days=days)),
                LimitOffset(limit=limit, offset=offset),
                order_by=[Post.created_at.desc()],
            )
            return self.to_schema(posts, schema_type=PostResponse)

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
    query_results = await db_session.execute(select(Post))
    rows = query_results.fetchall()  # Returns list[Row[Any]]

    # Convert Row objects to schema types
    post_data = post_service.to_schema(rows[0][0], schema_type=PostSchema)
    posts_list = post_service.to_schema([row[0] for row in rows], schema_type=PostSchema)

    # Also supports RowMapping objects
    row_mapping = await db_session.execute(select(Post))
    row_mapping_results = row_mapping.mappings().first()['Post']
    mapping_data = post_service.to_schema(row_mapping_results, schema_type=PostSchema)


Framework Integration
---------------------

Services integrate seamlessly with both Litestar and FastAPI.

- :doc:`frameworks/litestar`
- :doc:`frameworks/fastapi`
