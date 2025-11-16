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

    class PostService(SQLAlchemyAsyncRepositoryService[Post, PostRepository]):
        """Post service with tag handling."""

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

    class PostService(SQLAlchemyAsyncRepositoryService[Post, PostRepository]):
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

Multi-Model Coordination
=========================

Services handle relationships across models using UniqueMixin and model instance manipulation:

.. code-block:: python

    from uuid import uuid4
    from advanced_alchemy import service
    from advanced_alchemy.service import SQLAlchemyAsyncRepositoryService
    from advanced_alchemy.utils.text import slugify

    class TeamService(SQLAlchemyAsyncRepositoryService[Team, TeamRepository]):
        """Team service handling owner and tag relationships."""

        repository_type = TeamRepository
        match_fields = ["name"]

        async def to_model_on_create(self, data: service.ModelDictT[Team]) -> service.ModelDictT[Team]:
            """Create team with owner and tags."""
            if service.is_dict(data):
                # Extract relationship data
                owner_id = data.pop("owner_id", None)
                tag_names = data.pop("tags", [])
                data["id"] = data.get("id", uuid4())

                # Convert to model instance
                data = await super().to_model(data)

                # Handle tags using UniqueMixin (get or create)
                if tag_names:
                    data.tags.extend([
                        await Tag.as_unique_async(
                            self.repository.session,
                            name=tag_name,
                            slug=slugify(tag_name)
                        )
                        for tag_name in tag_names
                    ])

                # Add owner as team member
                if owner_id:
                    data.members.append(
                        TeamMember(
                            user_id=owner_id,
                            role=TeamRoles.ADMIN,
                            is_owner=True
                        )
                    )

            return data

This pattern:

- Extracts relationship data from input using ``pop()``
- Converts to model instance with ``await super().to_model(data)``
- Uses ``UniqueMixin.as_unique_async()`` for get-or-create pattern
- Manipulates relationships directly on model instance

Implementation Patterns
=======================

Service Composition
-------------------

Compose services for complex operations. When using framework dependency injection, services receive sessions:

.. code-block:: python

    from sqlalchemy.ext.asyncio import AsyncSession

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

Outside frameworks, use ``.new()`` for session management:

.. code-block:: python

    from advanced_alchemy.config import SQLAlchemyAsyncConfig

    class AnalyticsService:
        """Analytics service using .new() for session management."""

        def __init__(self, config: SQLAlchemyAsyncConfig):
            self.config = config

        async def get_author_stats(self, author_id: int) -> dict:
            """Get comprehensive author statistics."""
            async with AuthorService.new(config=self.config) as author_service, \
                       PostService.new(config=self.config) as post_service:
                author = await author_service.get(author_id)
                posts = await post_service.list(Post.author_id == author_id)

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

to_model Hooks
--------------

Override ``to_model_on_create``, ``to_model_on_update``, and ``to_model_on_upsert`` to transform data before model creation:

Basic Pattern
~~~~~~~~~~~~~

.. code-block:: python

    from advanced_alchemy.service import SQLAlchemyAsyncRepositoryService, schema_dump, is_dict
    from advanced_alchemy.service.typing import ModelDictT

    class UserService(SQLAlchemyAsyncRepositoryService[User]):

        async def to_model_on_create(self, data: ModelDictT[User]) -> ModelDictT[User]:
            """Transform data before creating user."""
            data = schema_dump(data)  # Convert schema to dict
            # Custom transformation logic
            return data

All ``to_model_on_*`` hooks receive ``ModelDictT`` (schema or dict) and return ``ModelDictT``.

Field Extraction
~~~~~~~~~~~~~~~~

Extract fields from input and transform:

.. code-block:: python

    from advanced_alchemy import service

    class UserService(SQLAlchemyAsyncRepositoryService[User]):

        async def to_model_on_create(self, data: service.ModelDictT[User]) -> service.ModelDictT[User]:
            """Hash password before creating user."""
            data = service.schema_dump(data)
            if service.is_dict(data) and (password := data.pop("password", None)) is not None:
                data["hashed_password"] = await hash_password(password)
            return data

Use ``data.pop()`` to extract and remove fields from input.

Conditional Field Population
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Generate fields conditionally:

.. code-block:: python

    class TagService(SQLAlchemyAsyncRepositoryService[Tag]):

        async def to_model_on_create(self, data: service.ModelDictT[Tag]) -> service.ModelDictT[Tag]:
            """Generate slug if not provided."""
            data = service.schema_dump(data)
            if service.is_dict_without_field(data, "slug"):
                data["slug"] = await self.repository.get_available_slug(data["name"])
            return data

        async def to_model_on_update(self, data: service.ModelDictT[Tag]) -> service.ModelDictT[Tag]:
            """Regenerate slug if name changed."""
            data = service.schema_dump(data)
            if service.is_dict_without_field(data, "slug") and service.is_dict_with_field(data, "name"):
                data["slug"] = await self.repository.get_available_slug(data["name"])
            return data

Helper functions:
- ``service.is_dict(data)`` - Check if data is dict
- ``service.is_dict_with_field(data, "field")`` - Check dict has field
- ``service.is_dict_without_field(data, "field")`` - Check dict missing field

Helper Method Pattern
~~~~~~~~~~~~~~~~~~~~~

Delegate to helper methods for complex logic:

.. code-block:: python

    class UserService(SQLAlchemyAsyncRepositoryService[User]):

        async def to_model_on_create(self, data: service.ModelDictT[User]) -> service.ModelDictT[User]:
            return await self._populate_model(data)

        async def to_model_on_update(self, data: service.ModelDictT[User]) -> service.ModelDictT[User]:
            return await self._populate_model(data)

        async def _populate_model(self, data: service.ModelDictT[User]) -> service.ModelDictT[User]:
            """Shared transformation logic."""
            data = service.schema_dump(data)
            data = await self._populate_password(data)
            data = await self._populate_role(data)
            return data

        async def _populate_password(self, data: service.ModelDictT[User]) -> service.ModelDictT[User]:
            if service.is_dict(data) and (password := data.pop("password", None)) is not None:
                data["hashed_password"] = await hash_password(password)
            return data

Reuse transformation logic across create/update/upsert hooks.

Working with Model Instances
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Convert to model instance for relationship manipulation:

.. code-block:: python

    class TeamService(SQLAlchemyAsyncRepositoryService[Team]):

        async def to_model_on_create(self, data: service.ModelDictT[Team]) -> service.ModelDictT[Team]:
            if service.is_dict(data):
                owner_id = data.pop("owner_id", None)
                data = await super().to_model(data)  # Convert to Team instance

                # Now work with model relationships
                if owner_id:
                    data.members.append(
                        TeamMember(user_id=owner_id, role=TeamRoles.ADMIN, is_owner=True)
                    )
            return data

Call ``await super().to_model(data)`` to convert dict to model instance, then manipulate relationships.

Custom Hooks
------------

Add custom pre/post hooks for side effects:

.. code-block:: python

    class PostService(SQLAlchemyAsyncRepositoryService[Post, PostRepository]):

        async def create(self, data: ModelDictT[Post], **kwargs) -> Post:
            """Create with pre/post hooks."""
            await self._before_create(data)  # Pre-creation hook
            post = await super().create(data, **kwargs)
            await self._after_create(post)  # Post-creation hook
            return post

        async def _before_create(self, data: ModelDictT[Post]) -> None:
            """Validate business rules, log operations."""
            pass

        async def _after_create(self, post: Post) -> None:
            """Index in search, send webhooks, update caches."""
            pass

Custom hooks separate concerns and enable extensibility.

Query Service
=============

The ``SQLAlchemyAsyncQueryService`` provides direct SQL query execution for analytics and reporting without requiring a model.

Basic Query Service
-------------------

Execute raw SQL queries and return results:

.. code-block:: python

    from advanced_alchemy import exceptions as exc
    from advanced_alchemy import service
    from sqlalchemy import RowMapping, text

    class StatsService(service.SQLAlchemyAsyncQueryService):
        """Stats service for analytics queries."""

        async def users_by_week(self) -> list[RowMapping]:
            """Get user signup counts by week."""
            statement = text(
                """
                    select a.week, count(a.user_id) as new_users
                    from (
                        select date_trunc('week', user_account.joined_at) as week,
                               user_account.id as user_id
                        from user_account
                    ) a
                    group by a.week
                    order by a.week
                """,
            )
            with exc.wrap_sqlalchemy_exception():
                result = await self.repository.session.execute(statement)
                return list(result.mappings())

        async def current_totals(self) -> list[RowMapping]:
            """Get current total counts."""
            statement = text(
                """
                    select count(user_account.id) as total_users,
                           date_trunc('hour', current_timestamp) as as_of
                    from user_account
                    group by as_of
                """,
            )
            with exc.wrap_sqlalchemy_exception():
                result = await self.repository.session.execute(statement)
                return list(result.mappings())

