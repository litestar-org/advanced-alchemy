# /// script
# dependencies = [
#   "advanced_alchemy",
#   "aiosqlite",
#   "fastapi[standard]",
#   "orjson"
# ]
# ///
import datetime
from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, FastAPI
from pydantic import BaseModel
from sqlalchemy.orm import Mapped

from advanced_alchemy.extensions.fastapi import (
    AdvancedAlchemy,
    AsyncSessionConfig,
    SQLAlchemyAsyncConfig,
    base,
    filters,
    repository,
    service,
)

alchemy_config = SQLAlchemyAsyncConfig(
    connection_string="sqlite+aiosqlite:///test.sqlite",
    session_config=AsyncSessionConfig(expire_on_commit=False),
    commit_mode="autocommit",
    create_all=True,
)
app = FastAPI()
alchemy = AdvancedAlchemy(config=alchemy_config, app=app)
author_router = APIRouter()


# the SQLAlchemy base includes a declarative model for you to use in your models.
# The `Base` class includes a `UUID` based primary key (`id`)
class AuthorModel(base.UUIDBase):
    # we can optionally provide the table name instead of auto-generating it
    __tablename__ = "author"
    name: Mapped[str]
    dob: Mapped[Optional[datetime.date]]


class AuthorService(service.SQLAlchemyAsyncRepositoryService[AuthorModel]):
    """Author repository."""

    class Repo(repository.SQLAlchemyAsyncRepository[AuthorModel]):
        """Author repository."""

        model_type = AuthorModel

    repository_type = Repo


# Pydantic Models
class Author(BaseModel):
    id: Optional[UUID]
    name: str
    dob: Optional[datetime.date]


class AuthorCreate(BaseModel):
    name: str
    dob: Optional[datetime.date]


class AuthorUpdate(BaseModel):
    name: Optional[str]
    dob: Optional[datetime.date]


@author_router.get(path="/authors", response_model=service.OffsetPagination[Author])
async def list_authors(
    authors_service: Annotated[AuthorService, Depends(alchemy.provide_service(AuthorService))],
    filters: Annotated[
        list[filters.FilterTypes],
        Depends(
            alchemy.provide_filters(
                {
                    "id_filter": UUID,
                    "pagination_type": "limit_offset",
                    "search": "name",
                    "search_ignore_case": True,
                    "sort_field": "dob",
                    "sort_order": "desc",
                }
            )
        ),
    ],
) -> service.OffsetPagination[AuthorModel]:
    results, total = await authors_service.list_and_count(*filters)
    return authors_service.to_schema(results, total, filters=filters)


@author_router.post(path="/authors")
async def create_author(
    authors_service: Annotated[AuthorService, Depends(alchemy.provide_service(AuthorService))],
    data: AuthorCreate,
) -> Author:
    obj = await authors_service.create(data)
    # if you want to have the service return a pydantic model instead of the sqlalchemy model,
    # you can do so by passing the model to the schema_type argument of the to_schema method
    return authors_service.to_schema(obj, schema_type=Author)


@author_router.get(path="/authors/{author_id}", response_model=Author)
async def get_author(
    authors_service: Annotated[AuthorService, Depends(alchemy.provide_service(AuthorService))],
    author_id: UUID,
) -> AuthorModel:
    obj = await authors_service.get(author_id)
    return authors_service.to_schema(obj)


@author_router.patch(path="/authors/{author_id}", response_model=Author)
async def update_author(
    authors_service: Annotated[AuthorService, Depends(alchemy.provide_service(AuthorService))],
    data: AuthorUpdate,
    author_id: UUID,
) -> AuthorModel:
    obj = await authors_service.update(data, item_id=author_id)
    return authors_service.to_schema(obj)


@author_router.delete(path="/authors/{author_id}")
async def delete_author(
    authors_service: Annotated[AuthorService, Depends(alchemy.provide_service(AuthorService))], author_id: UUID
) -> None:
    _ = await authors_service.delete(author_id)


app.include_router(author_router)


if __name__ == "__main__":
    """Launches the FastAPI CLI with the database commands registered
    Run `uv run examples/fastapi/fastapi_service.py --help` to launch the FastAPI CLI with the database commands registered
    """
    from fastapi_cli.cli import app as fastapi_cli_app  # pyright: ignore[reportUnknownVariableType]
    from typer.main import get_group

    from advanced_alchemy.extensions.fastapi.cli import register_database_commands

    click_app = get_group(fastapi_cli_app)  # pyright: ignore[reportUnknownArgumentType]
    click_app.add_command(register_database_commands(app))
    click_app()
