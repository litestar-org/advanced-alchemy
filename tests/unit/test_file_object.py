"""Unit tests for FileObject class."""

import asyncio
import logging
import sys
from pathlib import Path
from typing import Callable, Optional
from unittest.mock import AsyncMock, MagicMock, Mock, PropertyMock, patch

import pytest
from sqlalchemy.orm import Session

from advanced_alchemy.service.typing import PYDANTIC_INSTALLED, BaseModel
from advanced_alchemy.types.file_object import FileObject
from advanced_alchemy.types.file_object.base import StorageBackend
from advanced_alchemy.types.file_object.session_tracker import FileObjectSessionTracker

if sys.version_info >= (3, 11):
    from builtins import ExceptionGroup
else:
    from exceptiongroup import ExceptionGroup  # type: ignore[import-not-found,unused-ignore]


def test_file_object_delete_no_backend() -> None:
    """Test delete method when backend is None."""
    # Create a FileObject
    obj = FileObject(backend="mock", filename="test.txt")

    # Directly patch the backend property to specifically return None for this test
    with patch.object(FileObject, "backend", new_callable=PropertyMock, return_value=None):
        # Deleting with no backend should raise a RuntimeError
        with pytest.raises(RuntimeError, match="No storage backend configured"):
            obj.delete()


def test_sign_empty_result_list() -> None:
    """Test sign method when backend returns an empty list."""
    # Create a FileObject
    obj = FileObject(backend="mock", filename="test.txt")

    # Create a mock backend
    mock_backend = Mock(spec=StorageBackend)
    mock_backend.key = "mock"
    mock_backend.sign.return_value = []  # Empty list

    # Patch the storages.get_backend method to return our mock backend
    with patch("advanced_alchemy.types.file_object.storages.get_backend", return_value=mock_backend):
        # Test sign method - should raise RuntimeError when list is empty
        with pytest.raises(RuntimeError, match="No signed URL generated"):
            obj.sign(expires_in=3600)


@pytest.mark.asyncio
async def test_sign_async_empty_result_list() -> None:
    """Test sign_async method when backend returns an empty list."""
    # Create a FileObject
    obj = FileObject(backend="mock", filename="test.txt")

    # Create a mock backend
    mock_backend = Mock(spec=StorageBackend)
    mock_backend.key = "mock"
    mock_backend.sign_async = AsyncMock(return_value=[])  # Empty list

    # Patch the storages.get_backend method to return our mock backend
    with patch("advanced_alchemy.types.file_object.storages.get_backend", return_value=mock_backend):
        # Test sign_async method - should raise RuntimeError when list is empty
        with pytest.raises(RuntimeError, match="No signed URL generated"):
            await obj.sign_async(expires_in=3600)


def test_file_object_initialization() -> None:
    """Test FileObject initialization with different parameters."""
    # Test with minimal parameters
    obj = FileObject(backend="mock", filename="test.txt")
    assert obj.filename == "test.txt"
    assert obj.path == "test.txt"  # When to_filename is not provided, path defaults to filename

    # Test with to_filename
    obj = FileObject(backend="mock", filename="original.txt", to_filename="destination.txt")
    assert obj.filename == "destination.txt"  # filename property returns path
    assert obj.path == "destination.txt"

    # Test with content_type
    obj = FileObject(backend="mock", filename="test.txt", content_type="text/plain")
    assert obj.content_type == "text/plain"

    # Test with metadata
    obj = FileObject(backend="mock", filename="test.txt", metadata={"category": "test"})
    assert obj.metadata == {"category": "test"}


def test_file_object_to_dict() -> None:
    """Test to_dict method of FileObject."""
    # Create a FileObject with metadata
    obj = FileObject(
        backend="mock",
        filename="test.txt",
        size=100,
        content_type="text/plain",
        last_modified=1234567890.0,
        checksum="abc123",
        etag="xyz789",
        version_id="v1",
        metadata={"category": "test"},
    )

    # Create a mock backend
    mock_backend = Mock(spec=StorageBackend)
    mock_backend.key = "mock_backend"  # Set as an attribute, not a property

    # Patch the storages.get_backend method to return our mock backend
    with patch("advanced_alchemy.types.file_object.storages.get_backend", return_value=mock_backend):
        # Convert to dict
        obj_dict = obj.to_dict()

        # Verify the dict contains the expected values
        assert obj_dict == {
            "filename": "test.txt",
            "content_type": "text/plain",
            "size": 100,
            "last_modified": 1234567890.0,
            "checksum": "abc123",
            "etag": "xyz789",
            "version_id": "v1",
            "metadata": {"category": "test"},
            "backend": "mock_backend",
        }


def test_file_object_update_metadata() -> None:
    """Test update_metadata method of FileObject."""
    # Create a FileObject with initial metadata
    obj = FileObject(backend="mock", filename="test.txt", metadata={"category": "document", "tags": ["important"]})

    # Update metadata
    obj.update_metadata({"priority": "high", "tags": ["urgent"]})

    # Verify metadata was updated correctly
    assert obj.metadata == {
        "category": "document",
        "tags": ["urgent"],  # Tags should be replaced, not appended
        "priority": "high",  # New field should be added
    }


def test_file_object_repr() -> None:
    """Test __repr__ method of FileObject."""
    # Create a FileObject with all attributes
    obj = FileObject(
        backend="mock",
        filename="test.txt",
        size=100,
        content_type="text/plain",
        last_modified=1234567890.0,
        etag="etag123",
        version_id="v1",
    )

    # Mock the backend to have a key attribute
    mock_backend = Mock()
    mock_backend.key = "mock_backend"

    # Patch the storages.get_backend method to return our mock backend
    with patch("advanced_alchemy.types.file_object.storages.get_backend", return_value=mock_backend):
        # Get the string representation
        repr_str = repr(obj)

        # Verify it contains expected information
        assert "FileObject" in repr_str
        assert "filename=test.txt" in repr_str
        assert "backend=mock_backend" in repr_str
        assert "size=100" in repr_str
        assert "content_type=text/plain" in repr_str
        assert "etag=etag123" in repr_str
        assert "last_modified=1234567890.0" in repr_str
        assert "version_id=v1" in repr_str


def test_file_object_equality() -> None:
    """Test __eq__ and __hash__ methods of FileObject."""
    # Create a basic equality test by using direct instances
    obj1 = FileObject(backend="mock", filename="test.txt")

    # Create a different object with same path
    obj2 = FileObject(backend="mock", filename="test.txt")

    # Create an object with different path
    obj3 = FileObject(backend="mock", filename="other.txt")

    # Test basic __eq__ behavior (two instances with same values)
    with patch("advanced_alchemy.types.file_object.storages.get_backend") as mock_get_backend:
        # The first two instances should be equal with same backend and path
        mock_get_backend.return_value = Mock(spec=StorageBackend, key="same_key")
        assert obj1 == obj2

        # Test inequality with different paths (same backend)
        assert obj1 != obj3

        # Compare with a non-FileObject type
        assert obj1 != "not a file object"


