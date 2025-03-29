"""Tests for file object types."""

import os
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, cast
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from advanced_alchemy.types.file_object.fsspec import FSSpecBackend
from advanced_alchemy.types.file_object.obstore import ObstoreBackend
from advanced_alchemy.types.file_object.store import (
    AsyncStoredObject,
    ObjectStore,
    StoredObjectBase,
    SyncStoredObject,
)


class Base(DeclarativeBase):
    """Base class for models."""


class FileModel(Base):
    """Model for testing file objects."""

    __tablename__ = "files"

    id: Mapped[int] = mapped_column(primary_key=True)
    file: Mapped[Optional[StoredObjectBase]] = mapped_column(
        ObjectStore(FSSpecBackend(protocol="file"), base_path="test_files")
    )


@pytest.fixture
def temp_dir(tmp_path: Path) -> str:
    """Create a temporary directory for file storage."""
    return str(tmp_path)


@pytest.fixture
def fsspec_backend(temp_dir: str) -> FSSpecBackend:
    """Create a FSSpec backend for testing."""
    return FSSpecBackend(protocol="file", base_url=f"file://{temp_dir}")


@pytest.fixture
def obstore_backend() -> ObstoreBackend:
    """Create a mock Obstore backend for testing."""
    with patch("advanced_alchemy.types.file_object.obstore.OBSTORE_INSTALLED", True):
        mock_store = MagicMock()
        mock_store.put = MagicMock()
        mock_store.get_url = MagicMock(return_value="https://example.com/test.txt")
        mock_store.delete = MagicMock()

        backend = ObstoreBackend(
            bucket="test-bucket",
            endpoint_url="https://example.com",
            access_key="test-key",
            secret_key="test-secret",
        )
        backend._store = mock_store  # type: ignore[protected-access]
        return backend


@pytest.fixture
def db_engine(temp_dir: str) -> Any:
    """Create a SQLite engine for testing."""
    engine = create_engine(f"sqlite:///{temp_dir}/test.db")
    Base.metadata.create_all(engine)
    return engine


def test_fsspec_backend_save_file(fsspec_backend: FSSpecBackend, temp_dir: str) -> None:
    """Test saving a file using FSSpec backend."""
    # Test with bytes
    fsspec_backend.save_file("test1.txt", b"test data", "text/plain")
    assert os.path.exists(os.path.join(temp_dir, "test1.txt"))
    with open(os.path.join(temp_dir, "test1.txt"), "rb") as f:
        assert f.read() == b"test data"

    # Test with string
    fsspec_backend.save_file("test2.txt", "test data", "text/plain")
    assert os.path.exists(os.path.join(temp_dir, "test2.txt"))
    with open(os.path.join(temp_dir, "test2.txt"), "rb") as f:
        assert f.read() == b"test data"

    # Test with iterator
    data = [b"chunk1", b"chunk2", b"chunk3"]
    fsspec_backend.save_file("test3.txt", iter(data), "text/plain")
    assert os.path.exists(os.path.join(temp_dir, "test3.txt"))
    with open(os.path.join(temp_dir, "test3.txt"), "rb") as f:
        assert f.read() == b"chunk1chunk2chunk3"


def test_fsspec_backend_get_url(fsspec_backend: FSSpecBackend, temp_dir: str) -> None:
    """Test getting URLs using FSSpec backend."""
    # Test download URL
    url = fsspec_backend.get_url("test.txt", 3600)
    assert url == f"file://{temp_dir}/test.txt"

    # Test upload URL
    url_tuple = cast(
        tuple[str, str],
        fsspec_backend.get_url(
            "test.txt",
            3600,
            http_method="PUT",
            content_type="text/plain",
            for_upload=True,
            filename="test.txt",
        ),
    )
    assert url_tuple[0] == f"file://{temp_dir}/test.txt"
    assert isinstance(url_tuple[1], str)  # Token


def test_fsspec_backend_delete_file(fsspec_backend: FSSpecBackend, temp_dir: str) -> None:
    """Test deleting a file using FSSpec backend."""
    # Create a test file
    test_file = os.path.join(temp_dir, "test.txt")
    with open(test_file, "wb") as f:
        f.write(b"test data")

    # Delete the file
    fsspec_backend.delete_file("test.txt")
    assert not os.path.exists(test_file)


def test_obstore_backend_save_file(obstore_backend: ObstoreBackend) -> None:
    """Test saving a file using Obstore backend."""
    # Test with bytes
    obstore_backend.save_file("test1.txt", b"test data", "text/plain")
    cast(MagicMock, obstore_backend._store).put.assert_called_with(  # type: ignore[protected-access]
        "test1.txt", b"test data", content_type="text/plain"
    )

    # Test with string
    obstore_backend.save_file("test2.txt", "test data", "text/plain")
    cast(MagicMock, obstore_backend._store).put.assert_called_with(  # type: ignore[protected-access]
        "test2.txt", b"test data", content_type="text/plain"
    )

    # Test with iterator
    data = [b"chunk1", b"chunk2", b"chunk3"]
    obstore_backend.save_file("test3.txt", iter(data), "text/plain")
    cast(MagicMock, obstore_backend._store).put.assert_called_with(  # type: ignore[protected-access]
        "test3.txt", b"chunk1chunk2chunk3", content_type="text/plain"
    )


