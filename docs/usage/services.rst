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
- Data transformation using Pydantic or Msgspec models
- Input validation
- Complex operations involving multiple repositories
- Consistent error handling

Basic Service Usage
-------------------

Let's enhance our blog example with services:

.. code-block:: python

    from advanced_alchemy.service import SQLAlchemyAsyncRepositoryService
    from sqlalchemy.ext.asyncio import AsyncSession
    from pydantic import BaseModel
    from typing import Optional
    from uuid import UUID

    # Define DTOs for input/output
    class PostCreate(BaseModel):
        title: str
        content: str
        author_id: UUID
        published: bool = False

    class PostRead(BaseModel):
        id: int
        title: str
        content: str
        author_id: UUID
        published: bool
        created_at: datetime
        updated_at: datetime

    class PostService(SQLAlchemyAsyncRepositoryService[Post]):
        """Service for managing blog posts with data transformation."""

        model_type = Post

        # Define schema mappings
        create_schema = PostCreate
        read_schema = PostRead

    async def create_post(session: AsyncSession, data: PostCreate) -> PostRead:
        service = PostService(session=session)
        # Service automatically handles validation and transformation
        return await service.create(data)

Data Transformation
-------------------

Services automatically handle transformation between DTOs and database models:

.. code-block:: python

    from msgspec import Struct
    from typing import List

    # Using msgspec for better performance
    class PostUpdate(Struct):
        title: Optional[str] = None
        content: Optional[str] = None
        published: Optional[bool] = None

    class PostWithTags(Struct):
        id: int
        title: str
        content: str
        tags: List[str]  # Only include tag names

    class EnhancedPostService(SQLAlchemyAsyncRepositoryService[Post]):
        model_type = Post
        create_schema = PostCreate
        read_schema = PostWithTags
        update_schema = PostUpdate

        async def to_schema(self, model: Post) -> PostWithTags:
            """Custom transformation logic."""
            data = await super().to_schema(model)
            # Enhance the schema with computed fields
            data.tags = [tag.name for tag in model.tags]
            return data

Complex Operations
------------------

Services can encapsulate complex business logic:

.. code-block:: python

    class BlogService(SQLAlchemyAsyncRepositoryService[Post]):
        model_type = Post

        async def publish_with_notification(
            self, post_id: int, notify_followers: bool = True
        ) -> PostRead:
            # Get post
            post = await self.get_one(post_id)

            # Update post
            post.published = True
            post = await self.update(post)

            if notify_followers and post.author.followers:
                # Business logic for notifications
                await self._notify_followers(post)

            return await self.to_schema(post)

        async def _notify_followers(self, post: Post) -> None:
            # Implementation of notification logic
            ...

Batch Operations
----------------

Services support efficient batch operations with schema transformation:

.. code-block:: python

    async def bulk_publish_posts(
        session: AsyncSession, post_ids: list[int]
    ) -> list[PostRead]:
        service = PostService(session=session)

        # Fetch and update posts
        posts = await service.list(Post.id.in_(post_ids))
        for post in posts:
            post.published = True

        # Update and transform all posts
        updated_posts = await service.update_many(posts)
        return await service.to_schema_list(updated_posts)

Error Handling
--------------

Services provide consistent error handling:

.. code-block:: python

    from advanced_alchemy.exceptions import NotFoundError

    async def update_post(
        session: AsyncSession, post_id: int, data: PostUpdate
    ) -> PostRead:
        service = PostService(session=session)
        try:
            post = await service.get_one(post_id)
            return await service.update(post, data)
        except NotFoundError:
            raise HTTPException(status_code=404, detail="Post not found")

This completes our core usage guide. The next sections will cover framework-specific integrations
and how to use Advanced Alchemy with Litestar, FastAPI, and Sanic.
