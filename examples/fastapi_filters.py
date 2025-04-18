"""This example demonstrates how to use the FastAPI CLI to manage the database."""

# /// script
# dependencies = [
#   "advanced_alchemy",
#   "fastapi[standard]",
#   "orjson"
# ]
# ///
import datetime
from collections.abc import AsyncGenerator
from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, FastAPI
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped

from advanced_alchemy.extensions.fastapi import (
    AdvancedAlchemy,
    AsyncSessionConfig,
    SQLAlchemyAsyncConfig,
    base,
    filters,
    providers,
    repository,
    service,
)


class AuthorModel(base.UUIDBase):
    __tablename__ = "author"
    name: Mapped[str]
    dob: Mapped[Optional[datetime.date]]


class Author(BaseModel):
    id: Optional[UUID]
    name: str
    dob: Optional[datetime.date]


class AuthorService(service.SQLAlchemyAsyncRepositoryService[AuthorModel]):
    """Author repository."""

    class Repo(repository.SQLAlchemyAsyncRepository[AuthorModel]):
        """Author repository."""

        model_type = AuthorModel

    repository_type = Repo


sqlalchemy_config = SQLAlchemyAsyncConfig(
    connection_string="sqlite+aiosqlite:///test.sqlite",
    session_config=AsyncSessionConfig(expire_on_commit=False),
    create_all=True,
)
app = FastAPI()
alchemy = AdvancedAlchemy(config=sqlalchemy_config, app=app)


async def provide_authors_service(
    db_session: Annotated[AsyncSession, Depends(alchemy.provide_session())],
) -> AsyncGenerator[AuthorService, None]:
    async with AuthorService.new(session=db_session) as service:
        yield service


author_router = APIRouter()


@author_router.get(path="/authors", response_model=service.OffsetPagination[Author])
async def list_authors(
    authors_service: Annotated[AuthorService, Depends(provide_authors_service)],
    filters: Annotated[
        list[filters.FilterTypes],
        Depends(
            providers.provide_filters({
                "id_filter": UUID,
                "pagination_type": "limit_offset",
                "search": "name",
                "search_ignore_case": True,
            })
        ),
    ],
) -> service.OffsetPagination[AuthorModel]:
    results, total = await authors_service.list_and_count(*filters)
    return authors_service.to_schema(results, total, filters=filters)


app.include_router(author_router)
if __name__ == "__main__":
    """Launches the FastAPI CLI with the database commands registered"""
    from fastapi_cli.cli import app as fastapi_cli_app  # pyright: ignore[reportUnknownVariableType]
    from typer.main import get_group

    from advanced_alchemy.extensions.fastapi.cli import register_database_commands

    click_app = get_group(fastapi_cli_app)  # pyright: ignore[reportUnknownArgumentType]
    click_app.add_command(register_database_commands(app))
    click_app()
