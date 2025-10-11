# Repository-Service Pattern

Advanced Alchemy repository-service pattern reference. See [AGENTS.md](/home/cody/code/litestar/advanced-alchemy/AGENTS.md) for complete conventions.

## Core Pattern

**Always: Service → Repository → Model**

## Basic Service Structure

```python
from __future__ import annotations

from advanced_alchemy import repository, service
from app.db import models as m


class TagService(service.SQLAlchemyAsyncRepositoryService[m.Tag]):
    """Basic service with slug generation."""

    class Repo(repository.SQLAlchemyAsyncSlugRepository[m.Tag]):
        model_type = m.Tag

    repository_type = Repo
    match_fields = ["name"]

    async def to_model_on_create(self, data: service.ModelDictT[m.Tag]) -> service.ModelDictT[m.Tag]:
        data = service.schema_dump(data)
        if service.is_dict_without_field(data, "slug"):
            data["slug"] = await self.repository.get_available_slug(data["name"])
        return data
```

## Service Hooks

### Data Transformation Hooks

```python
# Called before create
async def to_model_on_create(self, data: service.ModelDictT[m.User]) -> service.ModelDictT[m.User]:
    data = service.schema_dump(data)
    # Hash passwords, generate slugs, set defaults
    return data

# Called before update
async def to_model_on_update(self, data: service.ModelDictT[m.User]) -> service.ModelDictT[m.User]:
    data = service.schema_dump(data)
    # Update slugs, validate permissions
    return data

# Called before upsert (insert or update based on match_fields)
async def to_model_on_upsert(self, data: service.ModelDictT[m.User]) -> service.ModelDictT[m.User]:
    data = service.schema_dump(data)
    return data
```

## Service Patterns

### Password Hashing

```python
class UserService(service.SQLAlchemyAsyncRepositoryService[m.User]):
    class Repo(repository.SQLAlchemyAsyncRepository[m.User]):
        model_type = m.User

    repository_type = Repo
    match_fields = ["email"]

    async def to_model_on_create(self, data: service.ModelDictT[m.User]) -> service.ModelDictT[m.User]:
        data = service.schema_dump(data)
        return await self._populate_with_hashed_password(data)

    async def _populate_with_hashed_password(self, data: service.ModelDictT[m.User]) -> service.ModelDictT[m.User]:
        if service.is_dict(data) and (password := data.pop("password", None)) is not None:
            data["hashed_password"] = await crypt.get_password_hash(password)
        return data

    async def authenticate(self, username: str, password: bytes | str) -> m.User:
        """Authenticate user."""
        db_obj = await self.get_one_or_none(email=username)
        if db_obj is None:
            raise PermissionDeniedException(detail="user not found or password invalid")
        if not await crypt.verify_password(password, db_obj.hashed_password):
            raise PermissionDeniedException(detail="user not found or password invalid")
        if not db_obj.is_active:
            raise PermissionDeniedException(detail="user account is inactive")
        return db_obj
```

### Relationship Management

```python
class TeamService(service.SQLAlchemyAsyncRepositoryService[m.Team]):
    class Repo(repository.SQLAlchemyAsyncSlugRepository[m.Team]):
        model_type = m.Team

    repository_type = Repo
    match_fields = ["name"]

    async def to_model_on_create(self, data: service.ModelDictT[m.Team]) -> service.ModelDictT[m.Team]:
        data = service.schema_dump(data)
        data = await self._populate_slug(data)
        return await self._populate_with_tags(data)

    async def _populate_with_tags(self, data: service.ModelDictT[m.Team]) -> service.ModelDictT[m.Team]:
        if service.is_dict(data):
            input_tags: list[str] = data.pop("tags", [])
            data = await super().to_model(data)  # Convert to model instance
            if input_tags:
                # Add tags using UniqueMixin pattern (get-or-create)
                data.tags.extend([
                    await m.Tag.as_unique_async(
                        self.repository.session,
                        name=tag_text,
                        slug=slugify(tag_text)
                    )
                    for tag_text in input_tags
                ])
        return data
```

## Repository Types

### `SQLAlchemyAsyncRepository`