def test_file_object_equality_different_backends() -> None:
    """Test equality with different backends."""
    # Create two FileObjects with the same path but different backends
    obj1 = FileObject(backend="mock1", filename="test.txt")
    obj2 = FileObject(backend="mock2", filename="test.txt")

    # Create mocks for backends with different keys
    mock_backend1 = Mock(spec=StorageBackend)
    mock_backend1.key = "backend1"

    mock_backend2 = Mock(spec=StorageBackend)
    mock_backend2.key = "backend2"

    # Use a mock dictionary for get_backend
    mock_backends = {"mock1": mock_backend1, "mock2": mock_backend2}

    # Patch the get_backend method to return the appropriate mock
    with patch("advanced_alchemy.types.file_object.storages.get_backend", side_effect=lambda key: mock_backends[key]):  # type: ignore
        # Files with same path but different backends should not be equal
        assert obj1 != obj2


def test_file_object_content_type_guessing() -> None:
    """Test content_type guessing from filename."""
    # Test common file extensions
    file_types = {
        "test.txt": "text/plain",
        "image.jpg": "image/jpeg",
        "doc.pdf": "application/pdf",
        "data.json": "application/json",
        "script.py": "text/x-python",
        "unknown": "application/octet-stream",  # No extension
    }

    for filename, expected_type in file_types.items():
        obj = FileObject(backend="mock", filename=filename)
        assert obj.content_type == expected_type


def test_file_object_save_no_data() -> None:
    """Test save method with no data."""
    # Create a FileObject with no content or source_path
    obj = FileObject(backend="mock", filename="test.txt")

    # Saving with no data should raise a TypeError
    with pytest.raises(TypeError, match=r"No data provided and no pending content/path found to save."):
        obj.save()


@pytest.mark.asyncio
async def test_file_object_save_async_no_data() -> None:
    """Test save_async method with no data."""
    # Create a FileObject with no content or source_path
    obj = FileObject(backend="mock", filename="test.txt")

    # Saving with no data should raise a TypeError
    with pytest.raises(TypeError, match=r"No data provided and no pending content/path found to save."):
        await obj.save_async()


def test_file_object_save_with_content() -> None:
    """Test save method with content provided in constructor."""
    # Create content
    test_content = b"Test content"

    # Create a FileObject with content
    obj = FileObject(backend="mock", filename="test.txt", content=test_content)

    # Verify object has pending data before save
    assert obj.has_pending_data

    # Mock the backend's save_object method
    mock_backend = Mock(spec=StorageBackend)
    mock_backend.key = "mock"
    mock_backend.save_object.return_value = obj  # Return the same object

    # Patch the storages.get_backend method to return our mock backend
    with patch("advanced_alchemy.types.file_object.storages.get_backend", return_value=mock_backend):
        # Call save method
        result = obj.save()

        # Verify the backend's save_object method was called
        assert mock_backend.save_object.called

        # Verify the method returns the updated object
        assert result is obj

        # Verify the pending content was cleared
        assert not obj.has_pending_data


@pytest.mark.asyncio
async def test_file_object_save_async_with_content() -> None:
    """Test save_async method with content provided in constructor."""
    # Create content
    test_content = b"Test async content"

    # Create a FileObject with content
    obj = FileObject(backend="mock", filename="test.txt", content=test_content)

    # Verify object has pending data before save
    assert obj.has_pending_data

    # Mock the backend's save_object_async method
    mock_backend = Mock(spec=StorageBackend)
    mock_backend.key = "mock"
    mock_backend.save_object_async = AsyncMock(return_value=obj)  # Return the same object

    # Patch the storages.get_backend method to return our mock backend
    with patch("advanced_alchemy.types.file_object.storages.get_backend", return_value=mock_backend):
        # Call save_async method
        result = await obj.save_async()

        # Verify the backend's save_object_async method was called
        assert mock_backend.save_object_async.called

        # Verify the method returns the updated object
        assert result is obj

        # Verify the pending content was cleared
        assert not obj.has_pending_data


def test_file_object_get_content() -> None:
    """Test get_content method."""
    # Create expected content
    test_content = b"Test content for get_content"

    # Create a FileObject
    obj = FileObject(backend="mock", filename="test.txt")

    # Mock the backend's get_content method
    mock_backend = Mock(spec=StorageBackend)
    mock_backend.key = "mock"
    mock_backend.get_content.return_value = test_content

    # Patch the storages.get_backend method to return our mock backend
    with patch("advanced_alchemy.types.file_object.storages.get_backend", return_value=mock_backend):
        # Call get_content method
        content = obj.get_content()

        # Verify the backend's get_content method was called with the right parameters
        mock_backend.get_content.assert_called_once_with(obj.path, options=None)

        # Verify the content returned matches the expected content
        assert content == test_content

        # Test with options
        options = {"option1": "value1"}
        content = obj.get_content(options=options)
        mock_backend.get_content.assert_called_with(obj.path, options=options)


@pytest.mark.asyncio
async def test_file_object_get_content_async() -> None:
    """Test get_content_async method."""
    # Create expected content
    test_content = b"Test content for get_content_async"

    # Create a FileObject
    obj = FileObject(backend="mock", filename="test.txt")

    # Mock the backend's get_content_async method
    mock_backend = Mock(spec=StorageBackend)
    mock_backend.key = "mock"
    mock_backend.get_content_async = AsyncMock(return_value=test_content)

    # Patch the storages.get_backend method to return our mock backend
    with patch("advanced_alchemy.types.file_object.storages.get_backend", return_value=mock_backend):
        # Call get_content_async method
        content = await obj.get_content_async()

        # Verify the backend's get_content_async method was called with the right parameters
        mock_backend.get_content_async.assert_called_once_with(obj.path, options=None)

        # Verify the content returned matches the expected content
        assert content == test_content

        # Test with options
        options = {"option1": "value1"}
        content = await obj.get_content_async(options=options)
        mock_backend.get_content_async.assert_called_with(obj.path, options=options)


def test_file_object_delete() -> None:
    """Test delete method."""
    # Create a FileObject
    obj = FileObject(backend="mock", filename="test.txt")

    # Mock the backend's delete_object method
    mock_backend = Mock(spec=StorageBackend)
    mock_backend.key = "mock"

    # Patch the storages.get_backend method to return our mock backend
    with patch("advanced_alchemy.types.file_object.storages.get_backend", return_value=mock_backend):
        # Call delete method
        obj.delete()

        # Verify the backend's delete_object method was called with the right parameters
        mock_backend.delete_object.assert_called_once_with(obj.path)


@pytest.mark.asyncio
async def test_file_object_delete_async() -> None:
    """Test delete_async method."""
    # Create a FileObject
    obj = FileObject(backend="mock", filename="test.txt")

    # Mock the backend's delete_object_async method
    mock_backend = Mock(spec=StorageBackend)
    mock_backend.key = "mock"
    mock_backend.delete_object_async = AsyncMock()

    # Patch the storages.get_backend method to return our mock backend
    with patch("advanced_alchemy.types.file_object.storages.get_backend", return_value=mock_backend):
        # Call delete_async method
        await obj.delete_async()

        # Verify the backend's delete_object_async method was called with the right parameters
        mock_backend.delete_object_async.assert_called_once_with(obj.path)


