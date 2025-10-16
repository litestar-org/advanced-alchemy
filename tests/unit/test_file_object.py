"""Unit tests for FileObject class."""

import asyncio
import logging
from pathlib import Path
from unittest.mock import AsyncMock, Mock, PropertyMock, patch

import pytest

from advanced_alchemy.service.typing import PYDANTIC_INSTALLED, BaseModel
from advanced_alchemy.types.file_object import FileObject
from advanced_alchemy.types.file_object.base import StorageBackend
from advanced_alchemy.types.file_object.session_tracker import FileObjectSessionTracker


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
    tracker = FileObjectSessionTracker()
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
    tracker = FileObjectSessionTracker()
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
    """When multiple saves fail, the first in order is raised."""
    tracker = FileObjectSessionTracker()
    a = Mock(spec=FileObject)
    a.path = "a"
    a.save_async = AsyncMock(side_effect=RuntimeError("first"))
    b = Mock(spec=FileObject)
    b.path = "b"
    b.save_async = AsyncMock(side_effect=RuntimeError("second"))

    tracker.add_pending_save(a, b"x")
    tracker.add_pending_save(b, b"y")

    with pytest.raises(RuntimeError, match="first"):
        await tracker.commit_async()


@pytest.mark.asyncio
async def test_session_tracker_commit_async_logs_exc_info_on_save_error(caplog: "pytest.LogCaptureFixture") -> None:
    """Async save errors are logged with exc_info for stack traces."""
    tracker = FileObjectSessionTracker()
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
    tracker = FileObjectSessionTracker()

    # cases: (exception, expect_raise_type, expect_log)
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
    tracker = FileObjectSessionTracker()

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
    tracker = FileObjectSessionTracker()
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
    tracker = FileObjectSessionTracker()
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
async def test_session_tracker_rollback_reraises_delete_errors_param(mode: str, caplog: "pytest.LogCaptureFixture") -> None:
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
    exc_factory,
    expected_exception,
    expect_log: bool,
) -> None:
    """Parametrized verification of async delete exception handling semantics."""
    tracker = FileObjectSessionTracker()
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
