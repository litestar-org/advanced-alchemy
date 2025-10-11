# Litestar Playbook

Advanced Alchemy + Litestar integration patterns. For full Litestar docs, see [docs.litestar.dev](https://docs.litestar.dev).

## Installation

```bash
pip install litestar[standard] advanced-alchemy[all]
# or with uv
uv add litestar[standard] advanced-alchemy[all]
```

## Basic Setup

```python
from litestar import Litestar
from litestar.plugins.sqlalchemy import SQLAlchemyPlugin, SQLAlchemyAsyncConfig

alchemy = SQLAlchemyPlugin(
    config=SQLAlchemyAsyncConfig(
        connection_string="postgresql+asyncpg://user:pass@localhost/db",
    ),
)

app = Litestar(
    plugins=[alchemy],
    route_handlers=[],
)
```

## Models

```python
from advanced_alchemy.base import UUIDAuditBase
from sqlalchemy.orm import Mapped, mapped_column, relationship


class User(UUIDAuditBase):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(unique=True, index=True)
    name: Mapped[str]
    hashed_password: Mapped[str | None] = mapped_column(default=None)
    is_active: Mapped[bool] = mapped_column(default=True)

    posts: Mapped[list["Post"]] = relationship("Post", back_populates="author")
```

## Services

```python
from __future__ import annotations

from litestar.plugins.sqlalchemy import service, repository
from app.db import models as m


class UserService(service.SQLAlchemyAsyncRepositoryService[m.User]):
    """User service."""

    class Repo(repository.SQLAlchemyAsyncRepository[m.User]):
        model_type = m.User

    repository_type = Repo
    match_fields = ["email"]

    async def to_model_on_create(self, data: service.ModelDictT[m.User]) -> service.ModelDictT[m.User]:
        data = service.schema_dump(data)
        return data
```

## DTOs

```python
from litestar.dto import DTOConfig, DataclassDTO
from dataclasses import dataclass
from uuid import UUID


@dataclass
class UserCreate:
    email: str
    name: str
    password: str


@dataclass
class UserUpdate:
    email: str | None = None
    name: str | None = None


@dataclass
class UserPublic:
    id: UUID
    email: str
    name: str
    is_active: bool
    created_at: str
    updated_at: str


class UserCreateDTO(DataclassDTO[UserCreate]):
    config = DTOConfig()


class UserUpdateDTO(DataclassDTO[UserUpdate]):
    config = DTOConfig(partial=True)


class UserPublicDTO(DataclassDTO[UserPublic]):
    config = DTOConfig()
```

## Controllers

```python
from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from litestar import Controller, get, post, patch, delete
from litestar.di import Provide
from litestar.dto import DTOData

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def provide_user_service(db_session: AsyncSession) -> UserService:
    return UserService(session=db_session)


class UserController(Controller):
    path = "/users"
    tags = ["users"]
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

## Advanced Patterns

### Filtering and Pagination

```python
from advanced_alchemy.filters import LimitOffset, BeforeAfter, SearchFilter
from litestar import get
from litestar.params import Parameter


@get()
async def list_users(
    user_service: UserService,
    limit: int = Parameter(default=20, le=100),
    offset: int = Parameter(default=0, ge=0),
    search: str | None = None,
) -> list[m.User]:
    filters = [LimitOffset(limit=limit, offset=offset)]
    if search:
        filters.append(SearchFilter(field_name="name", value=search))
    users, total = await user_service.list_and_count(*filters)
    return users
```

### Eager Loading

```python
from sqlalchemy.orm import selectinload


@get("/{user_id:uuid}")
async def get_user_with_posts(user_service: UserService, user_id: UUID) -> m.User:
    return await user_service.get_one(
        id=user_id,
        load=[selectinload(m.User.posts)],
    )
```

### Password Hashing

```python
class UserService(service.SQLAlchemyAsyncRepositoryService[m.User]):
    # ... repository setup ...

    async def to_model_on_create(self, data: service.ModelDictT[m.User]) -> service.ModelDictT[m.User]:
        data = service.schema_dump(data)
        return await self._populate_with_hashed_password(data)

    async def _populate_with_hashed_password(self, data: service.ModelDictT[m.User]) -> service.ModelDictT[m.User]:
        if service.is_dict(data) and (password := data.pop("password", None)) is not None:
            data["hashed_password"] = await crypt.get_password_hash(password)
        return data

    async def authenticate(self, email: str, password: str) -> m.User:
        user = await self.get_one_or_none(email=email.lower())
        if not user:
            raise PermissionDeniedException(detail="invalid credentials")
        if not user.hashed_password:
            raise PermissionDeniedException(detail="invalid credentials")
        if not await crypt.verify_password(password, user.hashed_password):
            raise PermissionDeniedException(detail="invalid credentials")
        if not user.is_active:
            raise PermissionDeniedException(detail="account inactive")
        return user
```

### Slug Repository

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

### UniqueMixin Pattern

```python
from advanced_alchemy.base import UUIDAuditBase
from advanced_alchemy.mixins import UniqueMixin
from sqlalchemy import ColumnElement
from sqlalchemy.orm import Mapped, mapped_column


class Tag(UUIDAuditBase, UniqueMixin):
    __tablename__ = "tags"

    name: Mapped[str] = mapped_column(unique=True)
    slug: Mapped[str] = mapped_column(unique=True)

    @classmethod
    def unique_hash(cls, *args, **kwargs) -> int:
        return hash(kwargs.get("name"))

    @classmethod
    def unique_filter(cls, *args, **kwargs) -> ColumnElement[bool]:
        return cls.name == kwargs.get("name")


# Usage: get-or-create
tag = await Tag.as_unique_async(session, name="python", slug="python")
```

### Relationship Management with UniqueMixin

```python
from uuid_utils.compat import uuid4
from advanced_alchemy.utils.text import slugify


class TeamService(service.SQLAlchemyAsyncRepositoryService[m.Team]):
    # ... setup ...

    async def to_model_on_create(self, data: service.ModelDictT[m.Team]) -> service.ModelDictT[m.Team]:
        data = service.schema_dump(data)

        if service.is_dict(data):
            owner_id = data.pop("owner_id", None)
            tag_names = data.pop("tags", [])

            data["id"] = data.get("id", uuid4())
            data = await super().to_model(data)

            # Add tags using UniqueMixin (get-or-create)
            if tag_names:
                data.tags.extend([
                    await m.Tag.as_unique_async(
                        self.repository.session,
                        name=tag,
                        slug=slugify(tag)
                    )
                    for tag in tag_names
                ])

            if owner_id:
                data.members.append(
                    m.TeamMember(
                        user_id=owner_id,
                        role=m.TeamRoles.ADMIN,
                        is_owner=True
                    )
                )

        return data
```

## Multiple Databases

```python
from advanced_alchemy.extensions.litestar import SQLAlchemyPlugin, SQLAlchemyAsyncConfig

alchemy = SQLAlchemyPlugin(
    config=[
        SQLAlchemyAsyncConfig(
            connection_string="postgresql+asyncpg://user:pass@localhost/primary",
            session_dependency_key="primary_db_session",
        ),
        SQLAlchemyAsyncConfig(
            connection_string="duckdb:///analytics.db",
            session_dependency_key="analytics_db_session",
        ),
    ]
)

app = Litestar(plugins=[alchemy])
```

## Connection Pooling

```python
config = SQLAlchemyAsyncConfig(
    connection_string="postgresql+asyncpg://user:pass@localhost/db",
    pool_size=20,
    max_overflow=10,
    pool_timeout=30,
    pool_recycle=3600,
    pool_pre_ping=True,
)
```

## Testing

```python
import pytest
from litestar import Litestar
from litestar.testing import AsyncTestClient
from litestar.plugins.sqlalchemy import SQLAlchemyPlugin, SQLAlchemyAsyncConfig

from app.db.models import Base


@pytest.fixture
async def app() -> Litestar:
    alchemy = SQLAlchemyPlugin(
        config=SQLAlchemyAsyncConfig(
            connection_string="sqlite+aiosqlite:///:memory:",
        ),
    )

    app = Litestar(
        plugins=[alchemy],
        route_handlers=[UserController],
    )

    async with alchemy.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    return app


@pytest.fixture
async def client(app: Litestar) -> AsyncTestClient:
    async with AsyncTestClient(app=app) as client:
        yield client


async def test_create_user(client: AsyncTestClient) -> None:
    response = await client.post(
        "/users",
        json={"email": "test@example.com", "name": "Test User", "password": "secret123"},
    )
    assert response.status_code == 201
    assert response.json()["email"] == "test@example.com"
```

## Common Pitfalls

### ❌ Creating New Session Per Request

```python
# Wrong
async def provide_user_service() -> UserService:
    config = SQLAlchemyAsyncConfig(...)  # Don't do this!
    return UserService(...)
```

### ✅ Use Injected Session

```python
# Correct
async def provide_user_service(db_session: AsyncSession) -> UserService:
    return UserService(session=db_session)
```

### ❌ Bypassing Service Layer

```python
# Wrong
@post()
async def create_user(db_session: AsyncSession, data: UserCreate) -> m.User:
    user = m.User(**data.dict())
    db_session.add(user)
    await db_session.commit()
    return user
```

### ✅ Use Service Methods

```python
# Correct
@post()
async def create_user(user_service: UserService, data: DTOData[UserCreate]) -> m.User:
    return await user_service.create(data.as_builtins())
```

## Production Checklist

- ✅ Use connection pooling
- ✅ Enable `pool_pre_ping`
- ✅ Use DTOs to exclude sensitive fields
- ✅ Add indexes to models
- ✅ Use eager loading to prevent N+1 queries
- ✅ Use Alembic for migrations
- ✅ Set `expire_on_commit=False` for detached instances
- ✅ Use transactions for multi-step operations

## Examples

Working examples in [`examples/`](../../../examples/):

- **[litestar_service.py](../../../examples/litestar/litestar_service.py)** - Complete service layer
- **[litestar_repo_only.py](../../../examples/litestar/litestar_repo_only.py)** - Repository without service
- **[litestar_fileobject.py](../../../examples/litestar/litestar_fileobject.py)** - File storage
- **[fastapi/](../../../examples/fastapi/)** - FastAPI integration
- **[flask/](../../../examples/flask/)** - Flask integration
- **[sanic.py](../../../examples/sanic.py)** - Sanic integration
- **[standalone.py](../../../examples/standalone.py)** - Without web framework

## See Also

- [Repository-Service Pattern](../patterns/repository-service.md)
- [Testing Guide](../testing/integration.md)
- [Litestar Docs](https://docs.litestar.dev)
- [litestar-fullstack-spa](https://github.com/litestar-org/litestar-fullstack-spa) - Reference app