def test_file_object_sign() -> None:
    """Test sign method with non-list return value."""
    # Create a FileObject
    obj = FileObject(backend="mock", filename="test.txt")

    # Mock the backend's sign method to return a string
    mock_backend = Mock(spec=StorageBackend)
    mock_backend.key = "mock"
    mock_backend.sign.return_value = "signed-url"

    # Patch the storages.get_backend method to return our mock backend
    with patch("advanced_alchemy.types.file_object.storages.get_backend", return_value=mock_backend):
        # Call sign method
        url = obj.sign(expires_in=3600)

        # Verify the backend's sign method was called with the right parameters
        mock_backend.sign.assert_called_once_with(obj.path, expires_in=3600, for_upload=False)

        # Verify the url returned matches the expected url
        assert url == "signed-url"

        # Test with for_upload=True
        url = obj.sign(for_upload=True)
        mock_backend.sign.assert_called_with(obj.path, expires_in=None, for_upload=True)


@pytest.mark.asyncio
async def test_file_object_sign_async() -> None:
    """Test sign_async method with non-list return value."""
    # Create a FileObject
    obj = FileObject(backend="mock", filename="test.txt")

    # Mock the backend's sign_async method to return a string
    mock_backend = Mock(spec=StorageBackend)
    mock_backend.key = "mock"
    mock_backend.sign_async = AsyncMock(return_value="signed-url-async")

    # Patch the storages.get_backend method to return our mock backend
    with patch("advanced_alchemy.types.file_object.storages.get_backend", return_value=mock_backend):
        # Call sign_async method
        url = await obj.sign_async(expires_in=3600)

        # Verify the backend's sign_async method was called with the right parameters
        mock_backend.sign_async.assert_called_once_with(obj.path, expires_in=3600, for_upload=False)

        # Verify the url returned matches the expected url
        assert url == "signed-url-async"

        # Test with for_upload=True
        url = await obj.sign_async(for_upload=True)
        mock_backend.sign_async.assert_called_with(obj.path, expires_in=None, for_upload=True)


def test_file_object_has_pending_data() -> None:
    """Test has_pending_data property."""
    # Create a FileObject with no pending data
    obj1 = FileObject(backend="mock", filename="test1.txt")
    assert not obj1.has_pending_data

    # Create a FileObject with pending content
    obj2 = FileObject(backend="mock", filename="test2.txt", content=b"pending content")
    assert obj2.has_pending_data

    # Create a FileObject with pending source_path
    obj3 = FileObject(backend="mock", filename="test3.txt", source_path=Path("source.txt"))
    assert obj3.has_pending_data


def test_file_object_incompatible_init() -> None:
    """Test incompatible initialization parameters."""
    # Cannot provide both content and source_path
    with pytest.raises(ValueError, match="Cannot provide both 'source_content' and 'source_path'"):
        FileObject(backend="mock", filename="test.txt", content=b"Test content", source_path=Path("source.txt"))


@pytest.mark.asyncio
async def test_file_object_sign_async_empty_result_list() -> None:
    """Test sign_async method when backend returns an empty list."""
    # Create a FileObject
    obj = FileObject(backend="mock", filename="test.txt")

    # Create a mock backend
    mock_backend = Mock(spec=StorageBackend)
    mock_backend.key = "mock"
    mock_backend.sign_async = AsyncMock(return_value=[])  # Empty list

    # Patch the storages.get_backend method to return our mock backend
    with patch("advanced_alchemy.types.file_object.storages.get_backend", return_value=mock_backend):
        # Test sign_async method - should raise RuntimeError when list is empty
        with pytest.raises(RuntimeError, match="No signed URL generated"):
            await obj.sign_async(expires_in=3600)


@pytest.mark.skipif(not PYDANTIC_INSTALLED, reason="Pydantic v2 not installed")
def test_pydantic_serialization() -> None:
    """Test serialization of FileObject within a Pydantic model."""

    class FileModel(BaseModel):  # type: ignore[valid-type, misc]
        file: FileObject

    file_obj = FileObject(
        backend="mock",
        filename="test.txt",
        size=100,
        content_type="text/plain",
        last_modified=1234567890.0,
        etag="etag123",
        version_id="v1",
        metadata={"key": "value"},
    )
    model = FileModel(file=file_obj)

    # Mock backend for serialization
    mock_backend = Mock(spec=StorageBackend)
    mock_backend.key = "mock_backend_key"
    with patch("advanced_alchemy.types.file_object.storages.get_backend", return_value=mock_backend):
        serialized_data = model.model_dump()

        # Check if the serialized data matches the output of to_dict()
        expected_dict = {
            "filename": "test.txt",
            "content_type": "text/plain",
            "size": 100,
            "last_modified": 1234567890.0,
            "checksum": None,
            "etag": "etag123",
            "version_id": "v1",
            "metadata": {"key": "value"},
            "backend": "mock_backend_key",  # Expect backend key here
        }
        assert serialized_data == {"file": expected_dict}


@pytest.mark.skipif(not PYDANTIC_INSTALLED, reason="Pydantic v2 not installed")
def test_pydantic_validation_from_dict() -> None:
    """Test validation of a dictionary into FileObject via Pydantic."""

    class FileModel(BaseModel):  # type: ignore[valid-type, misc]
        file: FileObject

    input_dict = {
        "filename": "validated.txt",
        "backend": "mock_validate",
        "size": 200,
        "content_type": "image/png",
        "etag": "etag_validate",
        "metadata": {"source": "validation"},
    }

    # Mock backend for validation lookup
    mock_backend = Mock(spec=StorageBackend)
    mock_backend.key = "mock_validate"
    with patch("advanced_alchemy.types.file_object.storages.get_backend", return_value=mock_backend):
        model = FileModel(file=input_dict)  # type: ignore[arg-type]

        # Verify the created FileObject instance
        assert isinstance(model.file, FileObject)
        assert model.file.filename == "validated.txt"
        assert model.file.backend == mock_backend  # Backend should be resolved instance
        assert model.file.size == 200
        assert model.file.content_type == "image/png"
        assert model.file.etag == "etag_validate"
        assert model.file.metadata == {"source": "validation"}


@pytest.mark.skipif(not PYDANTIC_INSTALLED, reason="Pydantic v2 not installed")
def test_pydantic_validation_from_instance() -> None:
    """Test validation when providing an existing FileObject instance."""

    class FileModel(BaseModel):  # type: ignore[valid-type, misc]
        file: FileObject

    file_obj = FileObject(backend="instance_mock", filename="instance.txt")
    mock_backend = Mock(spec=StorageBackend)
    mock_backend.key = "instance_mock"

    with patch("advanced_alchemy.types.file_object.storages.get_backend", return_value=mock_backend):
        model = FileModel(file=file_obj)
        assert model.file is file_obj  # Should accept the instance directly


@pytest.mark.skipif(not PYDANTIC_INSTALLED, reason="Pydantic v2 not installed")
def test_pydantic_validation_error_missing_filename() -> None:
    """Test Pydantic validation error for missing filename."""
    from pydantic import ValidationError

    class FileModel(BaseModel):  # type: ignore[valid-type, misc]
        file: FileObject

    input_dict = {
        "backend": "mock_error",
        "size": 100,
    }
    with pytest.raises(ValidationError, match="filename"):  # type: ignore[call-arg]
        FileModel(file=input_dict)  # type: ignore[arg-type]


