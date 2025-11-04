# Guide: Repository Pattern

The Repository Pattern is a core concept in `advanced-alchemy` that mediates between the domain and data mapping layers using a collection-like interface for accessing domain objects. It decouples the business logic from the data access layer, making the application more modular, testable, and maintainable.

## Core Implementations

`advanced-alchemy` provides two primary repository implementations:

-   `SQLAlchemyAsyncRepository`: For use in asynchronous applications (e.g., with `asyncio`).
-   `SQLAlchemySyncRepository`: For use in synchronous applications.

Both implementations offer the same API, with the only difference being that the methods of `SQLAlchemyAsyncRepository` are `async` and must be awaited.

## Instantiation

To use a repository, you need to create a class that inherits from either the async or sync base repository and provide a SQLAlchemy model as a generic type. You must also provide a SQLAlchemy session instance.

### Async Repository Example

```python
from advanced_alchemy.repository import SQLAlchemyAsyncRepository
from sqlalchemy.ext.asyncio import AsyncSession
from .my_models import MyModel

class MyRepository(SQLAlchemyAsyncRepository[MyModel]):
    """My repository."""

    model_type = MyModel

# Instantiate with a session
async_session: AsyncSession = ...  # Get your session from your engine
repo = MyRepository(session=async_session)
```

### Sync Repository Example

```python
from advanced_alchemy.repository import SQLAlchemySyncRepository
from sqlalchemy.orm import Session
from .my_models import MyModel

class MyRepository(SQLAlchemySyncRepository[MyModel]):
    """My repository."""

    model_type = MyModel

# Instantiate with a session
sync_session: Session = ...  # Get your session from your engine
repo = MyRepository(session=sync_session)
```

## Core Methods

The repository provides a rich set of methods for CRUD (Create, Read, Update, Delete) operations.

### Creating Data

-   `add(data: ModelT) -> ModelT`: Adds a new model instance to the database.
-   `add_many(data: list[ModelT]) -> list[ModelT]`: Adds multiple model instances in a single transaction.

**Example (Async):**

```python
new_user = User(name="John Doe", email="john.doe@example.com")
created_user = await user_repo.add(new_user)
```

### Reading Data

-   `get(item_id: Any) -> ModelT`: Retrieves a model instance by its primary key. Raises `NotFoundError` if not found.
-   `get_one(**kwargs: Any) -> ModelT`: Retrieves a single model instance matching the given keyword arguments. Raises `NotFoundError` if not found.
-   `get_one_or_none(**kwargs: Any) -> ModelT | None`: Retrieves a single model instance or `None` if not found.
-   `list(*filters, **kwargs) -> list[ModelT]`: Retrieves a list of model instances that match the given filters and keyword arguments.
-   `count(*filters, **kwargs) -> int`: Returns the total count of model instances matching the filters.
-   `list_and_count(*filters, **kwargs) -> tuple[list[ModelT], int]`: Returns a tuple containing the list of model instances and the total count in a single operation.

**Example (Async):**

```python
# Get user by ID
user = await user_repo.get(1)

# Get one user by email
user = await user_repo.get_one(email="john.doe@example.com")

# List all users
users = await user_repo.list()

# List and count active users
active_users, total = await user_repo.list_and_count(is_active=True)
```

### Updating Data

-   `update(data: ModelT) -> ModelT`: Updates an existing model instance. The instance must have its primary key attribute set.
-   `update_many(data: list[ModelT]) -> list[ModelT]`: Updates multiple model instances.
-   `upsert(data: ModelT) -> ModelT`: Updates a model instance if it exists, or creates it if it does not.

**Example (Async):**

```python
user_to_update = await user_repo.get(1)
user_to_update.name = "John Smith"
updated_user = await user_repo.update(user_to_update)
```

### Deleting Data

-   `delete(item_id: Any) -> ModelT`: Deletes a model instance by its primary key.
-   `delete_many(item_ids: list[Any]) -> list[ModelT]`: Deletes multiple model instances by their primary keys.

**Example (Async):**

```python
# Delete user by ID
deleted_user = await user_repo.delete(1)
```

## Filtering

The `list`, `get_one`, `get_one_or_none`, and `count` methods accept both keyword arguments for simple equality filters and more advanced filter objects for complex queries.

**Keyword Argument Filtering:**

```python
# Finds users where name = 'John Doe' AND is_active = True
users = await user_repo.list(name="John Doe", is_active=True)
```

**Advanced Filtering:**

`advanced-alchemy` provides special filter objects for more complex queries like `CollectionFilter`, `SearchFilter`, `OrderBy`, and `LimitOffset`.

```python
from advanced-alchemy.filters import LimitOffset, OrderBy

# Get the first 10 users, ordered by name descending
users = await user_repo.list(
    OrderBy("name", "desc"),
    LimitOffset(limit=10, offset=0),
)
```

## Adding Custom Repository Methods

While the built-in methods and filters cover many use cases, you will often need to write custom, complex queries. The recommended pattern is to add new methods to your repository subclass. This keeps your data access logic cleanly encapsulated.

This is useful for:
-   Queries with complex joins between multiple tables.
-   Applying specific loading strategies (e.g., `selectinload`, `joinedload`) for nested relationships.
-   Aggregations and other database functions.

**Example: Get Workspaces for a Specific User**

Imagine you want to retrieve all workspaces that a specific user belongs to. This requires a join through a `WorkspaceMember` association table.

```python
from sqlalchemy import select
from sqlalchemy.orm import joinedload
from advanced_alchemy.repository import SQLAlchemyAsyncRepository
from . import models as m

class WorkspaceRepository(SQLAlchemyAsyncRepository[m.Workspace]):
    """Workspace Repository."""
    model_type = m.Workspace

    async def get_user_workspaces(self, user_id: UUID) -> tuple[list[m.Workspace], int]:
        """Get all workspaces for a user, with members and their users pre-loaded."""
        
        # Create a custom statement with a join and specific loading options
        statement = (
            select(self.model_type)
            .join(m.WorkspaceMember, onclause=self.model_type.id == m.WorkspaceMember.workspace_id)
            .where(m.WorkspaceMember.user_id == user_id)
            .options(
                joinedload(m.Workspace.members).joinedload(m.WorkspaceMember.user)
            )
        )
        
        # Use the built-in list_and_count to execute the custom statement
        return await self.list_and_count(statement=statement)

```

By adding custom methods to your repository, you can handle any data access requirement while still benefiting from the structure and convenience of the base repository.
