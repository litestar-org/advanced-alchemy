"""FastAPI cursor pagination with Advanced Alchemy filter dependencies."""

import os
import tempfile
from http import HTTPStatus
from pathlib import Path
from typing import Annotated, Optional, Union

from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient
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

__all__ = (
    "EventCreate",
    "EventModel",
    "EventRepository",
    "EventSchema",
    "EventService",
    "create_app",
    "main",
)


class EventModel(base.BigIntAuditBase):
    """Event database model."""

    __tablename__ = "fastapi_cursor_event"
    name: Mapped[str]
    priority: Mapped[int]


class EventCreate(BaseModel):
    """Request payload for creating an event."""

    name: str
    priority: int


class EventSchema(BaseModel):
    """Response schema for an event."""

    model_config = {"from_attributes": True}

    id: int
    name: str
    priority: int


class EventRepository(repository.SQLAlchemyAsyncRepository[EventModel]):
    """Event async repository."""

    model_type = EventModel


class EventService(service.SQLAlchemyAsyncRepositoryService[EventModel, EventRepository]):
    """Event async repository service."""

    repository_type = EventRepository


def create_app(db_path: Path) -> FastAPI:
    """Create a FastAPI application with cursor-paginated event listing."""
    app = FastAPI()
    alchemy = AdvancedAlchemy(
        config=SQLAlchemyAsyncConfig(
            connection_string=f"sqlite+aiosqlite:///{db_path}",
            session_config=AsyncSessionConfig(expire_on_commit=False),
            create_all=True,
            commit_mode="autocommit",
            pagination_cursor_secret=os.environ.get("CURSOR_SECRET", "development-only-secret"),
        ),
        app=app,
    )
    router = APIRouter()

    @router.post("/events", status_code=int(HTTPStatus.CREATED))
    async def create_event(
        data: EventCreate,
        events_service: Annotated[EventService, Depends(alchemy.provide_service(EventService))],
    ) -> EventSchema:
        """Create an event."""
        obj = await events_service.create(data)
        return events_service.to_schema(obj, schema_type=EventSchema)

    @router.get("/events")
    async def list_events(
        events_service: Annotated[EventService, Depends(alchemy.provide_service(EventService))],
        filters: Annotated[
            list[filters.FilterTypes],
            Depends(
                alchemy.provide_filters(
                    {
                        "pagination_type": "cursor",
                        "pagination_size": 20,
                        "sort_field": "priority",
                        "sort_fields": ["priority", "name"],
                    },
                ),
            ),
        ],
    ) -> service.CursorPagination[EventSchema]:
        """List events one cursor page at a time."""
        results = await events_service.get_many(*filters)
        return events_service.to_schema(
            results,
            filters=filters,
            schema_type=EventSchema,
            pagination_type="cursor",
        )

    app.include_router(router)
    return app


def main() -> None:
    """Create events, then walk every page ordered by name."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        app = create_app(Path(tmp_dir) / "fastapi_cursor.sqlite")
        with TestClient(app=app) as client:
            for index in range(5):
                response = client.post("/events", json={"name": f"event {4 - index}", "priority": index % 2})
                if response.status_code != HTTPStatus.CREATED:
                    msg = f"Unexpected create status: {response.status_code}"
                    raise RuntimeError(msg)

            names: list[str] = []
            cursor: Optional[str] = None
            while True:
                params: dict[str, Union[str, int]] = {"orderBy": "name", "pageSize": 2}
                if cursor:
                    params["cursor"] = cursor
                page = client.get("/events", params=params).json()
                names.extend(item["name"] for item in page["items"])
                if not page["has_next"]:
                    break
                cursor = page["next_cursor"]

            if names != [f"event {index}" for index in range(5)]:
                msg = f"Unexpected walk: {names}"
                raise RuntimeError(msg)

            rejected = client.get("/events", params={"orderBy": "id"})
            if rejected.status_code != HTTPStatus.UNPROCESSABLE_ENTITY:
                msg = f"Disallowed sort field was not rejected: {rejected.status_code}"
                raise RuntimeError(msg)