@pytest.mark.skipif(not PYDANTIC_INSTALLED, reason="Pydantic v2 not installed")
def test_pydantic_validation_error_missing_backend() -> None:
    """Test Pydantic validation error for missing backend."""
    from pydantic import ValidationError

    class FileModel(BaseModel):  # type: ignore[valid-type, misc]
        file: FileObject

    input_dict = {
        "filename": "no_backend.txt",
        "size": 100,
    }
    with pytest.raises(ValidationError, match="backend"):  # type: ignore
        FileModel(file=input_dict)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_session_tracker_commit_async_reraises_base_exceptions() -> None:
    """Ensure async commit re-raises non-Exception BaseException instances."""
    tracker = FileObjectSessionTracker()
    file_obj = Mock(spec=FileObject)
    file_obj.path = "tmp"
    file_obj.save_async = AsyncMock(side_effect=asyncio.CancelledError())

    tracker.add_pending_save(file_obj, b"payload")

    with pytest.raises(asyncio.CancelledError):
        await tracker.commit_async()

    file_obj.save_async.assert_awaited_once_with(b"payload")


def test_session_tracker_commit_ignores_file_not_found_on_delete_sync() -> None:
    """Sync commit should ignore FileNotFoundError from delete."""
    tracker = FileObjectSessionTracker()
    file_obj = Mock(spec=FileObject)
    file_obj.path = "tmp"
    file_obj.delete.side_effect = FileNotFoundError()

    tracker.add_pending_delete(file_obj)

    tracker.commit()  # should not raise
    file_obj.delete.assert_called_once_with()


def test_session_tracker_add_pending_delete_ignores_none_path() -> None:
    """Objects with no path are not added to pending deletes."""
    tracker = FileObjectSessionTracker()
    file_obj = Mock(spec=FileObject)
    file_obj.path = None

    tracker.add_pending_delete(file_obj)

    assert file_obj not in tracker.pending_deletes


def test_session_tracker_rollback_ignores_file_not_found_sync() -> None:
    """Rollback ignores FileNotFoundError from delete in sync path."""
    tracker = FileObjectSessionTracker()
    obj = Mock(spec=FileObject)
    obj.path = "tmp"
    obj.delete.side_effect = FileNotFoundError()

    tracker._saved_in_transaction.add(obj)

    tracker.rollback()  # should not raise
    obj.delete.assert_called_once_with()


@pytest.mark.asyncio
async def test_session_tracker_rollback_async_ignores_file_not_found() -> None:
    """Rollback ignores FileNotFoundError from delete in async path."""
    tracker = FileObjectSessionTracker()
    obj = Mock(spec=FileObject)
    obj.path = "tmp"
    obj.delete_async = AsyncMock(side_effect=FileNotFoundError())

    tracker._saved_in_transaction.add(obj)

    await tracker.rollback_async()  # should not raise
    obj.delete_async.assert_awaited_once_with()


def test_session_tracker_commit_multiple_saves_then_rollback_deletes_successful_ones() -> None:
    """Sync commit failure after some saves should allow rollback to delete saved ones."""
    tracker = FileObjectSessionTracker(raise_on_error=True)
    obj1 = Mock(spec=FileObject)
    obj1.path = "p1"
    obj1.save.return_value = None
    obj2 = Mock(spec=FileObject)
    obj2.path = "p2"
    obj2.save.side_effect = RuntimeError("boom2")

    tracker.add_pending_save(obj1, b"a")
    tracker.add_pending_save(obj2, b"b")

    with pytest.raises(RuntimeError, match="boom2"):
        tracker.commit()

    # first save recorded, second failed
    assert obj1 in tracker._saved_in_transaction
    assert obj2 not in tracker._saved_in_transaction

    # rollback deletes the saved file
    tracker.rollback()
    obj1.delete.assert_called_once_with()


@pytest.mark.asyncio
async def test_session_tracker_commit_async_multiple_saves_raises_first_and_rollback_deletes_success() -> None:
    """Async commit raises first failure; rollback deletes successful saves."""
    tracker = FileObjectSessionTracker(raise_on_error=True)
    ok = Mock(spec=FileObject)
    ok.path = "ok"
    ok.save_async = AsyncMock(return_value=None)
    bad = Mock(spec=FileObject)
    bad.path = "bad"
    bad.save_async = AsyncMock(side_effect=RuntimeError("first failure"))

    tracker.add_pending_save(ok, b"ok")
    tracker.add_pending_save(bad, b"bad")

    with pytest.raises(RuntimeError, match="first failure"):
        await tracker.commit_async()

    # success recorded despite overall failure
    assert ok in tracker._saved_in_transaction
    # rollback deletes the successful one
    await tracker.rollback_async()
    ok.delete_async.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_session_tracker_commit_async_raises_first_save_exception_in_order() -> None:
    """When multiple saves fail, an ExceptionGroup is raised with all failures."""
    tracker = FileObjectSessionTracker(raise_on_error=True)
    a = Mock(spec=FileObject)
    a.path = "a"
    a.save_async = AsyncMock(side_effect=RuntimeError("first"))
    b = Mock(spec=FileObject)
    b.path = "b"
    b.save_async = AsyncMock(side_effect=RuntimeError("second"))

    tracker.add_pending_save(a, b"x")
    tracker.add_pending_save(b, b"y")

    # Multiple errors raise ExceptionGroup
    with pytest.raises(ExceptionGroup, match="multiple FileObject operation failures"):
        await tracker.commit_async()


@pytest.mark.asyncio
async def test_session_tracker_commit_async_logs_exc_info_on_save_error(caplog: "pytest.LogCaptureFixture") -> None:
    """Async save errors are logged with exc_info for stack traces."""
    tracker = FileObjectSessionTracker(raise_on_error=True)
    obj = Mock(spec=FileObject)
    obj.path = "tmp"
    obj.save_async = AsyncMock(side_effect=RuntimeError("fail"))

    tracker.add_pending_save(obj, b"data")

    with caplog.at_level(logging.ERROR):
        with pytest.raises(RuntimeError):
            await tracker.commit_async()

    # Find our error record and assert exc_info present
    err_records = [r for r in caplog.records if "error saving file" in r.message]
    assert err_records and any(rec.exc_info for rec in err_records)


def test_session_tracker_commit_delete_exceptions_sync(
    caplog: "pytest.LogCaptureFixture",
) -> None:
    """Parametrized-like table: sync delete exceptions behavior."""
    tracker = FileObjectSessionTracker(raise_on_error=True)

    cases = [
        (FileNotFoundError(), None, False),
        (RuntimeError("boom"), RuntimeError, True),
        (asyncio.CancelledError(), asyncio.CancelledError, False),
    ]

    for exc, expected_exc, expect_log in cases:
        file_obj = Mock(spec=FileObject)
        file_obj.path = "tmp"
        file_obj.delete.side_effect = exc
        tracker.add_pending_delete(file_obj)

        with caplog.at_level(logging.ERROR):
            if expected_exc is None:
                tracker.commit()
            else:
                with pytest.raises(expected_exc):
                    tracker.commit()

        file_obj.delete.assert_called_once_with()
        if expect_log:
            assert any("error deleting file" in r.message for r in caplog.records)
        else:
            assert not any("error deleting file" in r.message for r in caplog.records)

        # reset tracker for next case
        tracker.clear()
        caplog.clear()


