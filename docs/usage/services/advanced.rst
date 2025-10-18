========
Advanced
========

Advanced service patterns handle complex business logic, custom operations, and multi-repository coordination.

Prerequisites
=============

Familiarity with :doc:`basics` and :doc:`schemas` recommended.

Complex Operations
==================

Services coordinate operations across multiple repositories and enforce business rules.

Overriding CRUD Methods
------------------------

Customize create/update behavior:

.. note::

    The following example assumes the existence of the
    ``Post`` model defined in :ref:`many_to_many_relationships` and the
    ``Tag`` model defined in :ref:`using_unique_mixin`.

.. code-block:: python

    from typing import Any
    from uuid import uuid4

    from advanced_alchemy.service import SQLAlchemyAsyncRepositoryService
    from advanced_alchemy.service.typing import ModelDictT
    from advanced_alchemy.utils.text import slugify

    class PostService(SQLAlchemyAsyncRepositoryService[Post]):

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

This pattern:

- Extracts tags from input data
- Uses ``UniqueMixin`` for get-or-create
- Updates relationships
- Calls parent method for database operation

Custom Business Operations
---------------------------

Add domain-specific methods:

.. code-block:: python

    import datetime
    from datetime import timedelta
    from typing import List

    class PostService(SQLAlchemyAsyncRepositoryService[Post]):
        repository_type = PostRepository

        # Custom write operation
        async def publish_post(
            self,
            post_id: int,
            publish: bool = True,
        ) -> Post:
            """Publish or unpublish a post with timestamp."""
            data = {
                "published": publish,
                "published_at": datetime.datetime.utcnow() if publish else None,
            }
            return await self.repository.update(
                item_id=post_id,
                data=data,
                auto_commit=True,
            )

        # Custom read operation
        async def get_trending_posts(
            self,
            days: int = 7,
            min_views: int = 100,
        ) -> List[Post]:
            """Get trending posts based on view count and recency."""
            return await self.list(
                Post.published == True,
                Post.created_at > (datetime.datetime.utcnow() - timedelta(days=days)),
                Post.view_count >= min_views,
                order_by=[Post.view_count.desc()],
            )

Custom methods encapsulate business logic.

Overriding to_model
-------------------

Customize schema-to-model conversion:

.. code-block:: python

    from advanced_alchemy.utils.dataclass import is_dict, is_msgspec_struct, is_pydantic_model

    class PostService(SQLAlchemyAsyncRepositoryService[Post]):
        repository_type = PostRepository

        # Override the default `to_model` to handle slugs
        async def to_model(self, data: ModelDictT[Post], operation: str | None = None) -> Post:
            """Convert a dictionary, msgspec Struct, or Pydantic model to a Post model."""
            if (is_msgspec_struct(data) or is_pydantic_model(data)) and operation in {"create", "update"} and data.slug is None:
                data.slug = await self.repository.get_available_slug(data.name)
            if is_dict(data) and "slug" not in data and operation == "create":
                data["slug"] = await self.repository.get_available_slug(data["name"])
            if is_dict(data) and "slug" not in data and "name" in data and operation == "update":
                data["slug"] = await self.repository.get_available_slug(data["name"])
            return await super().to_model(data, operation)

This pattern generates slugs automatically during conversion.

Multi-Repository Coordination
==============================

Services coordinate multiple repositories:

.. code-block:: python

    from sqlalchemy.ext.asyncio import AsyncSession

    class BlogService:
        """Service coordinating posts, tags, and authors."""

        def __init__(self, session: AsyncSession):
            self.post_service = PostService(session=session)
            self.tag_service = TagService(session=session)
            self.author_service = AuthorService(session=session)
            self.session = session

        async def create_post_with_author(
            self,
            title: str,
            content: str,
            author_email: str,
            tag_names: list[str]
        ) -> Post:
            """Create post, ensuring author exists and tags are created."""
            async with self.session.begin():
                # Get or create author
                author = await self.author_service.get_one_or_none(
                    Author.email == author_email
                )
                if not author:
                    author = await self.author_service.create(
                        {"email": author_email, "name": author_email.split("@")[0]}
                    )

                # Create post with tags (handled by PostService.create override)
                post_data = {
                    "title": title,
                    "content": content,
                    "author_id": author.id,
                    "tags": tag_names
                }
                post = await self.post_service.create(post_data)

                return post

This pattern:

- Coordinates multiple services
- Manages transaction boundaries
- Enforces business rules across entities

