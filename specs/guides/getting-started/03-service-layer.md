# Guide: Service Layer

The Service Layer in `advanced-alchemy` provides a higher-level abstraction over the Repository Pattern. It is designed to contain business logic, orchestrate repository operations, and handle data transfer objects (DTOs) or other data structures, converting them into SQLAlchemy models before passing them to the repository.

## Core Implementations

Similar to the repository, the service layer comes in two flavors:

-   `SQLAlchemyAsyncRepositoryService`: For asynchronous applications.
-   `SQLAlchemySyncRepositoryService`: For synchronous applications.

These services are generic and must be subclassed with a specific repository type.

## Purpose of the Service Layer

-   **Business Logic**: Encapsulates business rules and processes. For example, a `UserService` might handle user registration, which involves creating a user, hashing a password, and sending a welcome email.
-   **Decoupling**: It further decouples the application's entry points (e.g., API controllers) from the data access layer. Controllers talk to services, not repositories.
-   **Data Transformation**: Services are responsible for converting data from external formats (like Pydantic models, dictionaries, or DTOs) into SQLAlchemy model instances that the repository can work with. The `to_model()` method is provided for this purpose.
-   **Unit of Work**: A service method often defines a single unit of work. It can orchestrate calls to multiple repositories within a single database transaction.

## Instantiation

There are two primary ways to define a service: the standard approach, which uses a separate repository class, and a convenient shorthand for simpler cases.

### Standard Instantiation

To create a service, you first need a repository. Then, you create a service class that inherits from the appropriate base service and specifies the repository type.

#### Async Service Example

```python
from advanced_alchemy.service import SQLAlchemyAsyncRepositoryService
from .my_repositories import MyRepository  # Your repository class

class MyService(SQLAlchemyAsyncRepositoryService[MyModel, MyRepository]):
    """My service."""

    repository_type = MyRepository

# Instantiate with a session
async_session: AsyncSession = ...  # Get your session
service = MyService(session=async_session)
```

#### Sync Service Example

```python
from advanced_alchemy.service import SQLAlchemySyncRepositoryService
from .my_repositories import MyRepository  # Your repository class

class MyService(SQLAlchemySyncRepositoryService[MyModel, MyRepository]):
    """My service."""

    repository_type = MyRepository

# Instantiate with a session
sync_session: Session = ...  # Get your session
service = MyService(session=sync_session)
```

### Shorthand Instantiation (Inline Repository)

When your repository does not require any custom methods or logic, you can use a more concise shorthand by defining the repository class inline within the service. This pattern is preferable for simplicity and avoids creating unnecessary repository files.

When using this approach, you can omit the second generic type hint in the service class definition (e.g., `SQLAlchemyAsyncRepositoryService[MyModel]` instead of `SQLAlchemyAsyncRepositoryService[MyModel, MyRepository]`).

#### Async Service Shorthand Example

```python
from advanced_alchemy.repository import SQLAlchemyAsyncRepository
from advanced_alchemy.service import SQLAlchemyAsyncRepositoryService

class MyService(SQLAlchemyAsyncRepositoryService[MyModel]):
    """My service with an inline repository."""
    class Repo(SQLAlchemyAsyncRepository[MyModel]):
        """The repository is defined directly inside the service."""
        model_type = MyModel
    
    repository_type = Repo

# Instantiate with a session
async_session: AsyncSession = ...  # Get your session
service = MyService(session=async_session)
```

#### Sync Service Shorthand Example

```python
from advanced_alchemy.repository import SQLAlchemySyncRepository
from advanced_alchemy.service import SQLAlchemySyncRepositoryService

class MyService(SQLAlchemySyncRepositoryService[MyModel]):
    """My service with an inline repository."""
    class Repo(SQLAlchemySyncRepository[MyModel]):
        """The repository is defined directly inside the service."""
        model_type = MyModel

    repository_type = Repo

# Instantiate with a session
sync_session: Session = ...  # Get your session
service = MyService(session=sync_session)
```


## Service Layer Patterns

The service layer is where you implement the core logic of your application. It acts as a bridge between your application's entry points (like API endpoints) and the data access layer (repositories).

### Exposing Repository Methods

By default, the service layer directly exposes the repository's core CRUD methods (`create`, `get`, `list`, `update`, `delete`, etc.). For many simple models, you may not need to add any extra methods to your service at all.

### Implementing Custom Business Logic

For more complex scenarios, you will extend the service with custom methods. There are two common patterns for this.

#### 1. Exposing Custom Repository Methods

