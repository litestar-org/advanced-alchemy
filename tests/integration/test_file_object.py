# ruff: noqa: PLC2701 DOC402 ANN201
from collections.abc import AsyncGenerator, Generator
from pathlib import Path
from typing import Optional

import pytest
from sqlalchemy import Engine, String, create_engine
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from advanced_alchemy.base import create_registry
from advanced_alchemy.types.file_object import (
    FileObject,
    FileObjectList,
    StoredObject,
)
from advanced_alchemy.types.file_object.backends.obstore import ObstoreBackend
from advanced_alchemy.types.file_object.registry import StorageRegistry, storages
from advanced_alchemy.types.mutables import MutableList

pytestmark = pytest.mark.integration


# --- Fixtures ---
orm_registry = create_registry()


# --- SQLAlchemy Model Definition ---
class Base(DeclarativeBase):
    metadata = orm_registry.metadata


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50))
    # Single file storage
    attachment: Mapped[Optional[FileObject]] = mapped_column(
        StoredObject(backend="local_test_store"),  # Use StoredObject wrapper
        nullable=True,
    )
    # Multiple file storage
    images: Mapped[Optional[FileObjectList]] = mapped_column(
        StoredObject(backend="local_test_store", multiple=True),  # Use StoredObject wrapper
        nullable=True,
    )


@pytest.fixture()
def storage_registry(tmp_path: Path) -> "StorageRegistry":
    """Clears and returns the global storage registry for the module.

    Returns:
        StorageRegistry: The global storage registry.
    """
    from obstore.store import LocalStore, MemoryStore

    if not storages.is_registered("memory"):
        storages.register_backend(ObstoreBackend(fs=MemoryStore(), key="memory"))
    if storages.is_registered("local_test_store"):
        storages.unregister_backend("local_test_store")
    storages.register_backend(
        ObstoreBackend(
            fs=LocalStore(prefix=Path(tmp_path / "file_object_test_storage"), automatic_cleanup=False, mkdir=True),  # pyright: ignore
            key="local_test_store",
        )
    )
    return storages


@pytest.fixture()
def sync_db_engine(tmp_path: Path) -> Generator[Engine, None, None]:
    """Provides an SQLite engine scoped to each function."""
    db_file = tmp_path / "test_file_object_sync.db"
    engine = create_engine(f"sqlite:///{db_file}")
    yield engine
    db_file.unlink(missing_ok=True)


@pytest.fixture()
def async_db_engine(tmp_path: Path) -> Generator[AsyncEngine, None, None]:
    """Provides an SQLite engine scoped to each function."""
    db_file = tmp_path / "test_file_object_async.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}")
    yield engine
    db_file.unlink(missing_ok=True)


@pytest.fixture()
def session(
    db_engine: Engine, storage_registry: "StorageRegistry"
) -> Generator[Session, None, None]:  # Depend on sqlalchemy_config to ensure setup runs
    """Provides a SQLAlchemy session scoped to each function."""
    Base.metadata.create_all(db_engine)
    with Session(db_engine) as db_session:
        yield db_session
    Base.metadata.drop_all(db_engine)


@pytest.fixture()
async def async_session(
    async_db_engine: AsyncEngine, storage_registry: "StorageRegistry"
) -> AsyncGenerator[AsyncSession, None]:  # Depend on sqlalchemy_config to ensure setup runs
    """Provides a SQLAlchemy session scoped to each function."""
    async with async_db_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_sessionmaker(async_db_engine)() as db_session:
        yield db_session

    async with async_db_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await async_db_engine.dispose()


# --- Test Cases ---


@pytest.mark.xdist_group("file_object")
async def test_save_retrieve_delete_content(storage_registry: StorageRegistry) -> None:
    """Test basic save, get_content, delete via backend and FileObject."""
    backend = storage_registry.get_backend("local_test_store")
    test_content = b"Hello Storage!"
    file_path = "test_basic.txt"  # Relative path for the backend

    # Create initial FileObject
    obj = FileObject(backend=backend, filename="test_basic.txt", to_filename=file_path)

    # Save using backend
    updated_obj = await backend.save_object_async(obj, test_content)

    # Assert FileObject updated
    assert updated_obj is obj  # Should update in-place
    assert obj.path == file_path
    assert obj.filename == "test_basic.txt"
    assert obj.size == len(test_content) or obj.size is None
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