def test_session_tracker_commit_save_exceptions_sync(caplog: "pytest.LogCaptureFixture") -> None:
    """Sync save exceptions: RuntimeError logs+raises; BaseException bubbles without log."""
    tracker = FileObjectSessionTracker(raise_on_error=True)

    cases = [
        (RuntimeError("sync failure"), RuntimeError, True),
        (asyncio.CancelledError(), asyncio.CancelledError, False),
    ]

    for exc, expected_exc, expect_log in cases:
        file_obj = Mock(spec=FileObject)
        file_obj.path = "tmp"
        file_obj.save.side_effect = exc
        tracker.add_pending_save(file_obj, b"payload")

        with caplog.at_level(logging.ERROR):
            with pytest.raises(expected_exc):
                tracker.commit()

        file_obj.save.assert_called_once_with(b"payload")
        if expect_log:
            assert any("error saving file" in r.message for r in caplog.records)
        else:
            assert not any("error saving file" in r.message for r in caplog.records)

        tracker.clear()
        caplog.clear()


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["sync", "async"])
async def test_session_tracker_commit_does_not_clear_state_on_error(mode: str) -> None:
    """Commit keeps pending items when a save fails (sync and async)."""
    tracker = FileObjectSessionTracker(raise_on_error=True)
    obj = Mock(spec=FileObject)
    obj.path = "tmp"
    if mode == "sync":
        obj.save.side_effect = RuntimeError("boom")
        tracker.add_pending_save(obj, b"data")
        with pytest.raises(RuntimeError):
            tracker.commit()
    else:
        obj.save_async = AsyncMock(side_effect=RuntimeError("boom"))
        tracker.add_pending_save(obj, b"data")
        with pytest.raises(RuntimeError):
            await tracker.commit_async()

    assert obj in tracker.pending_saves


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["sync", "async"])
async def test_session_tracker_commit_clears_state_on_success(mode: str) -> None:
    """Commit clears state after successful operations (sync and async)."""
    tracker = FileObjectSessionTracker()
    save_obj = Mock(spec=FileObject)
    save_obj.path = "tmp1"
    del_obj = Mock(spec=FileObject)
    del_obj.path = "tmp2"

    if mode == "sync":
        save_obj.save.return_value = None
        del_obj.delete.return_value = None
        tracker.add_pending_save(save_obj, b"data")
        tracker.add_pending_delete(del_obj)
        tracker.commit()
    else:
        save_obj.save_async = AsyncMock(return_value=None)
        del_obj.delete_async = AsyncMock(return_value=None)
        tracker.add_pending_save(save_obj, b"data")
        tracker.add_pending_delete(del_obj)
        await tracker.commit_async()

    assert not tracker.pending_saves
    assert not tracker.pending_deletes
    assert not tracker._saved_in_transaction


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode, expect_delete_called",
    [("sync", False), ("async", True)],
)
async def test_session_tracker_commit_delete_attempt_when_save_fails(mode: str, expect_delete_called: bool) -> None:
    """Sync commit aborts before deletes; async still attempts deletes on gather."""
    tracker = FileObjectSessionTracker(raise_on_error=True)
    save_obj = Mock(spec=FileObject)
    save_obj.path = "tmp1"
    del_obj = Mock(spec=FileObject)
    del_obj.path = "tmp2"

    tracker.add_pending_save(save_obj, b"data")
    tracker.add_pending_delete(del_obj)

    if mode == "sync":
        save_obj.save.side_effect = RuntimeError("save failed")
        with pytest.raises(RuntimeError):
            tracker.commit()
        assert del_obj.delete.call_count == (1 if expect_delete_called else 0)
    else:
        save_obj.save_async = AsyncMock(side_effect=RuntimeError("save failed"))
        del_obj.delete_async = AsyncMock(return_value=None)
        with pytest.raises(RuntimeError):
            await tracker.commit_async()
        assert del_obj.delete_async.await_count == (1 if expect_delete_called else 0)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["sync", "async"])
async def test_session_tracker_rollback_reraises_delete_errors_param(
    mode: str, caplog: "pytest.LogCaptureFixture"
) -> None:
    """Rollback re-raises delete errors in both modes."""
    tracker = FileObjectSessionTracker()
    obj = Mock(spec=FileObject)
    obj.path = "tmp"
    tracker._saved_in_transaction.add(obj)

    if mode == "sync":
        obj.delete.side_effect = RuntimeError("rollback delete failure")
        with caplog.at_level(logging.ERROR):
            with pytest.raises(RuntimeError, match="rollback delete failure"):
                tracker.rollback()
        obj.delete.assert_called_once_with()
    else:
        obj.delete_async = AsyncMock(side_effect=RuntimeError("rollback async delete failure"))
        with caplog.at_level(logging.ERROR):
            with pytest.raises(RuntimeError, match="rollback async delete failure"):
                await tracker.rollback_async()
        obj.delete_async.assert_awaited_once_with()


@pytest.mark.parametrize(
    "ops, expected_in_saves, expected_in_deletes",
    [
        (("save", "delete"), False, True),
        (("delete", "save"), True, False),
    ],
)
def test_session_tracker_override_semantics(
    ops: "tuple[str, str]",
    expected_in_saves: bool,
    expected_in_deletes: bool,
) -> None:
    """Parametrized check that save/delete override each other appropriately."""
    tracker = FileObjectSessionTracker()
    file_obj = Mock(spec=FileObject)
    file_obj.path = "tmp"

    first, second = ops
    if first == "save":
        tracker.add_pending_save(file_obj, b"data")
    else:
        tracker.add_pending_delete(file_obj)

    if second == "save":
        tracker.add_pending_save(file_obj, b"data")
    else:
        tracker.add_pending_delete(file_obj)

    assert (file_obj in tracker.pending_saves) is expected_in_saves
    assert (file_obj in tracker.pending_deletes) is expected_in_deletes


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "exc_factory, expected_exception, expect_log",
    [
        (lambda: RuntimeError("delete boom"), RuntimeError, True),
        (lambda: FileNotFoundError(), None, False),
        (lambda: asyncio.CancelledError(), asyncio.CancelledError, False),
    ],
)
async def test_session_tracker_commit_async_delete_exceptions(
    caplog: "pytest.LogCaptureFixture",
    exc_factory: "Callable[[], BaseException]",
    expected_exception: "Optional[type[BaseException]]",
    expect_log: bool,
) -> None:
    """Parametrized verification of async delete exception handling semantics."""
    tracker = FileObjectSessionTracker(raise_on_error=True)
    file_obj = Mock(spec=FileObject)
    file_obj.path = "tmp"
    file_obj.delete_async = AsyncMock(side_effect=exc_factory())

    tracker.add_pending_delete(file_obj)

    with caplog.at_level(logging.ERROR):
        if expected_exception is None:
            await tracker.commit_async()
        else:
            with pytest.raises(expected_exception):
                await tracker.commit_async()

    file_obj.delete_async.assert_awaited_once_with()
    if expect_log:
        assert any("error deleting file" in r.message for r in caplog.records)
    else:
        assert not any("error deleting file" in r.message for r in caplog.records)


