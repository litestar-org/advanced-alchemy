# Guide: Advanced Many-to-Many Relationships

Handling many-to-many relationships is a common requirement in web applications. This guide demonstrates an advanced, robust pattern for managing such relationships using `advanced-alchemy`, focusing on a real-world example: a `Workspace` that can have multiple `Tag`s.

This pattern leverages several features:
-   A dedicated service for the "many" side of the relationship (`TagService`).
-   The `UniqueMixin` to efficiently create or retrieve existing tags.
-   Overriding the `create` and `update` methods on the "owning" service (`WorkspaceService`) to orchestrate the relationship changes.

## 1. The "Many" Side: The `Tag` Model and Service

First, define the model for the item you'll be linking to many things. In this case, a `Tag`.

### `Tag` Model

This model uses `UniqueMixin` to ensure that we never create duplicate tags with the same name. It also uses `SlugKey` to generate a URL-friendly slug.

```python
from sqlalchemy import ColumnElement
from advanced_alchemy.mixins import UniqueMixin, SlugKey, UUIDAuditBase
from advanced_alchemy.utils.text import slugify

class Tag(UUIDAuditBase, SlugKey, UniqueMixin):
    __tablename__ = "tag"
    name: Mapped[str]

    @classmethod
    def unique_hash(cls, name: str, **kwargs) -> str:
        return slugify(name)

    @classmethod
    def unique_filter(cls, name: str, **kwargs) -> ColumnElement[bool]:
        return cls.slug == slugify(name)
```

### `Tag` Service

The service for `Tag` is straightforward. It uses the `SQLAlchemyAsyncSlugRepository` and implements the `to_model_on_create` hook to automatically generate a slug from the tag's name if one isn't provided.

```python
from advanced_alchemy import service, repository
from . import models as m

class TagService(service.SQLAlchemyAsyncRepositoryService[m.Tag]):
    class Repo(repository.SQLAlchemyAsyncSlugRepository[m.Tag]):
        model_type = m.Tag
    
    repository_type = Repo

    async def to_model_on_create(self, data: service.ModelDictT[m.Tag]) -> service.ModelDictT[m.Tag]:
        if "name" in data and "slug" not in data and isinstance(data, dict):
            data["slug"] = await self.repository.get_available_slug(data["name"])
        return data
```

## 2. The "Owning" Side: The `Workspace` Service

The `WorkspaceService` is where the main orchestration logic resides. We will override its `create` and `update` methods to handle the association with tags.

### Overriding `create`

The `create` method will accept a list of tag names (strings) in its data dictionary.

**The Pattern:**
1.  In the `create` method, `pop` the list of tag names from the incoming data dictionary.
2.  Create the base `Workspace` model instance by calling `await self.to_model(data, "create")`.
3.  Iterate through the tag names. For each name, use the `Tag.as_unique_async()` method. This is a highly efficient way to get the `Tag` object if it already exists, or create it if it doesn't, all within the same session.
4.  Append the retrieved/created `Tag` objects to the `workspace.tags` relationship attribute.
5.  Finally, call `await super().create(db_obj)` to persist the `Workspace` and all its new relationships in a single transaction.

```python
class WorkspaceService(service.SQLAlchemyAsyncRepositoryService[m.Workspace, WorkspaceRepository]):
    # ...

    async def create(self, data: service.ModelDictT[m.Workspace]) -> m.Workspace:
        # 1. Pop the list of tag names
        tags_to_add = data.pop("tags", []) if isinstance(data, dict) else []

        # 2. Create the base workspace model
        db_obj = await self.to_model(data, "create")

        # 3 & 4. Get or create tags and append them
        if tags_to_add:
            db_obj.tags.extend(
                [
                    await m.Tag.as_unique_async(self.repository.session, name=tag_name)
                    for tag_name in tags_to_add
                ]
            )
        
        # 5. Persist everything
        return await super().create(db_obj)
```

### Overriding `update`

The `update` method is slightly more complex, as it needs to handle adding new tags, removing old ones, and leaving existing associations untouched.

**The Pattern:**
1.  `pop` the new list of tag names from the data dictionary.
2.  Convert the incoming data to a model instance. This instance will be merged into the session, so it will have the existing `tags` relationship loaded.
3.  Determine which tags to add and which to remove by comparing the incoming list of names with the names of tags already on the model.
4.  Remove the `Tag` objects that are no longer needed from the `workspace.tags` list.
5.  Use `Tag.as_unique_async()` to get/create the new tags and append them.
6.  Call `await super().update(...)` to save the changes.

```python
class WorkspaceService(service.SQLAlchemyAsyncRepositoryService[m.Workspace, WorkspaceRepository]):
    # ...

    async def update(self, data: service.ModelDictT[m.Workspace], item_id: Any) -> m.Workspace:
        # 1. Pop the new list of tag names
        tags_updated = data.pop("tags", []) if isinstance(data, dict) else []

        # 2. Get the model instance with current relationships
        data["id"] = item_id
        db_obj = await self.to_model(data, "update")

        # 3. Determine changes
        existing_tag_names = {tag.name for tag in db_obj.tags}
        tags_to_add_names = [name for name in tags_updated if name not in existing_tag_names]
        tags_to_remove = [tag for tag in db_obj.tags if tag.name not in tags_updated]

        # 4. Remove old tags
        for tag in tags_to_remove:
            db_obj.tags.remove(tag)

        # 5. Add new tags
        if tags_to_add_names:
            db_obj.tags.extend(
                [
                    await m.Tag.as_unique_async(self.repository.session, name=tag_name)
                    for tag_name in tags_to_add_names
                ]
            )

        # 6. Persist changes
        return await super().update(item_id=item_id, data=db_obj)
```

This pattern provides a clean, efficient, and robust way to manage many-to-many relationships within the service layer.
