======
Basics
======

Services provide business logic abstraction and wrap repositories for higher-level operations.

Prerequisites
=============

Understanding of :doc:`../repositories/basics` recommended.

Understanding Services
======================

Services sit between your application's API layer and the database, providing:

- Input validation
- Business rule enforcement
- Data transformation
- Multi-repository coordination
- Consistent error handling

While repositories handle CRUD operations, services handle domain logic.

Basic Service Pattern
=====================

Creating a service for the Post model:

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

Service configuration:

- Generic type parameter ``[Post]`` specifies the model
- ``repository_type`` specifies the repository class
- Inherits CRUD operations from base service

Basic CRUD Operations
=====================

Create
------

Creating records with validation:

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

The service:

- Validates input using Pydantic schema
- Creates database record via repository
- Returns validated response schema

Read
----

Retrieving records:

.. code-block:: python

    async def get_post(
        post_service: PostService,
        post_id: int,
    ) -> PostResponse:
        """Get a post by ID."""
        post = await post_service.get(post_id)
        return post_service.to_schema(post, schema_type=PostResponse)

    async def list_posts(
        post_service: PostService,
    ) -> List[PostResponse]:
        """List all posts."""
        posts = await post_service.list()
        return post_service.to_schema(posts, schema_type=PostResponse)

Methods available:

- ``get(item_id)`` - Get single record by ID
- ``get_one(*filters)`` - Get single record by filters
- ``list(*filters, **kwargs)`` - List multiple records

Update
------

Updating records:

.. code-block:: python

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

The service:

- Validates input schema
- Updates database record
- Returns updated response schema

Delete
------

Deleting records:

.. code-block:: python

    async def delete_post(
        post_service: PostService,
        post_id: int,
    ) -> None:
        """Delete a post."""
        await post_service.delete(
            post_id,
            auto_commit=True,
        )

Schema Conversion
=================

Services provide bidirectional schema conversion:

to_schema
---------

Convert model to schema:

.. code-block:: python

    # Single record
    post_data = post_service.to_schema(post, schema_type=PostResponse)

    # Multiple records
    posts_data = post_service.to_schema(posts, schema_type=PostResponse)

to_model
--------

Convert schema to model (automatic in CRUD methods):

.. code-block:: python

    # Automatically called by create/update methods
    post = await post_service.create(PostCreate(title="Test", content="Content"))

    # Manual conversion (advanced usage)
    post_model = await post_service.to_model(post_create_data, operation="create")

Implementation Patterns
=======================

Repository Wrapping
-------------------

Services wrap repository operations:

.. code-block:: python

    class PostService(SQLAlchemyAsyncRepositoryService[Post]):
        repository_type = PostRepository

        async def get_published_posts(self) -> List[Post]:
            """Get published posts using repository."""
            return await self.repository.list(
                Post.published == True,
                Post.published_at.isnot(None)
            )

Services access repositories via ``self.repository``.

Dependency Injection
--------------------

Services receive session via dependency injection:

.. code-block:: python

    # Litestar example
    from litestar import get
    from litestar.di import Provide

    async def provide_post_service(db_session: AsyncSession) -> PostService:
        return PostService(session=db_session)

    @get("/posts")
    async def list_posts(post_service: PostService) -> List[PostResponse]:
        posts = await post_service.list()
        return post_service.to_schema(posts, schema_type=PostResponse)

    app = Litestar(
        route_handlers=[list_posts],
        dependencies={"post_service": Provide(provide_post_service)}
    )

Framework integration handles service instantiation.

Sync Services
-------------

For synchronous applications, use sync service:

.. code-block:: python

    from advanced_alchemy.service import SQLAlchemySyncRepositoryService
    from sqlalchemy.orm import Session

    class PostService(SQLAlchemySyncRepositoryService[Post]):
        """Sync service for posts."""
        repository_type = PostRepository

    def create_post(db_session: Session, data: PostCreate) -> Post:
        post_service = PostService(session=db_session)
        return post_service.create(data, auto_commit=True)

Sync services have the same API as async services, without ``await``.

Technical Constraints
=====================

Session Management
------------------

Services do not manage session lifecycle:

.. code-block:: python

    # ✅ Correct - session managed externally
    async with AsyncSession(engine) as session:
        post_service = PostService(session=session)
        post = await post_service.create(data, auto_commit=True)
        # Session closes here

    # ❌ Incorrect - service doesn't close session
    post_service = PostService(session=session)
    post = await post_service.create(data, auto_commit=True)
    # Session remains open, must be closed manually

Always manage session lifecycle outside services.

Schema Compatibility
--------------------

Schemas must support SQLAlchemy models:

.. code-block:: python

    # ✅ Correct - Pydantic with from_attributes
    class PostResponse(BaseModel):
        id: int
        title: str

        model_config = {"from_attributes": True}

    # ❌ Incorrect - missing from_attributes
    class PostResponse(BaseModel):
        id: int
        title: str
        # Will fail when converting from SQLAlchemy model

Pydantic models require ``model_config = {"from_attributes": True}`` for SQLAlchemy model conversion.

Auto-Commit Behavior
--------------------

``auto_commit`` commits transactions immediately:

.. code-block:: python

    # ✅ Correct - auto_commit for single operation
    post = await post_service.create(data, auto_commit=True)
    # Transaction committed immediately

    # ✅ Correct - manual transaction for multiple operations
    async with session.begin():
        post = await post_service.create(post_data)
        tag = await tag_service.create(tag_data)
        # Transaction committed here

Use ``auto_commit=False`` for multi-operation transactions.

Next Steps
==========

Learn about schema validation in :doc:`schemas`.

Related Topics
==============

- :doc:`schemas` - Pydantic/msgspec integration
- :doc:`advanced` - Complex operations and hooks
- :doc:`../repositories/basics` - Repository layer