# --- FileObject Listener Tests (from _listeners module) ---


def test_file_object_inspector_inspect_instance_no_state() -> None:
    """Test FileObjectInspector when inspect returns None."""
    from advanced_alchemy._listeners import FileObjectInspector

    instance = MagicMock()
    tracker = MagicMock()
    # Mock inspect to return None
    with patch("advanced_alchemy._listeners.inspect", return_value=None):
        FileObjectInspector.inspect_instance(instance, tracker)
        # Should return early, no exception


def test_file_object_inspector_inspect_instance_no_mapper() -> None:
    """Test FileObjectInspector when state has no mapper."""
    from advanced_alchemy._listeners import FileObjectInspector

    instance = MagicMock()
    tracker = MagicMock()
    mock_state = MagicMock()
    mock_state.mapper = None

    with patch("advanced_alchemy._listeners.inspect", return_value=mock_state):
        FileObjectInspector.inspect_instance(instance, tracker)
        # Should return early


def test_file_object_inspector_inspect_instance_key_error() -> None:
    """Test FileObjectInspector handles KeyError gracefully."""
    from advanced_alchemy._listeners import FileObjectInspector
    from advanced_alchemy.types.file_object import StoredObject

    instance = MagicMock()
    tracker = MagicMock()
    mock_state = MagicMock()
    mock_mapper = MagicMock()
    mock_state.mapper = mock_mapper

    mock_attr = MagicMock()
    mock_attr.expression.type = MagicMock(spec=StoredObject)

    mock_mapper.column_attrs = {"file_col": mock_attr}
    mock_state.attrs = {}  # Empty attrs, will trigger KeyError

    with patch("advanced_alchemy._listeners.inspect", return_value=mock_state):
        FileObjectInspector.inspect_instance(instance, tracker)
        # Should handle KeyError gracefully


def test_handle_single_attribute_added() -> None:
    """Test handling single attribute when file is added."""
    from advanced_alchemy._listeners import FileObjectInspector

    tracker = MagicMock(spec=FileObjectSessionTracker)
    attr_state = MagicMock()

    mock_file = MagicMock(spec=FileObject)
    mock_file._pending_source_content = b"content"
    mock_file._pending_source_path = None

    attr_state.history.added = [mock_file]
    attr_state.history.deleted = []

    FileObjectInspector.handle_single_attribute(attr_state, tracker)

    tracker.add_pending_save.assert_called_with(mock_file, b"content")


def test_handle_single_attribute_deleted() -> None:
    """Test handling single attribute when file is deleted."""
    from advanced_alchemy._listeners import FileObjectInspector

    tracker = MagicMock(spec=FileObjectSessionTracker)
    attr_state = MagicMock()

    mock_file = MagicMock(spec=FileObject)
    mock_file.path = "some/path"

    attr_state.history.added = []
    attr_state.history.deleted = [mock_file]

    FileObjectInspector.handle_single_attribute(attr_state, tracker)

    tracker.add_pending_delete.assert_called_with(mock_file)


def test_handle_multiple_attribute() -> None:
    """Test handling multiple attribute with deletion from pending removed."""
    from advanced_alchemy._listeners import FileObjectInspector
    from advanced_alchemy.types.mutables import MutableList

    tracker = MagicMock(spec=FileObjectSessionTracker)
    instance = MagicMock()
    attr_name = "files"
    attr_state = MagicMock()

    # Case: Deletion from pending removed
    current_list = MagicMock(spec=MutableList)
    deleted_item = MagicMock(spec=FileObject)
    deleted_item.path = "path/to/delete"
    current_list._pending_removed = {deleted_item}
    current_list._pending_append = []

    setattr(instance, attr_name, current_list)
    attr_state.history.deleted = []
    attr_state.history.added = []

    FileObjectInspector.handle_multiple_attribute(instance, attr_name, attr_state, tracker)

    tracker.add_pending_delete.assert_called_with(deleted_item)


def test_handle_multiple_attribute_replacement() -> None:
    """Test handling multiple attribute with list replacement."""
    from advanced_alchemy._listeners import FileObjectInspector

    tracker = MagicMock(spec=FileObjectSessionTracker)
    instance = MagicMock()
    attr_name = "files"
    attr_state = MagicMock()

    # Case: List replacement
    # Original list had item1, item2
    # New list has item2 (so item1 removed)
    item1 = MagicMock(spec=FileObject)
    item1.path = "p1"
    item2 = MagicMock(spec=FileObject)
    item2.path = "p2"

    # SQLAlchemy history.deleted contains the *value* that was deleted.
    # For a list assignment replacing the whole list, it might be [old_list].
    # The code expects history.deleted[0] to be the list.
    attr_state.history.deleted = [[item1, item2]]  # original list wrapped in list
    attr_state.history.added = [[item2]]  # new list wrapped in list

    # We must mock getattr(instance, attr_name) to return None or regular list
    setattr(instance, attr_name, [item2])

    FileObjectInspector.handle_multiple_attribute(instance, attr_name, attr_state, tracker)

    tracker.add_pending_delete.assert_called_with(item1)


def test_handle_multiple_attribute_append_and_new() -> None:
    """Test handling multiple attribute with appends and new items."""
    from advanced_alchemy._listeners import FileObjectInspector
    from advanced_alchemy.types.mutables import MutableList

    tracker = MagicMock(spec=FileObjectSessionTracker)
    instance = MagicMock()
    attr_name = "files"
    attr_state = MagicMock()

    current_list = MagicMock(spec=MutableList)
    current_list._pending_removed = set()

    item1 = MagicMock(spec=FileObject)
    item1.path = None
    item1._pending_content = b"d1"
    item1._pending_source_path = None
    # For item2, we want to test pending_source_path
    item2 = MagicMock(spec=FileObject)
    item2.path = None
    item2._pending_source_path = "p2"
    item2._pending_source_content = None

    current_list._pending_append = [item1]

    setattr(instance, attr_name, current_list)

    # Case: New items in history.added
    attr_state.history.deleted = []
    attr_state.history.added = [[item2]]

    FileObjectInspector.handle_multiple_attribute(instance, attr_name, attr_state, tracker)

    tracker.add_pending_save.assert_any_call(item1, b"d1")
    tracker.add_pending_save.assert_any_call(item2, "p2")


def test_process_deleted_instance() -> None:
    """Test processing a deleted instance for file cleanup."""
    from advanced_alchemy._listeners import FileObjectInspector
    from advanced_alchemy.types.file_object import StoredObject

    instance = MagicMock()
    tracker = MagicMock()
    mapper = MagicMock()

    mock_attr = MagicMock()
    mock_attr.expression.type = MagicMock(spec=StoredObject)
    mock_attr.expression.type.multiple = False

    mapper.column_attrs = {"file_col": mock_attr}

    file_obj = MagicMock()
    file_obj.path = "path"
    setattr(instance, "file_col", file_obj)

    FileObjectInspector.process_deleted_instance(instance, mapper, tracker)

    tracker.add_pending_delete.assert_called_with(file_obj)


def test_get_file_tracker_create() -> None:
    """Test get_file_tracker creates a new tracker."""
    from advanced_alchemy._listeners import get_file_tracker

    session = MagicMock(spec=Session)
    session.info = {}

    result = get_file_tracker(session, create=True)
    assert result is not None
    assert session.info["_aa_file_tracker"] is result