This pattern:

- Extends ``SQLAlchemyAsyncQueryService`` (no model required)
- Uses ``text()`` for raw SQL queries
- Wraps queries with ``exc.wrap_sqlalchemy_exception()`` for consistent error handling
- Returns ``list[RowMapping]`` for dictionary-like result access
- Accesses session via ``self.repository.session``

Query Service Characteristics
------------------------------

``SQLAlchemyAsyncQueryService`` differs from ``SQLAlchemyAsyncRepositoryService``:

- No model type parameter (works with raw SQL)
- No CRUD operations (create, update, delete)
- Direct session access for complex queries
- Returns ``RowMapping`` instead of model instances
- Useful for analytics, reporting, and aggregations

Sample Repository and Service
==============================

Complete example showing Author and Post models with repositories and services.

Author Repository and Service
------------------------------

.. note::

    The following examples use the ``Author`` and ``Post`` models from :ref:`one_to_many_relationships`.

.. code-block:: python

    from advanced_alchemy import service
    from advanced_alchemy.repository import SQLAlchemyAsyncRepository
    from advanced_alchemy.service import SQLAlchemyAsyncRepositoryService

    class AuthorRepository(SQLAlchemyAsyncRepository[Author]):
        """Author repository with custom queries."""

        model_type = Author

        async def get_by_email(self, email: str) -> Author | None:
            """Get author by email address."""
            return await self.get_one_or_none(Author.email == email.lower())

        async def get_top_authors(self, limit: int = 10) -> list[Author]:
            """Get authors with most posts."""
            from sqlalchemy import func, select
            from sqlalchemy.orm import selectinload

            stmt = (
                select(Author)
                .join(Author.posts)
                .group_by(Author.id)
                .order_by(func.count(Post.id).desc())
                .limit(limit)
                .options(selectinload(Author.posts))
            )
            result = await self.session.execute(stmt)
            return list(result.scalars())

    class AuthorService(SQLAlchemyAsyncRepositoryService[Author, AuthorRepository]):
        """Author service with email normalization."""

        repository_type = AuthorRepository
        match_fields = ["email"]

        async def to_model_on_create(self, data: service.ModelDictT[Author]) -> service.ModelDictT[Author]:
            """Normalize email before creating author."""
            data = service.schema_dump(data)
            if service.is_dict(data) and service.is_dict_with_field(data, "email"):
                data["email"] = data["email"].lower().strip()
            return data

        async def to_model_on_update(self, data: service.ModelDictT[Author]) -> service.ModelDictT[Author]:
            """Normalize email before updating author."""
            data = service.schema_dump(data)
            if service.is_dict(data) and service.is_dict_with_field(data, "email"):
                data["email"] = data["email"].lower().strip()
            return data

Post Repository and Service
----------------------------

