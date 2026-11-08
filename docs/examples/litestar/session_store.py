"""Litestar server-side session store and StoredObject file storage example."""

from __future__ import annotations

from pathlib import Path
import tempfile
from typing import Any
from uuid import UUID

from litestar import Litestar, Request, get, post
from litestar.middleware.session.server_side import ServerSideSessionConfig
from litestar.stores.registry import StoreRegistry
from litestar.testing import TestClient
import msgspec
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from advanced_alchemy.extensions.litestar import (
    SQLAlchemyAsyncConfig,
    SQLAlchemyPlugin,
    base,
    repository,
    service,
)
from advanced_alchemy.extensions.litestar.store import SQLAlchemyStore, StoreModelMixin
from advanced_alchemy.types import FileObject, StoredObject, storages

__all__ = (
    "AppStoreModel",
    "AttachmentModel",
    "AttachmentRepository",
    "AttachmentSchema",
    "AttachmentService",
    "create_app",
    "main",
)


class AppStoreModel(StoreModelMixin):
    """Database table backing Litestar's server-side session store."""

    __tablename__ = "litestar_app_store"


class AttachmentModel(base.UUIDBase):
    """Document attachment model with StoredObject metadata."""

    __tablename__ = "litestar_attachment"
    title: Mapped[str]
    document: Mapped[FileObject | None] = mapped_column(
        StoredObject(backend="litestar_docs_fs"),
        nullable=True,
    )


class AttachmentSchema(msgspec.Struct):
    """Serialized attachment response payload."""

    id: UUID
    title: str
    filename: str | None = None


class AttachmentRepository(repository.SQLAlchemyAsyncRepository[AttachmentModel]):
    """Attachment async repository."""

    model_type = AttachmentModel


class AttachmentService(service.SQLAlchemyAsyncRepositoryService[AttachmentModel, AttachmentRepository]):
    """Attachment async service."""

    repository_type = AttachmentRepository


@post(path="/session/{key:str}/{value:str}")
async def set_session_value(key: str, value: str, request: Request[Any, Any, Any]) -> dict[str, str]:
    """Store a key-value pair in the server-side session."""
    request.session[key] = value
    return {"key": key, "value": value}


@get(path="/session/{key:str}")
async def get_session_value(key: str, request: Request[Any, Any, Any]) -> dict[str, str | None]:
    """Read a key-value pair from the server-side session."""
    return {"key": key, "value": request.session.get(key)}


@post(path="/attachments")
async def upload_attachment(
    data: dict[str, str],
    db_session: AsyncSession,
) -> AttachmentSchema:
    """Persist an attachment record and its StoredObject file payload."""
    svc = AttachmentService(session=db_session)
    file_obj = FileObject(
        backend="litestar_docs_fs",
        filename=data["filename"],
        content_type="text/plain",
        content=data["content"].encode("utf-8"),
    )
    record = await svc.create(
        {"title": data["title"], "document": file_obj},
        auto_commit=True,
    )
    return AttachmentSchema(
        id=record.id,
        title=record.title,
        filename=record.document.filename if record.document else None,
    )


def create_app(db_path: Path, storage_dir: Path) -> Litestar:
    """Create a Litestar application configured with SQLAlchemyStore and StoredObject."""
    storages.register_backend(f"file://{storage_dir}", key="litestar_docs_fs")
    alchemy_config = SQLAlchemyAsyncConfig(
        connection_string=f"sqlite+aiosqlite:///{db_path}",
        create_all=True,
    )
    session_store = SQLAlchemyStore(config=alchemy_config, model=AppStoreModel)
    session_config = ServerSideSessionConfig(store="sessions")

    return Litestar(
        route_handlers=[set_session_value, get_session_value, upload_attachment],
        plugins=[SQLAlchemyPlugin(config=alchemy_config)],
        middleware=[session_config.middleware],
        stores=StoreRegistry(stores={"sessions": session_store}),
    )


def main() -> None:
    """Execute the session store and StoredObject Litestar example inside a temporary directory."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        base_dir = Path(tmp_dir)
        db_file = base_dir / "session_store.sqlite"
        storage_dir = base_dir / "uploads"
        storage_dir.mkdir(parents=True, exist_ok=True)
        app = create_app(db_file, storage_dir)
        with TestClient(app=app) as client:
            set_res = client.post("/session/theme/dark")
            assert set_res.status_code == 201

            get_res = client.get("/session/theme")
            assert get_res.status_code == 200
            assert get_res.json() == {"key": "theme", "value": "dark"}

            upload_res = client.post(
                "/attachments",
                json={"title": "Architecture Spec", "filename": "spec.txt", "content": "Stored via Advanced Alchemy"},
            )
            assert upload_res.status_code == 201
            payload = upload_res.json()
            assert payload["title"] == "Architecture Spec"
            assert payload["filename"] == "spec.txt"
        storages.clear_backends()
