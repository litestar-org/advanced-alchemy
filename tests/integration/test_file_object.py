# ruff: noqa: PLC2701 DOC402 ANN201
import tempfile
from collections.abc import Generator
from pathlib import Path
from typing import Any, Optional

import pytest
from sqlalchemy import Engine, MetaData, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

# Assuming these imports point to the refactored code
from advanced_alchemy._listeners import setup_file_object_listeners
from advanced_alchemy.exceptions import MissingDependencyError
from advanced_alchemy.types.file_object import (
    FileObject,
    StoredObject,
)
from advanced_alchemy.types.file_object.backends.fsspec import FSSpecBackend
from advanced_alchemy.types.file_object.registry import StorageRegistry, storages
from advanced_alchemy.types.mutables import MutableList

pytestmark = pytest.mark.integration

# --- Fixtures ---


@pytest.fixture(scope="module")
def storage_registry() -> StorageRegistry:
    """Clears and returns the global storage registry for the module.

    Returns:
        StorageRegistry: The global storage registry.
    """
    storages.clear()  # Ensure clean slate for tests
    return storages


@pytest.fixture(scope="module")
def local_storage_backend(storage_registry: StorageRegistry) -> Generator[FSSpecBackend, None, None]:
    """Sets up a local FSSpecBackend and registers it.

    Args:
        storage_registry: The storage registry to register the backend with.

    Raises:
        MissingDependencyError: If fsspec is not installed.

    Yields:
        FSSpecBackend: The local FSSpecBackend instance.
    """
    try:
        from fsspec.implementations.local import LocalFileSystem
    except ImportError as e:
        raise MissingDependencyError("fsspec", "tests") from e

    temp_dir = tempfile.TemporaryDirectory()
    storage_path = Path(temp_dir.name) / "file_object_test_storage"
    storage_path.mkdir(parents=True, exist_ok=True)

    local_fs = LocalFileSystem(auto_mkdir=True)  # fsspec handles paths relative to root
    backend = FSSpecBackend(fs=local_fs, key="local_test_store")
    storage_registry.register_backend(backend)

    yield backend  # Provide the backend instance to tests

    temp_dir.cleanup()
    storage_registry.clear_backends()  # Clean up registry after tests


@pytest.fixture(scope="function")
def db_engine(tmp_path: Path) -> Generator[Engine, None, None]:
    """Provides an SQLite engine scoped to each function."""
    db_file = tmp_path / "test_file_object.db"
    engine = create_engine(f"sqlite:///{db_file}")
    yield engine
    db_file.unlink(missing_ok=True)


@pytest.fixture(scope="function")
def sqlalchemy_config(db_engine: Engine, storage_registry: StorageRegistry) -> Generator[None, None, None]:
    """Sets up listeners."""
    # Note: In a real app, this config would likely come from a central place
    setup_file_object_listeners(storage_registry)  # Setup listeners using the registry
    yield
    # Teardown listeners? SQLAlchemy event registry doesn't have a simple remove_all
    # For isolated tests, ensuring clean registry/DB per function is usually enough


@pytest.fixture(scope="function")
def session(
    db_engine: Engine, sqlalchemy_config: Any
) -> Generator[Session, None, None]:  # Depend on sqlalchemy_config to ensure setup runs
    """Provides a SQLAlchemy session scoped to each function."""
    Base.metadata.create_all(db_engine)
    with Session(db_engine) as db_session:
        yield db_session
    Base.metadata.drop_all(db_engine)


# --- SQLAlchemy Model Definition ---
class Base(DeclarativeBase):
    metadata = MetaData()


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50))
    # Single file storage
    attachment: Mapped[Optional[FileObject]] = mapped_column(
        StoredObject(storage_key="local_test_store"),
        nullable=True,
    )
    # Multiple file storage
    images: Mapped[Optional[MutableList[FileObject]]] = mapped_column(  # Use MutableList type hint
        StoredObject(storage_key="local_test_store", multiple=True),
        nullable=True,
    )


# --- Test Cases ---