# --- BaseFileObjectListener Tests ---


def test_base_file_object_listener_is_listener_enabled_default() -> None:
    """Test BaseFileObjectListener enabled by default."""
    from advanced_alchemy._listeners import BaseFileObjectListener

    class TestBaseFileObjectListener(BaseFileObjectListener):
        pass

    session = MagicMock(spec=Session)
    session.info = {}
    session.bind = None
    session.execution_options = None

    assert TestBaseFileObjectListener._is_listener_enabled(session) is True


def test_base_file_object_listener_is_listener_enabled_session_info() -> None:
    """Test BaseFileObjectListener can be disabled via session info."""
    from advanced_alchemy._listeners import BaseFileObjectListener

    class TestBaseFileObjectListener(BaseFileObjectListener):
        pass

    session = MagicMock(spec=Session)
    session.info = {"enable_file_object_listener": False}

    assert TestBaseFileObjectListener._is_listener_enabled(session) is False


def test_base_file_object_listener_before_flush_disabled() -> None:
    """Test before_flush returns early when listener is disabled."""
    from advanced_alchemy._listeners import BaseFileObjectListener

    class TestBaseFileObjectListener(BaseFileObjectListener):
        pass

    session = MagicMock(spec=Session)
    session.info = {"enable_file_object_listener": False}

    TestBaseFileObjectListener.before_flush(session, MagicMock(), None)
    # Should return early
    assert "_aa_file_tracker" not in session.info


def test_base_file_object_listener_before_flush() -> None:
    """Test before_flush processes session objects."""
    from advanced_alchemy._listeners import BaseFileObjectListener

    class TestBaseFileObjectListener(BaseFileObjectListener):
        pass

    session = MagicMock(spec=Session)
    session.bind = MagicMock()
    session.info = {}
    session.new = []
    session.dirty = []
    session.deleted = []

    # Mock get_file_tracker to return a tracker
    with patch("advanced_alchemy._listeners.get_file_tracker") as mock_get_tracker:
        mock_tracker = MagicMock()
        mock_get_tracker.return_value = mock_tracker
        TestBaseFileObjectListener.before_flush(session, MagicMock(), None)


# --- SyncFileObjectListener Tests ---


def test_sync_file_object_listener_after_commit() -> None:
    """Test SyncFileObjectListener commits tracker on session commit."""
    from advanced_alchemy._listeners import SyncFileObjectListener

    session = MagicMock(spec=Session)
    tracker = MagicMock()
    session.info = {"_aa_file_tracker": tracker}

    SyncFileObjectListener.after_commit(session)

    tracker.commit.assert_called_once()
    assert "_aa_file_tracker" not in session.info


def test_sync_file_object_listener_after_rollback() -> None:
    """Test SyncFileObjectListener rolls back tracker on session rollback."""
    from advanced_alchemy._listeners import SyncFileObjectListener

    session = MagicMock(spec=Session)
    tracker = MagicMock()
    session.info = {"_aa_file_tracker": tracker}

    SyncFileObjectListener.after_rollback(session)

    tracker.rollback.assert_called_once()
    assert "_aa_file_tracker" not in session.info


# --- AsyncFileObjectListener Tests ---


@pytest.mark.asyncio
async def test_async_file_object_listener_after_commit() -> None:
    """Test AsyncFileObjectListener commits tracker asynchronously."""
    from advanced_alchemy._listeners import AsyncFileObjectListener, _active_file_operations

    session = MagicMock(spec=Session)
    tracker = MagicMock()
    tracker.commit_async = AsyncMock()
    session.info = {"_aa_file_tracker": tracker}

    AsyncFileObjectListener.after_commit(session)

    # Find the task and await it
    assert len(_active_file_operations) > 0
    task = next(iter(_active_file_operations))
    await task

    assert "_aa_file_tracker" not in session.info
    tracker.commit_async.assert_called_once()


@pytest.mark.asyncio
async def test_async_file_object_listener_after_rollback() -> None:
    """Test AsyncFileObjectListener rolls back tracker asynchronously."""
    from advanced_alchemy._listeners import AsyncFileObjectListener, _active_file_operations

    session = MagicMock(spec=Session)
    tracker = MagicMock()
    tracker.rollback_async = AsyncMock()
    session.info = {"_aa_file_tracker": tracker}

    AsyncFileObjectListener.after_rollback(session)

    # Find the task and await it
    assert len(_active_file_operations) > 0
    task = next(iter(_active_file_operations))
    await task

    assert "_aa_file_tracker" not in session.info
    tracker.rollback_async.assert_called_once()


# --- FileObjectListener (Legacy) Tests ---


def test_file_object_listener_legacy_sync() -> None:
    """Test legacy FileObjectListener in sync context."""
    from advanced_alchemy._listeners import FileObjectListener

    session = MagicMock(spec=Session)
    tracker = MagicMock()
    session.info = {"_aa_file_tracker": tracker}

    # patch is_async_context to return False
    with patch("advanced_alchemy._listeners.is_async_context", return_value=False):
        FileObjectListener.after_commit(session)
        tracker.commit.assert_called_once()

        session.info = {"_aa_file_tracker": tracker}  # put it back
        FileObjectListener.after_rollback(session)
        tracker.rollback.assert_called_once()


@pytest.mark.asyncio
async def test_file_object_listener_legacy_async() -> None:
    """Test legacy FileObjectListener in async context."""
    from advanced_alchemy._listeners import FileObjectListener, _active_file_operations

    session = MagicMock(spec=Session)
    tracker = MagicMock()
    tracker.commit_async = AsyncMock()
    tracker.rollback_async = AsyncMock()
    session.info = {"_aa_file_tracker": tracker}

    # patch is_async_context to return True
    with patch("advanced_alchemy._listeners.is_async_context", return_value=True):
        FileObjectListener.after_commit(session)

        # Await task
        if _active_file_operations:
            await next(iter(_active_file_operations))

        session.info = {"_aa_file_tracker": tracker}
        FileObjectListener.after_rollback(session)

        # Await task
        if _active_file_operations:
            for t in list(_active_file_operations):
                if not t.done():
                    await t


# --- Setup Tests ---


def test_setup_file_object_listeners() -> None:
    """Test setup_file_object_listeners registers event listeners."""
    from advanced_alchemy._listeners import setup_file_object_listeners

    with (
        patch("advanced_alchemy._listeners.event.listen") as mock_listen,
        patch("sqlalchemy.event.contains", return_value=False),
    ):
        setup_file_object_listeners()
        assert mock_listen.called


# --- Utility/Shared Tests ---


def test_touch_updated_timestamp() -> None:
    """Test touch_updated_timestamp updates timestamps on dirty instances."""
    import datetime

    from advanced_alchemy._listeners import touch_updated_timestamp

    session = MagicMock(spec=Session)
    instance = MagicMock()
    session.dirty = [instance]
    session.new = []

    with patch("advanced_alchemy._listeners.inspect") as mock_inspect:
        state = MagicMock()
        state.mapper.class_ = MagicMock()
        state.mapper.class_.updated_at = "exists"
        state.deleted = False

        # Mock updated_at attribute state
        attr_state = MagicMock()
        attr_state.history.added = []  # No manual update
        state.attrs.get.return_value = attr_state

        mock_inspect.return_value = state

        # Mock _has_persistent_column_changes to return True
        with patch("advanced_alchemy._listeners._has_persistent_column_changes", return_value=True):
            touch_updated_timestamp(session)

            # Verify instance.updated_at was set
            assert isinstance(instance.updated_at, datetime.datetime)