.. code-block:: python

    from datetime import datetime, timezone
    from uuid import uuid4
    from advanced_alchemy import service
    from advanced_alchemy.repository import SQLAlchemyAsyncRepository
    from advanced_alchemy.service import SQLAlchemyAsyncRepositoryService
    from advanced_alchemy.exceptions import ConflictError
    from advanced_alchemy.utils.text import slugify

    class PostRepository(SQLAlchemyAsyncRepository[Post]):
        """Post repository with custom queries."""

        model_type = Post

        async def get_published(self, limit: int = 10) -> list[Post]:
            """Get published posts."""
            from sqlalchemy.orm import selectinload

            return await self.list(
                Post.published == True,
                Post.published_at.is_not(None),
                order_by=[Post.published_at.desc()],
                limit=limit,
                load=[selectinload(Post.author), selectinload(Post.tags)],
            )

        async def get_by_author(self, author_id: int) -> list[Post]:
            """Get all posts by author."""
            from sqlalchemy.orm import selectinload

            return await self.list(
                Post.author_id == author_id,
                order_by=[Post.created_at.desc()],
                load=[selectinload(Post.tags)],
            )

    class PostService(SQLAlchemyAsyncRepositoryService[Post, PostRepository]):
        """Post service with tag handling and publishing logic."""

        repository_type = PostRepository
        match_fields = ["title"]
        default_load_options = [Post.author, Post.tags]

        async def to_model_on_create(self, data: service.ModelDictT[Post]) -> service.ModelDictT[Post]:
            """Handle tags when creating post."""
            if service.is_dict(data):
                # Extract and process tags
                tag_names = data.pop("tags", [])
                data["id"] = data.get("id", uuid4())

                # Convert to model instance
                data = await super().to_model(data)

                # Add tags using UniqueMixin
                if tag_names:
                    data.tags.extend([
                        await Tag.as_unique_async(
                            self.repository.session,
                            name=tag_name,
                            slug=slugify(tag_name)
                        )
                        for tag_name in tag_names
                    ])

            return data

        async def publish_post(self, post_id: int) -> Post:
            """Publish a post with timestamp."""
            post = await self.get(post_id)

            if post.published:
                raise ConflictError(f"post already published: {post_id}")

            post.published = True
            post.published_at = datetime.now(timezone.utc)

            return await self.update(post, auto_commit=True)

        async def unpublish_post(self, post_id: int) -> Post:
            """Unpublish a post."""
            post = await self.get(post_id)

            if not post.published:
                raise ConflictError(f"post not published: {post_id}")

            post.published = False
            post.published_at = None

            return await self.update(post, auto_commit=True)

Technical Constraints
=====================

Service Transaction Boundaries
-------------------------------

Services should not manage session lifecycle:

.. code-block:: python

    from advanced_alchemy.config import SQLAlchemyAsyncConfig

    # ✅ Correct - use .new() context manager
    async with PostService.new(config=config) as post_service, \
               AuthorService.new(config=config) as author_service:
        author = await author_service.create(author_data, auto_commit=True)
        post = await post_service.create(post_data, auto_commit=True)

    # ❌ Incorrect - service manages session
    class PostService:
        async def create_with_session(self, data):
            async with AsyncSession(engine) as session:
                # Don't create sessions in services
                pass

Services use ``.new()`` for session management or receive sessions from framework dependency injection.

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

    # ✅ Correct - services use repositories directly
    class PostService(SQLAlchemyAsyncRepositoryService[Post, PostRepository]):
        repository_type = PostRepository
        # Access Author data through repository queries, not AuthorService

    class AuthorService(SQLAlchemyAsyncRepositoryService[Author, AuthorRepository]):
        repository_type = AuthorRepository
        # Access Post data through repository queries, not PostService

Services should not depend on each other. Use repository queries to access related data.

Service Coordinators
--------------------

Use coordinator services to orchestrate multiple services in a single unit of work:

.. code-block:: python

    from advanced_alchemy.config import SQLAlchemyAsyncConfig

    class BlogCoordinator:
        """Coordinates author and post operations in transactions."""

        def __init__(self, config: SQLAlchemyAsyncConfig):
            self.config = config

        async def create_author_with_posts(
            self,
            author_data: dict,
            posts_data: list[dict],
        ) -> tuple[Author, list[Post]]:
            """Create author and their posts in single transaction."""
            # Services manage session lifecycle with .new()
            async with AuthorService.new(config=self.config) as author_service, \
                       PostService.new(config=self.config) as post_service:
                # Create author
                author = await author_service.create(author_data, auto_commit=True)

                # Create posts linked to author
                posts = []
                for post_data in posts_data:
                    post_data["author_id"] = author.id
                    post = await post_service.create(post_data, auto_commit=True)
                    posts.append(post)

                return author, posts

Coordinator characteristics:

- Uses ``.new()`` context manager for proper session handling
- Orchestrates multiple services in one transaction
- Contains cross-service business logic
- Ensures data consistency across services
- Does not duplicate service methods

Next Steps
==========

With service patterns in place, explore framework integration.

Related Topics
==============

- :doc:`../frameworks/index` - Litestar, FastAPI, Flask integration
- :doc:`basics` - Service fundamentals
- :doc:`schemas` - Schema validation and transformation
- :doc:`../repositories/advanced` - Advanced repository patterns