When you create a custom data access method on your repository (as shown in the Repository Pattern guide), you should expose it through the service. The service method typically just calls the corresponding repository method, acting as a pass-through.

**Example: Exposing `get_user_workspaces`**

```python
# In your repository:
class WorkspaceRepository(SQLAlchemyAsyncRepository[m.Workspace]):
    model_type = m.Workspace
    
    async def get_user_workspaces(self, user_id: UUID) -> tuple[list[m.Workspace], int]:
        # ... custom query logic ...
        return await self.list_and_count(statement=...)

# In your service:
class WorkspaceService(SQLAlchemyAsyncRepositoryService[m.Workspace, WorkspaceRepository]):
    repository_type = WorkspaceRepository

    async def get_user_workspaces(self, user_id: UUID) -> tuple[list[m.Workspace], int]:
        """Get all workspaces for a user."""
        # Simply call the repository's custom method
        return await self.repository.get_user_workspaces(user_id=user_id)
```

#### 2. Overriding Core Service Methods

For complex operations, especially `create` and `update`, you should override the base service methods to orchestrate your business logic. This logic might include validating data, working with multiple models, managing relationships, or calling external services.

A common pattern is:
1.  Receive a data dictionary or DTO.
2.  Pop off any data that isn't a direct field on the main model (e.g., relationship data, IDs).
3.  Call `await self.to_model(data, "create")` to build the base model instance.
4.  Use the popped data to create and attach related models.
5.  Call `await super().create(db_obj)` to persist the fully assembled object graph.

**Example: Overriding `create` for a Workspace**

```python
class WorkspaceService(SQLAlchemyAsyncRepositoryService[m.Workspace, WorkspaceRepository]):
    # ...

    async def create(self, data: ModelDictT[m.Workspace]) -> m.Workspace:
        """Create a new workspace, assigning an owner and tags."""
        
        # 1. Pop off related data
        owner_id = data.pop("owner_id")
        tags_to_add = data.pop("tags", [])

        # 2. Create the base model instance
        db_obj = await self.to_model(data, "create")

        # 3. Create and attach related models
        db_obj.members.append(m.WorkspaceMember(user_id=owner_id, role="admin", is_owner=True))
        
        db_obj.tags.extend(
            [
                await m.Tag.as_unique_async(self.repository.session, name=tag_name)
                for tag_name in tags_to_add
            ]
        )

        # 4. Call the original `create` method to save everything
        return await super().create(db_obj)
```

### Data Transformation and Business Logic Hooks

A key responsibility of the service layer is to transform incoming data into SQLAlchemy model instances. This is handled by the `to_model()` method and its associated hooks.

#### The `to_model()` Method

The `create`, `update`, and `upsert` methods accept a generic `ModelDictT`, which can be a dictionary, a Pydantic model, a msgspec struct, or other data structures. The service's `to_model()` method is responsible for converting this data into a SQLAlchemy model instance.

#### Business Logic with `to_model_on_<operation>` Hooks

While you can override `to_model()` directly, the preferred way to inject business logic that modifies the incoming data *before* model creation is by using these specific hooks:

-   `to_model_on_create(data: ...)`
-   `to_model_on_update(data: ...)`
-   `to_model_on_upsert(data: ...)`

These hooks are the ideal place to perform actions like hashing passwords, generating slugs, or enriching data.

**Example: Hashing Passwords in a `UserService`**

```python
from advanced_alchemy.service import SQLAlchemyAsyncRepositoryService, ModelDictT
from .my_models import User
from .security import crypt  # Your password hashing utility

class UserService(SQLAlchemyAsyncRepositoryService[User]):
    """Handles database operations for users."""

    class Repo(repository.SQLAlchemyAsyncRepository[User]):
        model_type = User

    repository_type = Repo

    async def to_model_on_create(self, data: ModelDictT[User]) -> ModelDictT[User]:
        """Called before a user model is created."""
        if "password" in data and isinstance(data, dict):
            hashed_password = await crypt.get_password_hash(data["password"])
            data["hashed_password"] = hashed_password
            del data["password"]
        return data

    async def to_model_on_update(self, data: ModelDictT[User]) -> ModelDictT[User]:
        """Called before a user model is updated."""
        if "password" in data and isinstance(data, dict):
            hashed_password = await crypt.get_password_hash(data["password"])
            data["hashed_password"] = hashed_password
            del data["password"]
        return data
```
By using these patterns, you can build a clean, powerful, and maintainable service layer that cleanly separates business logic from data access.