def test_has_persistent_column_changes() -> None:
    """Test _has_persistent_column_changes detects column modifications."""
    from advanced_alchemy._listeners import _has_persistent_column_changes

    state = MagicMock()
    mapper = MagicMock()
    attr = MagicMock()
    attr.key = "some_col"
    mapper.column_attrs = [attr]
    state.mapper = mapper

    attr_state = MagicMock()
    attr_state.history.has_changes.return_value = True
    state.attrs.get.return_value = attr_state

    assert _has_persistent_column_changes(state) is True


# --- Deprecation / Context Tests ---


def test_deprecated_context_functions() -> None:
    """Test deprecated async context functions emit warnings."""
    from advanced_alchemy._listeners import is_async_context, reset_async_context, set_async_context

    with pytest.warns(DeprecationWarning):
        set_async_context(True)

    with pytest.warns(DeprecationWarning):
        reset_async_context(None)

    with pytest.warns(DeprecationWarning):
        is_async_context()


def test_handle_multiple_attribute_finalize() -> None:
    """Test handling multiple attribute calls _finalize_pending."""
    from advanced_alchemy._listeners import FileObjectInspector
    from advanced_alchemy.types.mutables import MutableList

    tracker = MagicMock(spec=FileObjectSessionTracker)
    instance = MagicMock()
    attr_name = "files"
    attr_state = MagicMock()

    current_list = MagicMock(spec=MutableList)
    current_list._pending_removed = set()
    current_list._pending_append = []
    setattr(instance, attr_name, current_list)

    FileObjectInspector.handle_multiple_attribute(instance, attr_name, attr_state, tracker)

    assert current_list._finalize_pending.called


def test_handle_multiple_attribute_pending_save_branches() -> None:
    """Test branches in handle_multiple_attribute for pending saves."""
    from advanced_alchemy._listeners import FileObjectInspector
    from advanced_alchemy.types.mutables import MutableList

    tracker = MagicMock(spec=FileObjectSessionTracker)
    instance = MagicMock()
    attr_name = "files"
    attr_state = MagicMock()

    current_list = MagicMock(spec=MutableList)
    current_list._pending_removed = set()

    item1 = MagicMock(spec=FileObject)
    item1._pending_content = None
    item1._pending_source_path = "p1"

    current_list._pending_append = [item1]
    setattr(instance, attr_name, current_list)

    # item2 already in items_to_save (via history)
    item2 = MagicMock(spec=FileObject)
    item2._pending_source_content = b"d2"
    attr_state.history.added = [[item2]]
    attr_state.history.deleted = []

    FileObjectInspector.handle_multiple_attribute(instance, attr_name, attr_state, tracker)

    tracker.add_pending_save.assert_any_call(item1, "p1")
    tracker.add_pending_save.assert_any_call(item2, b"d2")


def test_process_deleted_instance_multiple() -> None:
    """Test process_deleted_instance with multiple items."""
    from advanced_alchemy._listeners import FileObjectInspector
    from advanced_alchemy.types.file_object import StoredObject
    from advanced_alchemy.types.mutables import MutableList

    instance = MagicMock()
    tracker = MagicMock()
    mapper = MagicMock()

    mock_attr = MagicMock()
    mock_attr.expression.type = MagicMock(spec=StoredObject)
    mock_attr.expression.type.multiple = True

    mapper.column_attrs = {"files_col": mock_attr}

    item1 = MagicMock(spec=FileObject)
    item2 = MagicMock(spec=FileObject)

    # Test with regular list
    setattr(instance, "files_col", [item1, item2])
    FileObjectInspector.process_deleted_instance(instance, mapper, tracker)
    tracker.add_pending_delete.assert_any_call(item1)
    tracker.add_pending_delete.assert_any_call(item2)

    # Test with MutableList
    tracker.reset_mock()
    m_list = MutableList[FileObject]([item1, item2])
    setattr(instance, "files_col", m_list)
    FileObjectInspector.process_deleted_instance(instance, mapper, tracker)
    tracker.add_pending_delete.assert_any_call(item1)
    tracker.add_pending_delete.assert_any_call(item2)


def test_is_listener_enabled_extended() -> None:
    """Test _is_listener_enabled with various option sources."""
    from advanced_alchemy._listeners import BaseFileObjectListener

    class TestListener(BaseFileObjectListener):
        pass

    session = MagicMock(spec=Session)
    session.info = {}

    # 1. Disable via session.bind.execution_options (dict)
    session.bind = MagicMock()
    session.bind.execution_options = {"enable_file_object_listener": False}
    assert TestListener._is_listener_enabled(session) is False

    # 2. Disable via session.bind.execution_options (callable)
    session.bind.execution_options = lambda: {"enable_file_object_listener": False}
    assert TestListener._is_listener_enabled(session) is False

    # 3. Disable via session.bind.sync_engine.execution_options
    session.bind.execution_options = None
    session.bind.sync_engine = MagicMock()
    session.bind.sync_engine.execution_options = {"enable_file_object_listener": False}
    assert TestListener._is_listener_enabled(session) is False

    # 4. Disable via session.execution_options (dict)
    session.bind = None
    session.execution_options = {"enable_file_object_listener": False}
    assert TestListener._is_listener_enabled(session) is False

    # 5. Disable via session.execution_options (callable)
    session.execution_options = lambda: {"enable_file_object_listener": False}
    assert TestListener._is_listener_enabled(session) is False

    # 6. Exception in callable execution_options
    def raising_options() -> None:
        raise ValueError("error")

    session.execution_options = raising_options
    # Should fallback to default True and not crash
    assert TestListener._is_listener_enabled(session) is True


@pytest.mark.asyncio
async def test_async_file_object_listener_error_handling(caplog: pytest.LogCaptureFixture) -> None:
    """Test error handling in AsyncFileObjectListener."""
    import logging

    from advanced_alchemy._listeners import AsyncFileObjectListener, _active_file_operations

    caplog.set_level(logging.DEBUG)
    session = MagicMock(spec=Session)
    tracker = MagicMock()
    tracker.commit_async = AsyncMock(side_effect=ValueError("commit error"))
    tracker.rollback_async = AsyncMock(side_effect=ValueError("rollback error"))
    session.info = {"_aa_file_tracker": tracker}

    # Test commit error
    caplog.clear()
    AsyncFileObjectListener.after_commit(session)
    while _active_file_operations:
        await asyncio.gather(*_active_file_operations)
    assert "An error occurred while committing a file object" in caplog.text

    # Test rollback error
    caplog.clear()
    session.info = {"_aa_file_tracker": tracker}
    AsyncFileObjectListener.after_rollback(session)
    while _active_file_operations:
        await asyncio.gather(*_active_file_operations)
    assert "An error occurred during async FileObject rollback" in caplog.text