def test_obstore_backend_get_url(obstore_backend: ObstoreBackend) -> None:
    """Test getting URLs using Obstore backend."""
    # Test download URL
    url = obstore_backend.get_url("test.txt", 3600)
    cast(MagicMock, obstore_backend._store).get_url.assert_called_with(  # type: ignore[protected-access]
        "test.txt", 3600
    )
    assert url == "https://example.com/test.txt"

    # Test upload URL
    url_tuple = cast(
        tuple[str, str],
        obstore_backend.get_url(
            "test.txt",
            3600,
            http_method="PUT",
            content_type="text/plain",
            for_upload=True,
            filename="test.txt",
        ),
    )
    assert url_tuple[0] == "https://example.com/test.txt"
    assert isinstance(url_tuple[1], str)  # Token


def test_obstore_backend_delete_file(obstore_backend: ObstoreBackend) -> None:
    """Test deleting a file using Obstore backend."""
    obstore_backend.delete_file("test.txt")
    cast(MagicMock, obstore_backend._store).delete.assert_called_with("test.txt")  # type: ignore[protected-access]


def test_stored_object_base() -> None:
    """Test StoredObjectBase class."""
    obj = StoredObjectBase(
        filename="test.txt",
        path="test/test.txt",
        backend="fsspec",
        uploaded_at=datetime.now(),
        size=100,
        checksum="abc123",
        content_type="text/plain",
        metadata={"key": "value"},
    )

    # Test to_dict
    data = obj.to_dict()
    assert data["filename"] == "test.txt"
    assert data["path"] == "test/test.txt"
    assert data["backend"] == "fsspec"
    assert data["size"] == 100
    assert data["checksum"] == "abc123"
    assert data["content_type"] == "text/plain"
    assert data["metadata"] == {"key": "value"}

    # Test from_dict
    new_obj = StoredObjectBase.from_dict(data)
    assert new_obj.filename == obj.filename
    assert new_obj.path == obj.path
    assert new_obj.backend == obj.backend
    assert new_obj.size == obj.size
    assert new_obj.checksum == obj.checksum
    assert new_obj.content_type == obj.content_type
    assert new_obj.metadata == obj.metadata


def test_object_store_type(db_engine: Any, fsspec_backend: FSSpecBackend) -> None:
    """Test ObjectStore SQLAlchemy type."""
    from sqlalchemy.orm import Session

    # Create a test file
    file_data = b"test data"
    filename = "test.txt"
    content_type = "text/plain"

    with Session(db_engine) as session:
        # Create a new file model
        file_model = FileModel()
        file_model.file = cast(StoredObjectBase, fsspec_backend.save_file(filename, file_data, content_type))
        session.add(file_model)
        session.commit()

        # Fetch the file model
        fetched_model = session.get(FileModel, file_model.id)
        assert fetched_model is not None
        assert fetched_model.file is not None
        assert fetched_model.file.filename == filename
        assert fetched_model.file.content_type == content_type
        assert fetched_model.file.size == len(file_data)

        # Test URL generation
        url = fetched_model.file.get_url(3600)
        assert isinstance(url, str)

        # Test file deletion
        fetched_model.file.delete_file()
        session.delete(fetched_model)
        session.commit()


@pytest.mark.asyncio
async def test_async_stored_object(fsspec_backend: FSSpecBackend) -> None:
    """Test AsyncStoredObject class."""
    obj = AsyncStoredObject(
        filename="test.txt",
        path="test/test.txt",
        backend="fsspec",
        uploaded_at=datetime.now(),
        type=ObjectStore(fsspec_backend),
    )

    # Test URL generation
    url = await obj.get_url(3600)
    assert isinstance(url, str)

    # Test file operations
    new_obj = await obj.save_file(b"test data", "test.txt", "text/plain")
    assert isinstance(new_obj, StoredObjectBase)
    await obj.delete_file()


def test_sync_stored_object(fsspec_backend: FSSpecBackend) -> None:
    """Test SyncStoredObject class."""
    obj = SyncStoredObject(
        filename="test.txt",
        path="test/test.txt",
        backend="fsspec",
        uploaded_at=datetime.now(),
        type=ObjectStore(fsspec_backend),
    )

    # Test URL generation
    url = obj.get_url(3600)
    assert isinstance(url, str)

    # Test file operations
    new_obj = obj.save_file(b"test data", "test.txt", "text/plain")
    assert isinstance(new_obj, StoredObjectBase)
    obj.delete_file()