@pytest.mark.xdist_group("file_object")
async def test_sqlalchemy_single_file_persist(async_session: AsyncSession, storage_registry: StorageRegistry) -> None:
    """Test saving and loading a model with a single StoredObject."""

    file_content = b"SQLAlchemy Integration Test"
    doc_name = "Integration Doc"
    file_path = "sqlalchemy_single.bin"

    # 1. Prepare FileObject and save via backend
    initial_obj = FileObject(
        backend="local_test_store",
        filename="report.bin",
        to_filename=file_path,
        content_type="application/octet-stream",
    )
    updated_obj = await initial_obj.save_async(data=file_content)

    # 2. Create and save model instance
    doc = Document(name=doc_name, attachment=updated_obj)
    async_session.add(doc)
    await async_session.commit()
    await async_session.refresh(doc)

    assert doc.id is not None
    assert doc.attachment is not None
    assert isinstance(doc.attachment, FileObject)
    assert doc.attachment.filename == "sqlalchemy_single.bin"
    assert doc.attachment.path == file_path
    assert doc.attachment.size == len(file_content) or doc.attachment.size is None
    assert doc.attachment.content_type == "application/octet-stream"
    assert doc.attachment.backend.key == "local_test_store"

    # 3. Retrieve content via loaded FileObject
    loaded_content = await doc.attachment.get_content_async()
    assert loaded_content == file_content


@pytest.mark.xdist_group("file_object")
async def test_sqlalchemy_multiple_files_persist(
    async_session: AsyncSession, storage_registry: StorageRegistry
) -> None:
    """Test saving and loading a model with multiple StoredObjects."""
    backend = storage_registry.get_backend("local_test_store")
    img1_content = b"img_data_1"
    img2_content = b"img_data_2"
    doc_name = "Multi Image Doc"
    img1_path = "img1.jpg"
    img2_path = "img2.png"

    # 1. Prepare FileObjects and save via backend
    obj1 = FileObject(backend=backend, filename="image1.jpg", to_filename=img1_path, content_type="image/jpeg")
    obj1_updated = await obj1.save_async(img1_content)

    obj2 = FileObject(backend=backend, filename="image2.png", to_filename=img2_path, content_type="image/png")
    obj2_updated = await obj2.save_async(img2_content)

    # 2. Create and save model instance with MutableList
    img_list = MutableList[FileObject]([obj1_updated, obj2_updated])
    doc = Document(name=doc_name, images=img_list)
    async_session.add(doc)
    await async_session.commit()
    await async_session.refresh(doc)

    assert doc.id is not None
    assert doc.images is not None
    assert isinstance(doc.images, MutableList)
    assert len(doc.images) == 2

    # Verify loaded objects
    loaded_obj1 = doc.images[0]
    loaded_obj2 = doc.images[1]
    assert isinstance(loaded_obj1, FileObject)
    assert loaded_obj1.filename == "img1.jpg"
    assert loaded_obj1.path == img1_path
    assert loaded_obj1.size == len(img1_content) or loaded_obj1.size is None
    assert loaded_obj1.backend and loaded_obj1.backend.driver == backend.driver

    assert isinstance(loaded_obj2, FileObject)
    assert loaded_obj2.filename == "img2.png"
    assert loaded_obj2.path == img2_path
    assert loaded_obj2.size == len(img2_content) or loaded_obj2.size is None
    assert loaded_obj2.backend and loaded_obj2.backend.driver == backend.driver

    # Verify content
    assert await loaded_obj1.get_content_async() == img1_content
    assert await loaded_obj2.get_content_async() == img2_content