Implementation Patterns
=======================

Service Composition
-------------------

Compose services for complex operations:

.. code-block:: python

    class AnalyticsService:
        """Analytics service using multiple domain services."""

        def __init__(self, session: AsyncSession):
            self.post_service = PostService(session=session)
            self.author_service = AuthorService(session=session)

        async def get_author_stats(self, author_id: int) -> dict:
            """Get comprehensive author statistics."""
            author = await self.author_service.get(author_id)
            posts = await self.post_service.list(Post.author_id == author_id)

            return {
                "author": author,
                "total_posts": len(posts),
                "published_posts": len([p for p in posts if p.published]),
                "total_views": sum(p.view_count for p in posts),
            }

Composition enables complex analytics without coupling services.

Error Handling
--------------

Services handle errors consistently:

.. code-block:: python

    from advanced_alchemy.exceptions import NotFoundError, ConflictError

    class PostService(SQLAlchemyAsyncRepositoryService[Post]):
        repository_type = PostRepository

        async def publish_post(self, post_id: int) -> Post:
            """Publish a post, ensuring it exists and isn't already published."""
            try:
                post = await self.get(post_id)
            except NotFoundError:
                raise NotFoundError(f"post not found with id: {post_id}")

            if post.published:
                raise ConflictError(f"post already published: {post_id}")

            post.published = True
            post.published_at = datetime.datetime.utcnow()

            return await self.update(post, auto_commit=True)

Specific exceptions provide clear error handling.

Hooks and Callbacks
-------------------

Extend behavior with hooks:

.. code-block:: python

    class PostService(SQLAlchemyAsyncRepositoryService[Post]):
        repository_type = PostRepository

        async def create(self, data: ModelDictT[Post], **kwargs) -> Post:
            """Create with pre/post hooks."""
            # Pre-creation hook
            await self._before_create(data)

            # Create operation
            post = await super().create(data, **kwargs)

            # Post-creation hook
            await self._after_create(post)

            return post

        async def _before_create(self, data: ModelDictT[Post]) -> None:
            """Hook called before creation."""
            # Validate business rules
            # Send notifications
            # Log operations
            pass

        async def _after_create(self, post: Post) -> None:
            """Hook called after creation."""
            # Index in search engine
            # Send webhooks
            # Update caches
            pass

Hooks separate concerns and enable extensibility.

Technical Constraints
=====================

Service Transaction Boundaries
-------------------------------

Services should not manage session lifecycle:

.. code-block:: python

    # ✅ Correct - session managed externally
    async with AsyncSession(engine) as session:
        post_service = PostService(session=session)
        author_service = AuthorService(session=session)

        async with session.begin():
            author = await author_service.create(author_data)
            post = await post_service.create(post_data)
            # Transaction committed here

    # ❌ Incorrect - service manages session
    class PostService:
        async def create_with_session(self, data):
            async with AsyncSession(engine) as session:
                # Don't create sessions in services
                pass

Services receive sessions, they don't create them.

Override Method Signatures
---------------------------

Overridden methods must match parent signatures:

.. code-block:: python

    # ✅ Correct - matches parent signature
    async def create(self, data: ModelDictT[Post], **kwargs) -> Post:
        # Custom logic
        return await super().create(data, **kwargs)

    # ❌ Incorrect - signature mismatch
    async def create(self, data: dict) -> Post:
        # Missing **kwargs, return type too specific
        pass

Maintain signature compatibility for framework integration.

Circular Service Dependencies
------------------------------

Avoid circular dependencies between services:

.. code-block:: python

    # ❌ Incorrect - circular dependency
    class PostService:
        def __init__(self, session, author_service):
            self.author_service = author_service  # PostService depends on AuthorService

    class AuthorService:
        def __init__(self, session, post_service):
            self.post_service = post_service  # AuthorService depends on PostService

    # ✅ Correct - use coordinator service
    class BlogService:
        def __init__(self, session):
            self.post_service = PostService(session=session)
            self.author_service = AuthorService(session=session)
            # BlogService coordinates both

Use coordinator services to break circular dependencies.

Next Steps
==========

With service patterns in place, explore framework integration.

Related Topics
==============

- :doc:`../frameworks/index` - Litestar, FastAPI, Flask integration
- :doc:`basics` - Service fundamentals
- :doc:`schemas` - Schema validation and transformation
- :doc:`../repositories/advanced` - Advanced repository patterns
