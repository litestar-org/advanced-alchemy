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
- Automatic schema validation and transformation

Basic Service Usage
-------------------

Let's build upon our blog example by creating services for posts and tags:

.. code-block:: python

    from advanced_alchemy.service import SQLAlchemyAsyncRepositoryService
    from pydantic import BaseModel
    from datetime import datetime
    from typing import Optional, List
    from uuid import UUID

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
        published_at: Optional[datetime]
        created_at: datetime
        updated_at: datetime
        tags: List["TagResponse"]

        model_config = {"from_attributes": True}

    class PostService(SQLAlchemyAsyncRepositoryService[Post]):
        """Service for managing blog posts with automatic schema validation."""

        repository_type = PostRepository

Service Operations
------------------

Services provide high-level methods for common operations:

.. code-block:: python

    async def create_post_with_tags(
        post_service: PostService,
        data: PostCreate,
    ) -> PostResponse:
        """Create a post with associated tags."""
        # Service automatically validates input using PostCreate schema
        post = await post_service.create(
            data,
            auto_commit=True,
        )
        return post_service.to_schema(post)

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
        return post_service.to_schema(post)

Complex Operations
-------------------

Services can handle complex business logic involving multiple repositories:

.. code-block:: python

    class PostService(SQLAlchemyAsyncRepositoryService[Post]):
        """Higher-level service coordinating posts and tags."""

        default_load_options = [Post.tags]
        repository_type = PostRepository
        match_fields = ["name"]

        def __init__(self, **repo_kwargs: Any) -> None:
            self.repository: PostRepository = self.repository_type(**repo_kwargs)
            self.model_type = self.repository.model_type


        async def create(
            self,
            data: ModelDictT[Post],
            *,
            auto_commit: bool | None = None,
            auto_expunge: bool | None = None,
            auto_refresh: bool | None = None,
            error_messages: ErrorMessages | None | EmptyType = Empty,
        ) -> Post:
            """Create a new post."""
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
            await super().create(
                data=data,
                auto_commit=auto_commit,
                auto_expunge=True,
                auto_refresh=False,
                error_messages=error_messages,
            )
            return data

        async def update(
            self,
            data: ModelDictT[Post],
            item_id: Any | None = None,
            *,
            id_attribute: str | InstrumentedAttribute[Any] | None = None,
            attribute_names: Iterable[str] | None = None,
            with_for_update: bool | None = None,
            auto_commit: bool | None = None,
            auto_expunge: bool | None = None,
            auto_refresh: bool | None = None,
            error_messages: ErrorMessages | None | EmptyType = Empty,
            load: LoadSpec | None = None,
            execution_options: dict[str, Any] | None = None,
        ) -> Post:
            """Wrap repository update operation.

            Returns:
                Updated representation.
            """
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
                attribute_names=attribute_names,
                id_attribute=id_attribute,
                load=load,
                execution_options=execution_options,
                with_for_update=with_for_update,
                auto_commit=auto_commit,
                auto_expunge=auto_expunge,
                auto_refresh=auto_refresh,
                error_messages=error_messages,
            )


        async def publish_post(
            self,
            post_id: int,
            publish: bool = True,
        ) -> PostResponse:
            """Publish or unpublish a post with timestamp."""
            data = PostUpdate(
                published=publish,
                published_at=datetime.utcnow() if publish else None,
            )
            post = await self.post_service.update(
                item_id=post_id,
                data=data,
                auto_commit=True,
            )
            return self.post_service.to_schema(post)

        async def get_trending_posts(
            self,
            days: int = 7,
            min_views: int = 100,
        ) -> List[PostResponse]:
            """Get trending posts based on view count and recency."""
            posts = await self.post_service.list(
                Post.published == True,
                Post.created_at > (datetime.utcnow() - timedelta(days=days)),
                Post.view_count >= min_views,
                order_by=[Post.view_count.desc()],
            )
            return self.post_service.to_schema(posts)

        async def to_model(self, data: ModelDictT[Post], operation: str | None = None) -> Post:
            """Convert a dictionary, Msgspec model, or Pydantic model to a Post model."""
            if (is_msgspec_struct(data) or is_pydantic_model(data)) and operation == "create" and data.slug is None:
                data.slug = await self.repository.get_available_slug(data.name)
            if (is_msgspec_struct(data) or is_pydantic_model(data)) and operation == "update" and data.slug is None:
                data.slug = await self.repository.get_available_slug(data.name)
            if is_dict(data) and "slug" not in data and operation == "create":
                data["slug"] = await self.repository.get_available_slug(data["name"])
            if is_dict(data) and "slug" not in data and "name" in data and operation == "update":
                data["slug"] = await self.repository.get_available_slug(data["name"])
            return await super().to_model(data, operation)

Framework Integration
---------------------

Services integrate seamlessly with both Litestar and FastAPI. For Litestar integration:
