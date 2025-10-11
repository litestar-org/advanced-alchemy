# Quick Reference

Advanced Alchemy patterns and code snippets. See [AGENTS.md](/home/cody/code/litestar/advanced-alchemy/AGENTS.md) for complete conventions.

## Service Patterns

### Basic Service

```python
from __future__ import annotations
from advanced_alchemy import repository, service
from app.db import models as m


class UserService(service.SQLAlchemyAsyncRepositoryService[m.User]):
    class Repo(repository.SQLAlchemyAsyncRepository[m.User]):
        model_type = m.User

    repository_type = Repo
    match_fields = ["email"]
```

### Service with Slug

```python
class TeamService(service.SQLAlchemyAsyncRepositoryService[m.Team]):
    class Repo(repository.SQLAlchemyAsyncSlugRepository[m.Team]):
        model_type = m.Team

    repository_type = Repo
    match_fields = ["name"]

    async def to_model_on_create(self, data: service.ModelDictT[m.Team]) -> service.ModelDictT[m.Team]:
        data = service.schema_dump(data)
        if service.is_dict_without_field(data, "slug") and service.is_dict_with_field(data, "name"):
            data["slug"] = await self.repository.get_available_slug(data["name"])
        return data
```

### Service with Transformation

```python
class UserService(service.SQLAlchemyAsyncRepositoryService[m.User]):
    # ... setup ...

    async def to_model_on_create(self, data: service.ModelDictT[m.User]) -> service.ModelDictT[m.User]:
        data = service.schema_dump(data)
        if service.is_dict(data) and (password := data.pop("password", None)):
            data["hashed_password"] = await hash_password(password)
        return data
```

## Models

### UUID with Audit

```python
from advanced_alchemy.base import UUIDAuditBase
from sqlalchemy.orm import Mapped, mapped_column


class User(UUIDAuditBase):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(unique=True, index=True)
    name: Mapped[str]
    is_active: Mapped[bool] = mapped_column(default=True)
```

### BigInt Model

```python
from advanced_alchemy.base import BigIntAuditBase


class Article(BigIntAuditBase):
    __tablename__ = "articles"

    title: Mapped[str]
    content: Mapped[str]
    published: Mapped[bool] = mapped_column(default=False)
```

### Model with Relationships

```python
from sqlalchemy.orm import relationship


class User(UUIDAuditBase):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(unique=True)
    posts: Mapped[list["Post"]] = relationship("Post", back_populates="author")


class Post(UUIDAuditBase):
    __tablename__ = "posts"

    title: Mapped[str]
    content: Mapped[str]
    author_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    author: Mapped["User"] = relationship("User", back_populates="posts")
```

## Query Methods

```python
# Get single (raises NotFoundError)
user = await service.get_one(id=user_id)

# Get single or None
user = await service.get_one_or_none(email="user@example.com")

# List
users = await service.list(is_active=True)

# List with count
users, total = await service.list_and_count(is_active=True)

# Exists
exists = await service.exists(email="user@example.com")

# Count
count = await service.count(is_active=True)
```

## Advanced Filters

```python
from advanced_alchemy.filters import LimitOffset, BeforeAfter, SearchFilter

users, total = await service.list_and_count(
    LimitOffset(limit=20, offset=0),
    SearchFilter(field_name="name", value="john"),
    BeforeAfter(field_name="created_at", before=end_date, after=start_date),
)
```

## Eager Loading

```python
from sqlalchemy.orm import selectinload, joinedload

# Load relationship
user = await service.get_one(
    id=user_id,
    load=[selectinload(m.User.posts)],
)

# Load multiple
user = await service.get_one(
    id=user_id,
    load=[selectinload(m.User.posts), selectinload(m.User.profile)],
)

# Joined load (many-to-one)
posts = await service.list(load=[joinedload(m.Post.author)])
```

## CRUD Operations

```python
# Create
user = await service.create({"email": "user@example.com", "name": "John"})

# Create many
users = await service.create_many([{...}, {...}])

# Update
user = await service.update({"name": "New Name"}, item_id=user_id)

# Upsert (insert or update based on match_fields)
user = await service.upsert({"email": "user@example.com", "name": "John"})

# Bulk upsert
users = await service.upsert_many([{...}, {...}])

# Delete
await service.delete(user_id)

# Delete many
await service.delete_many([id1, id2, id3])
```

## Litestar Controller

```python
from litestar import Controller, get, post, patch, delete
from litestar.di import Provide
from litestar.dto import DTOData
from uuid import UUID


async def provide_user_service(db_session: AsyncSession) -> UserService:
    return UserService(session=db_session)


class UserController(Controller):
    path = "/users"
    dependencies = {"user_service": Provide(provide_user_service)}
    return_dto = UserPublicDTO

    @get()
    async def list_users(self, user_service: UserService) -> list[m.User]:
        return await user_service.list()

    @get("/{user_id:uuid}")
    async def get_user(self, user_service: UserService, user_id: UUID) -> m.User:
        return await user_service.get_one(id=user_id)

    @post(dto=UserCreateDTO)
    async def create_user(self, user_service: UserService, data: DTOData[UserCreate]) -> m.User:
        return await user_service.create(data.as_builtins())

    @patch("/{user_id:uuid}", dto=UserUpdateDTO)
    async def update_user(self, user_service: UserService, user_id: UUID, data: DTOData[UserUpdate]) -> m.User:
        return await user_service.update(data.as_builtins(), item_id=user_id)

    @delete("/{user_id:uuid}", status_code=204)
    async def delete_user(self, user_service: UserService, user_id: UUID) -> None:
        await user_service.delete(user_id)
```

## Testing

```python
import pytest
from advanced_alchemy.repository.memory import SQLAlchemyAsyncMockRepository


@pytest.fixture
async def user_service(in_memory_session):
    class UserRepo(SQLAlchemyAsyncMockRepository[m.User]):
        model_type = m.User

    repo = UserRepo(session=in_memory_session)
    return UserService(repository=repo)


async def test_create_user(user_service):
    user = await user_service.create({"email": "test@example.com", "name": "Test"})
    assert user.email == "test@example.com"


@pytest.mark.asyncpg
async def test_user_postgres(asyncpg_engine):
    async with asyncpg_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session_factory() as session:
        service = UserService(session=session)
        user = await service.create({"email": "test@example.com", "name": "Test"})
        assert user.id is not None
```

## Error Handling

```python
from advanced_alchemy.exceptions import NotFoundError, ConflictError
from litestar.exceptions import PermissionDeniedException


class UserService(service.SQLAlchemyAsyncRepositoryService[m.User]):
    async def authenticate(self, email: str, password: str) -> m.User:
        user = await self.get_one_or_none(email=email)
        if not user:
            raise PermissionDeniedException(detail="invalid credentials")
        if not await verify_password(password, user.hashed_password):
            raise PermissionDeniedException(detail="invalid credentials")
        return user
```

## Utilities

```python
from advanced_alchemy.utils.text import slugify
from litestar.plugins.sqlalchemy import service

# Slugify
slug = slugify("Hello World!")  # "hello-world"

# Normalize input
data = service.schema_dump(input_data)

# Dict helpers
if service.is_dict(data):
    value = data.get("key")

if service.is_dict_with_field(data, "email"):
    email = data["email"]

if service.is_dict_without_field(data, "slug"):
    data["slug"] = generate_slug()
```

## Database Types

```python
from advanced_alchemy.types import JsonB, GUID, DateTimeUTC
from sqlalchemy.orm import Mapped, mapped_column


class Document(UUIDAuditBase):
    __tablename__ = "documents"

    # PostgreSQL JSONB
    metadata: Mapped[dict[str, Any]] = mapped_column(JsonB)

    # UTC datetime
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTimeUTC)
```

## Alembic

```bash
# Generate migration
alembic revision --autogenerate -m "add user table"

# Apply migrations
alembic upgrade head

# Downgrade
alembic downgrade -1

# Show current
alembic current

# Show history
alembic history
```

## Performance

### Prevent N+1

```python
# Bad - N+1 query
users = await service.list()
for user in users:
    print(user.posts)  # Triggers query per user

# Good - eager load
users = await service.list(load=[selectinload(m.User.posts)])
for user in users:
    print(user.posts)  # Already loaded
```

### Bulk Operations

```python
# Bulk create
users = await service.create_many([...])

# Bulk upsert
users = await service.upsert_many([...], match_fields=["email"])
```

### Connection Pooling

```python
config = SQLAlchemyAsyncConfig(
    connection_string="postgresql+asyncpg://...",
    pool_size=20,
    max_overflow=10,
    pool_timeout=30,
    pool_recycle=3600,
    pool_pre_ping=True,
)
```

## See Also

- [Repository-Service Pattern](../patterns/repository-service.md)
- [Litestar Playbook](litestar-playbook.md)
- [Testing Guide](../testing/integration.md)
