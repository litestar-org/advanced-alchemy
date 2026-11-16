import asyncio
from collections.abc import AsyncIterator, Sequence
from pathlib import Path
from typing import Any, Optional, Union

import pytest
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker as sync_sessionmaker

from advanced_alchemy._listeners import AsyncFileObjectListener
from advanced_alchemy.types.file_object.base import AsyncDataLike, DataLike, PathLike, StorageBackend
from advanced_alchemy.types.file_object.file import FileObject
from advanced_alchemy.types.file_object.registry import storages
from tests.unit.test_extensions.test_adk.fixtures import SESSION_MODEL_CONFIG, SampleADKArtifact, metadata


class DictStorageBackend(StorageBackend):
    driver = "dict"
    protocol = "memory"

    def __init__(self, key: str) -> None:
        super().__init__(key=key, fs={})
        self.fs: dict[str, bytes] = {}

    def get_content(self, path: PathLike, *, options: Optional[dict[str, Any]] = None) -> bytes:
        try:
            return self.fs[str(path)]
        except KeyError as e:
            raise FileNotFoundError(str(path)) from e

    async def get_content_async(self, path: PathLike, *, options: Optional[dict[str, Any]] = None) -> bytes:
        return self.get_content(path, options=options)

    def save_object(
        self,
        file_object: FileObject,
        data: DataLike,
        *,
        use_multipart: Optional[bool] = None,
        chunk_size: int = 5 * 1024 * 1024,
        max_concurrency: int = 12,
    ) -> FileObject:
        if isinstance(data, bytes):
            content = data
        elif isinstance(data, Path):
            content = data.read_bytes()
        elif hasattr(data, "read"):
            content = data.read()
        else:
            content = b"".join(data)
        self.fs[file_object.path] = content
        file_object.size = len(content)
        return file_object

    async def save_object_async(
        self,
        file_object: FileObject,
        data: AsyncDataLike,
        *,
        use_multipart: Optional[bool] = None,
        chunk_size: int = 5 * 1024 * 1024,
        max_concurrency: int = 12,
    ) -> FileObject:
        if hasattr(data, "__aiter__"):
            content = b"".join([chunk async for chunk in data])  # pyright: ignore[reportGeneralTypeIssues]
            return self.save_object(file_object, content)
        return self.save_object(file_object, data)  # type: ignore[arg-type]

    def delete_object(self, paths: Union[PathLike, Sequence[PathLike]]) -> None:
        path_list = [paths] if isinstance(paths, (str, Path)) else paths
        for path in path_list:
            try:
                del self.fs[str(path)]
            except KeyError as e:
                raise FileNotFoundError(str(path)) from e

    async def delete_object_async(self, paths: Union[PathLike, Sequence[PathLike]]) -> None:
        self.delete_object(paths)

    def sign(
        self,
        paths: Union[PathLike, Sequence[PathLike]],
        *,
        expires_in: Optional[int] = None,
        for_upload: bool = False,
    ) -> Union[str, list[str]]:
        if isinstance(paths, (str, Path)):
            return f"memory://{paths}"
        return [f"memory://{path}" for path in paths]

    async def sign_async(
        self,
        paths: Union[PathLike, Sequence[PathLike]],
        *,
        expires_in: Optional[int] = None,
        for_upload: bool = False,
    ) -> Union[str, list[str]]:
        return self.sign(paths, expires_in=expires_in, for_upload=for_upload)


@pytest.fixture
async def artifact_session(
    tmp_path: Path,
) -> AsyncIterator[tuple[async_sessionmaker[AsyncSession], DictStorageBackend]]:
    from advanced_alchemy.extensions.adk.artifacts import ADKAsyncArtifactService

    _ = ADKAsyncArtifactService
    backend = DictStorageBackend("adk-artifacts-test")
    if storages.is_registered(backend.key):
        storages.unregister_backend(backend.key)
    storages.register_backend(backend)

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'adk-artifacts.db'}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    sync_maker = sync_sessionmaker()
    event.listen(sync_maker, "before_flush", AsyncFileObjectListener.before_flush)
    event.listen(sync_maker, "after_commit", AsyncFileObjectListener.after_commit)
    event.listen(sync_maker, "after_rollback", AsyncFileObjectListener.after_rollback)
    session_factory.configure(sync_session_class=sync_maker)
    async with engine.begin() as connection:
        await connection.run_sync(metadata.create_all)
    try:
        yield session_factory, backend
    finally:
        storages.unregister_backend(backend.key)
        await engine.dispose()


async def _let_file_listener_run() -> None:
    await asyncio.sleep(0.05)