@pytest.mark.anyio
async def test_save_retrieve_delete_content(local_storage_backend: FSSpecBackend) -> None:
    """Test basic save, get_content, delete via backend and FileObject."""
    backend = local_storage_backend
    test_content = b"Hello Storage!"
    file_path = "test_basic.txt"  # Relative path for the backend

    # Create initial FileObject
    obj = FileObject(filename="test_basic.txt", path=file_path)

    # Save using backend
    updated_obj = await backend.save_to_storage_async(obj, test_content)

    # Assert FileObject updated
    assert updated_obj is obj  # Should update in-place
    assert obj.path == file_path
    assert obj.filename == "test_basic.txt"
    assert obj.size == len(test_content)
    assert obj.backend is backend
    assert obj.protocol == "file"  # Based on LocalFileSystem

    # Retrieve content via FileObject method
    retrieved_content = await obj.get_content_async()
    assert retrieved_content == test_content

    # Delete via FileObject method
    await obj.delete_async()

    # Verify deletion (expect FileNotFoundError or similar from backend)
    with pytest.raises(FileNotFoundError):
        await backend.get_content_async(file_path)


@pytest.mark.anyio
async def test_sqlalchemy_single_file_persist(session: Session, local_storage_backend: FSSpecBackend) -> None:
    """Test saving and loading a model with a single StoredObject."""
    backend = local_storage_backend
    file_content = b"SQLAlchemy Integration Test"
    doc_name = "Integration Doc"
    file_path = "sqlalchemy_single.bin"

    # 1. Prepare FileObject and save via backend
    initial_obj = FileObject(filename="report.bin", path=file_path, content_type="application/octet-stream")
    updated_obj = await backend.save_to_storage_async(initial_obj, file_content)

    # 2. Create and save model instance
    doc = Document(name=doc_name, attachment=updated_obj)
    session.add(doc)
    session.commit()
    session.refresh(doc)

    assert doc.id is not None
    assert doc.attachment is not None
    assert isinstance(doc.attachment, FileObject)
    assert doc.attachment.filename == "report.bin"
    assert doc.attachment.path == file_path
    assert doc.attachment.size == len(file_content)
    assert doc.attachment.content_type == "application/octet-stream"
    assert doc.attachment.backend is backend  # Backend should be injected on load

    # 3. Retrieve content via loaded FileObject
    loaded_content = await doc.attachment.get_content_async()
    assert loaded_content == file_content


@pytest.mark.anyio
async def test_sqlalchemy_multiple_files_persist(session: Session, local_storage_backend: FSSpecBackend) -> None:
    """Test saving and loading a model with multiple StoredObjects."""
    backend = local_storage_backend
    img1_content = b"img_data_1"
    img2_content = b"img_data_2"
    doc_name = "Multi Image Doc"
    img1_path = "img1.jpg"
    img2_path = "img2.png"

    # 1. Prepare FileObjects and save via backend
    obj1 = FileObject(filename="image1.jpg", path=img1_path, content_type="image/jpeg")
    obj1_updated = await backend.save_to_storage_async(obj1, img1_content)

    obj2 = FileObject(filename="image2.png", path=img2_path, content_type="image/png")
    obj2_updated = await backend.save_to_storage_async(obj2, img2_content)

    # 2. Create and save model instance with MutableList
    img_list = MutableList[FileObject]([obj1_updated, obj2_updated])
    doc = Document(name=doc_name, images=img_list)
    session.add(doc)
    session.commit()
    session.refresh(doc)

    assert doc.id is not None
    assert doc.images is not None
    assert isinstance(doc.images, MutableList)
    assert len(doc.images) == 2

    # Verify loaded objects
    loaded_obj1 = doc.images[0]
    loaded_obj2 = doc.images[1]
    assert isinstance(loaded_obj1, FileObject)
    assert loaded_obj1.filename == "image1.jpg"
    assert loaded_obj1.path == img1_path
    assert loaded_obj1.size == len(img1_content)
    assert loaded_obj1.backend is backend

    assert isinstance(loaded_obj2, FileObject)
    assert loaded_obj2.filename == "image2.png"
    assert loaded_obj2.path == img2_path
    assert loaded_obj2.size == len(img2_content)
    assert loaded_obj2.backend is backend

    # Verify content
    assert await loaded_obj1.get_content_async() == img1_content
    assert await loaded_obj2.get_content_async() == img2_content


@pytest.mark.anyio
async def test_listener_delete_on_object_delete(session: Session, local_storage_backend: FSSpecBackend) -> None:
    """Test listener deletes file when object is deleted and session committed."""
    backend = local_storage_backend
    file_content = b"File to be deleted with object"
    file_path = "delete_with_obj.dat"

    # Save initial file and model
    obj = FileObject(filename="delete_me.dat", path=file_path)
    updated_obj = await backend.save_to_storage_async(obj, file_content)
    doc = Document(name="DocToDelete", attachment=updated_obj)
    session.add(doc)
    session.commit()
    doc_id = doc.id

    # Verify file exists
    assert await backend.get_content_async(file_path) == file_content

    # Delete the object and commit
    session.delete(doc)
    session.commit()

    # Verify object is deleted from DB
    assert session.get(Document, doc_id) is None

    # Verify listener deleted the file from storage
    with pytest.raises(FileNotFoundError):
        await backend.get_content_async(file_path)