@pytest.mark.xdist_group("file_object")
async def test_update_file_object(async_session: AsyncSession, storage_registry: StorageRegistry) -> None:
    """Test listener deletes old file when attribute is updated and session committed."""
    backend = storage_registry.get_backend("local_test_store")
    old_content = b"Old file content"
    new_content = b"New file content"
    old_path = "old_file.txt"
    new_path = "new_file.txt"

    # Save initial file and model
    old_obj = FileObject(backend=backend, filename="old.txt", to_filename=old_path)
    old_obj_updated = await old_obj.save_async(old_content)
    doc = Document(name="DocToUpdate", attachment=old_obj_updated)
    async_session.add(doc)
    await async_session.commit()
    await async_session.refresh(doc)

    # Verify old file exists
    assert await backend.get_content_async(old_path) == old_content

    # Prepare and save new file
    new_obj = FileObject(backend=backend, filename="new.txt", to_filename=new_path)
    new_obj_updated = await new_obj.save_async(new_content)
    await old_obj.delete_async()
    # Update the document's attachment
    doc.attachment = new_obj_updated
    async_session.add(doc)  # Add again as it's modified
    await async_session.commit()
    await async_session.refresh(doc)

    # Verify new file exists and attachment updated
    assert await backend.get_content_async(new_path) == new_content
    assert doc.attachment is not None and doc.attachment.path == new_path

    # Verify listener deleted the OLD file from storage
    with pytest.raises(FileNotFoundError):
        await backend.get_content_async(old_path)


@pytest.mark.xdist_group("file_object")
async def test_listener_delete_on_update_clear(async_session: AsyncSession, storage_registry: StorageRegistry) -> None:
    """Test listener deletes old file when attribute is cleared and session committed."""
    backend = storage_registry.get_backend("local_test_store")
    old_content = b"File to clear"
    old_path = "clear_me.log"

    # Save initial file and model
    old_obj = FileObject(backend=backend, filename="clear.log", to_filename=old_path)
    old_obj_updated = await old_obj.save_async(old_content)
    doc = Document(name="DocToClear", attachment=old_obj_updated)
    async_session.add(doc)
    await async_session.commit()
    await async_session.refresh(doc)

    # Verify old file exists
    assert await backend.get_content_async(old_path) == old_content

    # Clear the attachment
    doc.attachment = None
    async_session.add(doc)
    await async_session.commit()
    await async_session.refresh(doc)
    await old_obj.delete_async()
    # Verify attachment is None
    assert doc.attachment is None

    # Verify listener deleted the file from storage
    with pytest.raises(FileNotFoundError):
        await backend.get_content_async(old_path)


@pytest.mark.xdist_group("file_object")
async def test_listener_delete_multiple_removed(async_session: AsyncSession, storage_registry: StorageRegistry) -> None:
    """Test listener deletes files removed from a multiple list."""
    backend = storage_registry.get_backend("local_test_store")
    content1 = b"img1"
    content2 = b"img2"
    content3 = b"img3"
    path1 = "multi_del_1.dat"
    path2 = "multi_del_2.dat"
    path3 = "multi_del_3.dat"

    # Save files
    obj1 = FileObject(backend=backend, filename=path1)
    obj2 = FileObject(backend=backend, filename=path2)
    obj3 = FileObject(backend=backend, filename=path3)
    obj1 = await obj1.save_async(content1)
    obj2 = await obj2.save_async(content2)
    obj3 = await obj3.save_async(content3)

    # Create model with initial list
    doc = Document(name="MultiDeleteTest", images=[obj1, obj2, obj3])
    async_session.add(doc)
    await async_session.commit()
    await async_session.refresh(doc)

    # Verify all files exist
    assert await backend.get_content_async(path1) == content1
    assert await backend.get_content_async(path2) == content2
    assert await backend.get_content_async(path3) == content3

    # Remove items from the list (triggers MutableList tracking)
    assert doc.images is not None
    removed_item = doc.images.pop(1)  # Remove obj2
    assert removed_item.path == obj2.path
    del doc.images[0]  # Remove obj1 using delitem
    await removed_item.delete_async()
    assert len(doc.images) == 1
    assert doc.images[0].path == obj3.path

    async_session.add(doc)  # Mark modified
    await async_session.commit()  # Listener should delete obj1 and obj2 based on MutableList._removed

    # Verify remaining file exists
    assert await backend.get_content_async(path3) == content3