async def test_artifact_service_round_trips_versions_and_metadata(
    artifact_session: tuple[async_sessionmaker[AsyncSession], DictStorageBackend],
) -> None:
    from google.adk.artifacts.base_artifact_service import ArtifactVersion, BaseArtifactService
    from google.genai import types

    from advanced_alchemy.extensions.adk.artifacts import ADKAsyncArtifactService

    session_factory, backend = artifact_session
    async with session_factory() as db_session:
        service = ADKAsyncArtifactService(db_session, artifact_model=SampleADKArtifact, backend_key=backend.key)

        assert isinstance(service, BaseArtifactService)

        first_version = await service.save_artifact(
            app_name="app",
            user_id="user",
            session_id="session",
            filename="report.bin",
            artifact=types.Part(inline_data=types.Blob(data=b"first", mime_type="application/octet-stream")),
            custom_metadata={"turn": 1},
        )
        second_version = await service.save_artifact(
            app_name="app",
            user_id="user",
            session_id="session",
            filename="report.bin",
            artifact=types.Part(text="second"),
        )

        assert (first_version, second_version) == (0, 1)
        assert backend.fs == {}

        await db_session.commit()
        await _let_file_listener_run()

        assert sorted(backend.fs) == ["app/user/session/report.bin/0", "app/user/session/report.bin/1"]
        assert await service.list_versions(
            app_name="app",
            user_id="user",
            session_id="session",
            filename="report.bin",
        ) == [0, 1]
        assert await service.list_artifact_keys(app_name="app", user_id="user", session_id="session") == [
            "report.bin",
        ]

        loaded_first = await service.load_artifact(
            app_name="app",
            user_id="user",
            session_id="session",
            filename="report.bin",
            version=0,
        )
        loaded_latest = await service.load_artifact(
            app_name="app",
            user_id="user",
            session_id="session",
            filename="report.bin",
        )

        assert loaded_first is not None
        assert loaded_first.inline_data is not None
        assert loaded_first.inline_data.data == b"first"
        assert loaded_first.inline_data.mime_type == "application/octet-stream"
        assert loaded_latest is not None
        assert loaded_latest.text == "second"

        artifact_version = await service.get_artifact_version(
            app_name="app",
            user_id="user",
            session_id="session",
            filename="report.bin",
            version=0,
        )
        assert isinstance(artifact_version, ArtifactVersion)
        assert artifact_version.version == 0
        assert artifact_version.canonical_uri == "memory://app/user/session/report.bin/0"
        assert artifact_version.custom_metadata == {"turn": 1}


async def test_artifact_service_rollback_skips_blob_upload(
    artifact_session: tuple[async_sessionmaker[AsyncSession], DictStorageBackend],
) -> None:
    from google.genai import types

    from advanced_alchemy.extensions.adk.artifacts import ADKAsyncArtifactService

    session_factory, backend = artifact_session
    async with session_factory() as db_session:
        service = ADKAsyncArtifactService(db_session, artifact_model=SampleADKArtifact, backend_key=backend.key)
        await service.save_artifact(
            app_name="app",
            user_id="user",
            session_id="session",
            filename="rollback.bin",
            artifact=types.Part(inline_data=types.Blob(data=b"rollback", mime_type="application/octet-stream")),
        )

        await db_session.rollback()
        await _let_file_listener_run()

        assert backend.fs == {}
        assert (await db_session.scalars(select(SampleADKArtifact))).all() == []


async def test_artifact_service_delete_removes_blobs_after_commit(
    artifact_session: tuple[async_sessionmaker[AsyncSession], DictStorageBackend],
) -> None:
    from google.genai import types

    from advanced_alchemy.extensions.adk.artifacts import ADKAsyncArtifactService

    session_factory, backend = artifact_session
    async with session_factory() as db_session:
        service = ADKAsyncArtifactService(db_session, artifact_model=SampleADKArtifact, backend_key=backend.key)
        await service.save_artifact(
            app_name="app",
            user_id="user",
            session_id="session",
            filename="delete.bin",
            artifact=types.Part(inline_data=types.Blob(data=b"delete", mime_type="application/octet-stream")),
        )
        await db_session.commit()
        await _let_file_listener_run()
        assert backend.fs == {"app/user/session/delete.bin/0": b"delete"}

        await service.delete_artifact(app_name="app", user_id="user", session_id="session", filename="delete.bin")
        await db_session.commit()
        await _let_file_listener_run()

        assert backend.fs == {}


async def test_artifact_service_user_scoped_artifacts_do_not_require_session_id(
    artifact_session: tuple[async_sessionmaker[AsyncSession], DictStorageBackend],
) -> None:
    from google.genai import types

    from advanced_alchemy.extensions.adk.artifacts import ADKAsyncArtifactService

    session_factory, backend = artifact_session
    async with session_factory() as db_session:
        service = ADKAsyncArtifactService(db_session, artifact_model=SampleADKArtifact, backend_key=backend.key)
        version = await service.save_artifact(
            app_name="app",
            user_id="user",
            filename="user:shared.bin",
            artifact=types.Part(inline_data=types.Blob(data=b"shared", mime_type="application/octet-stream")),
        )
        await db_session.commit()
        await _let_file_listener_run()

        assert version == 0
        assert backend.fs == {"app/user/user/user:shared.bin/0": b"shared"}
        assert await service.list_artifact_keys(app_name="app", user_id="user", session_id="session") == [
            "user:shared.bin",
        ]


async def test_session_service_delete_session_removes_session_artifact_blobs(
    artifact_session: tuple[async_sessionmaker[AsyncSession], DictStorageBackend],
) -> None:
    from google.genai import types

    from advanced_alchemy.extensions.adk import ADKAsyncSessionService
    from advanced_alchemy.extensions.adk.artifacts import ADKAsyncArtifactService

    session_factory, backend = artifact_session
    async with session_factory() as db_session:
        session_service = ADKAsyncSessionService(db_session, model_config=SESSION_MODEL_CONFIG)
        artifact_service = ADKAsyncArtifactService(
            db_session, artifact_model=SampleADKArtifact, backend_key=backend.key
        )
        await session_service.create_session(app_name="app", user_id="user", session_id="session")
        await artifact_service.save_artifact(
            app_name="app",
            user_id="user",
            session_id="session",
            filename="cascade.bin",
            artifact=types.Part(inline_data=types.Blob(data=b"cascade", mime_type="application/octet-stream")),
        )
        await db_session.commit()
        await _let_file_listener_run()
        assert backend.fs == {"app/user/session/cascade.bin/0": b"cascade"}

        await session_service.delete_session(app_name="app", user_id="user", session_id="session")
        await db_session.commit()
        await _let_file_listener_run()

        assert backend.fs == {}
        assert (await db_session.scalars(select(SampleADKArtifact))).all() == []