@pytest.mark.anyio
async def test_listener_delete_on_update_replace(session: Session, local_storage_backend: FSSpecBackend) -> None:
    """Test listener deletes old file when attribute is updated and session committed."""
    backend = local_storage_backend
    old_content = b"Old file content"
    new_content = b"New file content"
    old_path = "old_file.txt"
    new_path = "new_file.txt"

    # Save initial file and model
    old_obj = FileObject(filename="old.txt", path=old_path)
    old_obj_updated = await backend.save_to_storage_async(old_obj, old_content)
    doc = Document(name="DocToUpdate", attachment=old_obj_updated)
    session.add(doc)
    session.commit()
    session.refresh(doc)

    # Verify old file exists
    assert await backend.get_content_async(old_path) == old_content

    # Prepare and save new file
    new_obj = FileObject(filename="new.txt", path=new_path)
    new_obj_updated = await backend.save_to_storage_async(new_obj, new_content)

    # Update the document's attachment
    doc.attachment = new_obj_updated
    session.add(doc)  # Add again as it's modified
    session.commit()
    session.refresh(doc)

    # Verify new file exists and attachment updated
    assert await backend.get_content_async(new_path) == new_content
    assert doc.attachment.path == new_path

    # Verify listener deleted the OLD file from storage
    with pytest.raises(FileNotFoundError):
        await backend.get_content_async(old_path)


@pytest.mark.anyio
async def test_listener_delete_on_update_clear(session: Session, local_storage_backend: FSSpecBackend) -> None:
    """Test listener deletes old file when attribute is cleared and session committed."""
    backend = local_storage_backend
    old_content = b"File to clear"
    old_path = "clear_me.log"

    # Save initial file and model
    old_obj = FileObject(filename="clear.log", path=old_path)
    old_obj_updated = await backend.save_to_storage_async(old_obj, old_content)
    doc = Document(name="DocToClear", attachment=old_obj_updated)
    session.add(doc)
    session.commit()
    session.refresh(doc)

    # Verify old file exists
    assert await backend.get_content_async(old_path) == old_content

    # Clear the attachment
    doc.attachment = None
    session.add(doc)
    session.commit()
    session.refresh(doc)

    # Verify attachment is None
    assert doc.attachment is None

    # Verify listener deleted the file from storage
    with pytest.raises(FileNotFoundError):
        await backend.get_content_async(old_path)


@pytest.mark.anyio
async def test_listener_delete_multiple_removed(session: Session, local_storage_backend: FSSpecBackend) -> None:
    """Test listener deletes files removed from a multiple list."""
    backend = local_storage_backend
    content1 = b"img1"
    content2 = b"img2"
    content3 = b"img3"
    path1 = "multi_del_1.dat"
    path2 = "multi_del_2.dat"
    path3 = "multi_del_3.dat"

    # Save files
    obj1 = await backend.save_to_storage_async(FileObject(filename=path1), content1)
    obj2 = await backend.save_to_storage_async(FileObject(filename=path2), content2)
    obj3 = await backend.save_to_storage_async(FileObject(filename=path3), content3)

    # Create model with initial list
    doc = Document(name="MultiDeleteTest", images=MutableList([obj1, obj2, obj3]))
    session.add(doc)
    session.commit()
    session.refresh(doc)

    # Verify all files exist
    assert await backend.get_content_async(path1) == content1
    assert await backend.get_content_async(path2) == content2
    assert await backend.get_content_async(path3) == content3

    # Remove items from the list (triggers MutableList tracking)
    assert doc.images is not None
    removed_item = doc.images.pop(1)  # Remove obj2
    assert removed_item is obj2
    del doc.images[0]  # Remove obj1 using delitem

    assert len(doc.images) == 1
    assert doc.images[0] is obj3

    session.add(doc)  # Mark modified
    session.commit()  # Listener should delete obj1 and obj2 based on MutableList._removed

    # Verify remaining file exists
    assert await backend.get_content_async(path3) == content3

    # Verify listener deleted the removed files
    with pytest.raises(FileNotFoundError):
        await backend.get_content_async(path1)
    with pytest.raises(FileNotFoundError):
        await backend.get_content_async(path2)