Basic async CRUD repository:

```python
class UserRepo(repository.SQLAlchemyAsyncRepository[m.User]):
    model_type = m.User
```

### `SQLAlchemyAsyncSlugRepository`

Repository with slug generation:

```python
class TagRepo(repository.SQLAlchemyAsyncSlugRepository[m.Tag]):
    model_type = m.Tag

# Methods:
# - get_available_slug(value: str) -> str
```

### Sync Variants

- `SQLAlchemySyncRepository` - Sync CRUD repository
- `SQLAlchemySyncSlugRepository` - Sync repository with slugs

## Service Methods

### Query Methods

```python
# Get single (raises NotFoundError if not found)
user = await service.get_one(id=user_id)

# Get single or None
user = await service.get_one_or_none(email="user@example.com")

# List
users = await service.list(is_active=True)

# List with count (pagination)
users, total = await service.list_and_count(is_active=True)

# Exists
exists = await service.exists(email="user@example.com")

# Count
count = await service.count(is_active=True)
```

### CRUD Methods

```python
# Create
user = await service.create({"email": "user@example.com", "name": "John"})

# Create many
users = await service.create_many([{...}, {...}])

# Update
user = await service.update({"email": "new@example.com"}, item_id=user_id)

# Upsert (insert or update based on match_fields)
user = await service.upsert({"email": "user@example.com", "name": "John"})

# Delete
await service.delete(user_id)

# Delete many
await service.delete_many([id1, id2, id3])
```

## Helper Utilities

```python
# Normalize input (DTOs, Pydantic, dicts)
data = service.schema_dump(data)

# Check if dict
if service.is_dict(data):
    value = data.get("key")

# Check if dict has field
if service.is_dict_with_field(data, "email"):
    email = data["email"]

# Check if dict missing field
if service.is_dict_without_field(data, "slug"):
    data["slug"] = generate_slug()
```

## Anti-Patterns

### ❌ Don't Bypass Repository

```python
# Wrong - don't use session directly in service
class UserService(service.SQLAlchemyAsyncRepositoryService[m.User]):
    async def create_user(self, data: dict[str, Any]) -> m.User:
        user = m.User(**data)
        self.repository.session.add(user)  # ❌ Wrong
        await self.repository.session.flush()
        return user
```

### ✅ Use Repository Methods

```python
# Correct
class UserService(service.SQLAlchemyAsyncRepositoryService[m.User]):
    async def create_user(self, data: dict[str, Any]) -> m.User:
        return await self.create(data)  # ✅ Correct
```

### ❌ Don't Put Business Logic in Repository

```python
# Wrong - business logic in repository
class UserRepository(repository.SQLAlchemyAsyncRepository[m.User]):
    async def authenticate(self, email: str, password: str) -> m.User:  # ❌ Wrong
        user = await self.get_one_or_none(email=email)
        if not verify_password(password, user.hashed_password):
            raise PermissionDeniedException()
        return user
```

### ✅ Business Logic in Service

```python
# Correct - business logic in service
class UserService(service.SQLAlchemyAsyncRepositoryService[m.User]):
    async def authenticate(self, email: str, password: str) -> m.User:  # ✅ Correct
        user = await self.get_one_or_none(email=email)
        if not user or not await crypt.verify_password(password, user.hashed_password):
            raise PermissionDeniedException(detail="invalid credentials")
        return user
```

## Testing Services

```python
import pytest
from advanced_alchemy.repository.memory import SQLAlchemyAsyncMockRepository


@pytest.fixture
async def user_service(in_memory_session):
    """User service with in-memory repository."""
    class UserRepo(SQLAlchemyAsyncMockRepository[m.User]):
        model_type = m.User

    repo = UserRepo(session=in_memory_session)
    return UserService(repository=repo)


async def test_create_user(user_service):
    user = await user_service.create({"email": "test@example.com", "name": "Test"})
    assert user.email == "test@example.com"
```

## See Also

- [Type Hints Guide](type-hints.md)
- [Error Handling Guide](error-handling.md)
- [Litestar Playbook](../quick-reference/litestar-playbook.md)
- [Testing Guide](../testing/integration.md)
