# ruff: noqa: PLC2701 DOC402 ANN201
from collections.abc import AsyncGenerator, Generator
from pathlib import Path
from typing import Optional

import pytest
from minio import Minio
from pytest_databases.docker.minio import MinioService
from sqlalchemy import Engine, String, create_engine
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from advanced_alchemy.base import create_registry
from advanced_alchemy.exceptions import ImproperConfigurationError
from advanced_alchemy.types.file_object import (
    FileObject,
    FileObjectList,
    StoredObject,
)
from advanced_alchemy.types.file_object.backends.fsspec import FSSpecBackend
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

    # Create the storage directory
    storage_dir = tmp_path / "file_object_test_storage"
    storage_dir.mkdir(parents=True, exist_ok=True)

    storages.register_backend(
        ObstoreBackend(
            fs=LocalStore(prefix=str(storage_dir)),  # pyright: ignore
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
async def test_fsspec_s3_backend(
    storage_registry: StorageRegistry,
    minio_client: "Minio",
    minio_service: "MinioService",
    minio_default_bucket_name: str,
) -> None:
    """Test basic save, get_content, delete via backend and FileObject with prefix."""
    try:
        import s3fs
    except ImportError:
        pytest.skip("s3fs not installed")

    assert minio_client.bucket_exists(minio_default_bucket_name)
    _ = minio_client

    # Create s3fs filesystem instance without bucket info
    fs = s3fs.S3FileSystem(
        anon=False,
        key=minio_service.access_key,
        secret=minio_service.secret_key,
        endpoint_url=f"http://{minio_service.endpoint}",
        client_kwargs={
            "verify": False,
            "use_ssl": False,
        },
    )

    # Initialize backend with prefix
    backend = FSSpecBackend(
        key="s3_test_store",
        fs=fs,
        prefix=minio_default_bucket_name,
    )

    test_content = b"Hello Storage!"
    # Use relative path, prefix handles the bucket
    file_path = "test_basic.txt"

    # Create initial FileObject with relative path
    obj = FileObject(backend=backend, filename="test_basic.txt", to_filename=file_path)

    # Save using backend
    updated_obj = await backend.save_object_async(obj, test_content)

    # Assert FileObject updated
    assert updated_obj is obj  # Should update in-place
    assert obj.path == file_path  # Path should remain relative
    assert obj.filename == "test_basic.txt"
    assert obj.etag is not None
    assert obj.size == len(test_content)
    assert obj.backend is backend
    assert obj.protocol == "s3"  # Based on s3fs filesystem

    # Retrieve content via FileObject method (uses relative obj.path, backend adds prefix)
    retrieved_content = await obj.get_content_async()
    assert retrieved_content == test_content

    # Test sign method
    url = obj.sign(expires_in=3600)
    assert isinstance(url, str)
    assert url.startswith("http")

    # Test sign_async method
    url_async = await obj.sign_async(expires_in=3600)
    assert isinstance(url_async, str)
    assert url_async.startswith("http")

    # Test for_upload parameter
    with pytest.raises(
        NotImplementedError,
        match=r"Generating signed URLs for upload is generally not supported by fsspec's generic sign method.",
    ):
        _ = obj.sign(for_upload=True)
    # Delete via FileObject method (uses relative obj.path, backend adds prefix)
    await obj.delete_async()

    # Verify deletion using relative path with backend (backend adds prefix)
    with pytest.raises(FileNotFoundError):
        await backend.get_content_async(file_path)


@pytest.mark.xdist_group("file_object")
async def test_obstore_s3_backend(
    storage_registry: StorageRegistry,
    minio_client: "Minio",
    minio_service: "MinioService",
    minio_default_bucket_name: str,
) -> None:
    """Test basic save, get_content, delete via backend and FileObject."""

    assert minio_client.bucket_exists(minio_default_bucket_name)
    _ = minio_client
    backend = ObstoreBackend(
        key="s3_test_store",
        fs=f"s3://{minio_default_bucket_name}/",
        aws_endpoint=f"http://{minio_service.endpoint}/",
        aws_access_key_id=minio_service.access_key,
        aws_secret_access_key=minio_service.secret_key,
        aws_virtual_hosted_style_request=False,
        client_options={"allow_http": True},
    )

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
    assert obj.etag is not None
    assert obj.size == len(test_content)
    assert obj.backend is backend
    assert obj.protocol == "s3"  # Based on LocalFileSystem

    # Retrieve content via FileObject method
    retrieved_content = await obj.get_content_async()
    assert retrieved_content == test_content

    # Test sign method
    url = obj.sign(expires_in=3600)
    assert isinstance(url, str)
    assert url.startswith("http")

    # Test sign_async method
    url_async = await obj.sign_async(expires_in=3600)
    assert isinstance(url_async, str)
    assert url_async.startswith("http")

    # Test for_upload parameter
    url_for_upload = obj.sign(for_upload=True)
    assert isinstance(url_for_upload, str)
    assert url_for_upload.startswith("http")

    url_for_upload_async = await obj.sign_async(for_upload=True)
    assert isinstance(url_for_upload_async, str)
    assert url_for_upload_async.startswith("http")

    # Delete via FileObject method
    await obj.delete_async()

    # Verify deletion (expect FileNotFoundError or similar from backend)
    with pytest.raises(FileNotFoundError):
        await backend.get_content_async(file_path)


@pytest.mark.xdist_group("file_object")
async def test_obstore_backend_basic_operations(storage_registry: StorageRegistry) -> None:
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
async def test_obstore_backend_sqlalchemy_single_file_persist(
    async_session: AsyncSession, storage_registry: StorageRegistry
) -> None:
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
async def test_obstore_backend_sqlalchemy_multiple_files_persist(
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
async def test_obstore_backend_update_file_object(
    async_session: AsyncSession, storage_registry: StorageRegistry
) -> None:
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
async def test_obstore_backend_listener_delete_on_update_clear(
    async_session: AsyncSession, storage_registry: StorageRegistry
) -> None:
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
async def test_obstore_backend_listener_delete_multiple_removed(
    async_session: AsyncSession, storage_registry: StorageRegistry
) -> None:
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


@pytest.mark.xdist_group("file_object")
async def test_obstore_backend_file_object_invalid_init(storage_registry: StorageRegistry) -> None:
    """Test FileObject initialization with invalid parameters."""
    backend = storage_registry.get_backend("local_test_store")
    test_content = b"Test content"
    test_path = Path("test.txt")

    # Test both content and source_path provided
    with pytest.raises(ValueError, match="Cannot provide both 'source_content' and 'source_path'"):
        FileObject(
            backend=backend,
            filename="test.txt",
            content=test_content,
            source_path=test_path,
        )


@pytest.mark.xdist_group("file_object")
async def test_obstore_backend_file_object_metadata(storage_registry: StorageRegistry) -> None:
    """Test FileObject metadata handling."""
    backend = storage_registry.get_backend("local_test_store")
    initial_metadata = {"category": "test", "tags": ["sample"]}
    additional_metadata = {"priority": "high", "tags": ["important"]}

    # Create FileObject with initial metadata
    obj = FileObject(
        backend=backend,
        filename="test.txt",
        metadata=initial_metadata,
    )
    assert obj.metadata == initial_metadata

    # Update metadata
    obj.update_metadata(additional_metadata)
    expected_metadata = {
        "category": "test",
        "tags": ["important"],  # New tags override old ones
        "priority": "high",
    }
    assert obj.metadata == expected_metadata


@pytest.mark.xdist_group("file_object")
async def test_obstore_backend_file_object_to_dict(storage_registry: StorageRegistry) -> None:
    """Test FileObject to_dict method."""
    backend = storage_registry.get_backend("local_test_store")
    obj = FileObject(
        backend=backend,
        filename="test.txt",
        content_type="text/plain",
        size=100,
        last_modified=1234567890.0,
        checksum="abc123",
        etag="xyz789",
        version_id="v1",
        metadata={"category": "test"},
    )

    # Convert to dict
    obj_dict = obj.to_dict()
    assert obj_dict == {
        "filename": "test.txt",
        "content_type": "text/plain",
        "size": 100,
        "last_modified": 1234567890.0,
        "checksum": "abc123",
        "etag": "xyz789",
        "version_id": "v1",
        "metadata": {"category": "test"},
    }


@pytest.mark.xdist_group("file_object")
async def test_obstore_backend_local_file_object_sign_urls(storage_registry: StorageRegistry) -> None:
    """Test FileObject sign and sign_async methods."""
    backend = storage_registry.get_backend("local_test_store")
    test_content = b"Test content for signing"
    file_path = "test_sign.txt"

    # Create and save file
    obj = FileObject(backend=backend, filename="test.txt", to_filename=file_path)
    await obj.save_async(data=test_content)

    # Test sign method
    with pytest.raises(NotImplementedError, match=r"Error signing path test_sign.txt"):
        _ = obj.sign(expires_in=3600)

    # Test sign_async method
    with pytest.raises(NotImplementedError, match=r"Error signing path test_sign.txt"):
        _ = await obj.sign_async(expires_in=3600)

    with pytest.raises(
        NotImplementedError,
        match=r"Error signing path test_sign.txt",
    ):
        _ = obj.sign(for_upload=True)

    with pytest.raises(
        NotImplementedError,
        match=r"Error signing path test_sign.txt",
    ):
        _ = await obj.sign_async(for_upload=True)


@pytest.mark.xdist_group("file_object")
async def test_obstore_backend_file_object_save_with_different_data_types(storage_registry: StorageRegistry) -> None:
    """Test FileObject save with different data types."""
    backend = storage_registry.get_backend("local_test_store")
    test_content = b"Test content"
    file_path = "test_data_types.txt"

    # Test with bytes
    obj1 = FileObject(backend=backend, filename="test1.txt", to_filename=file_path)
    await obj1.save_async(data=test_content)
    assert await obj1.get_content_async() == test_content

    # Test with Path
    import tempfile

    with tempfile.NamedTemporaryFile(mode="wb", delete=False) as f:
        f.write(test_content)
        temp_path = Path(f.name)

    obj2 = FileObject(backend=backend, filename="test2.txt", to_filename=file_path)
    await obj2.save_async(data=temp_path)
    assert await obj2.get_content_async() == test_content

    # Cleanup
    temp_path.unlink()


@pytest.mark.xdist_group("file_object")
async def test_obstore_backend_file_object_pending_data(storage_registry: StorageRegistry) -> None:
    """Test FileObject has_pending_data property."""
    backend = storage_registry.get_backend("local_test_store")
    test_content = b"Test content"
    test_path = Path("test.txt")

    # Test with content
    obj1 = FileObject(backend=backend, filename="test1.txt", content=test_content)
    assert obj1.has_pending_data

    # Test with source_path
    obj2 = FileObject(backend=backend, filename="test2.txt", source_path=test_path)
    assert obj2.has_pending_data

    # Test without pending data
    obj3 = FileObject(backend=backend, filename="test3.txt")
    assert not obj3.has_pending_data


@pytest.mark.xdist_group("file_object")
async def test_obstore_backend_file_object_delete_methods(storage_registry: StorageRegistry) -> None:
    """Test FileObject delete and delete_async methods."""
    backend = storage_registry.get_backend("local_test_store")
    test_content = b"Test content to delete"
    file_path = "test_delete.txt"

    # Create and save file
    obj = FileObject(backend=backend, filename="test.txt", to_filename=file_path)
    await obj.save_async(data=test_content)

    # Verify file exists
    assert await backend.get_content_async(file_path) == test_content

    # Test delete_async
    await obj.delete_async()
    with pytest.raises(FileNotFoundError):
        await backend.get_content_async(file_path)

    # Create and save file again
    await obj.save_async(data=test_content)
    assert await backend.get_content_async(file_path) == test_content

    # Test delete
    obj.delete()
    with pytest.raises(FileNotFoundError):
        await backend.get_content_async(file_path)


@pytest.mark.xdist_group("file_object")
async def test_obstore_backend_storage_registry_management(storage_registry: StorageRegistry) -> None:
    """Test StorageRegistry management methods."""
    from obstore.store import MemoryStore

    from advanced_alchemy.types.file_object.backends.obstore import ObstoreBackend

    # Test registered_backends
    initial_backends = storage_registry.registered_backends()
    assert "local_test_store" in initial_backends
    assert "memory" in initial_backends

    # Test unregister_backend
    storage_registry.unregister_backend("local_test_store")
    assert "local_test_store" not in storage_registry.registered_backends()
    with pytest.raises(ImproperConfigurationError):
        storage_registry.get_backend("local_test_store")

    # Test clear_backends
    storage_registry.clear_backends()
    assert not storage_registry.registered_backends()

    # Test set_default_backend
    storage_registry.set_default_backend("advanced_alchemy.types.file_object.backends.obstore.ObstoreBackend")
    assert storage_registry.default_backend.__name__ == "ObstoreBackend"

    # Test register_backend with string value
    storage_registry.register_backend("memory://", key="test_backend")
    assert "test_backend" in storage_registry.registered_backends()
    assert isinstance(storage_registry.get_backend("test_backend"), ObstoreBackend)

    # Test register_backend with StorageBackend instance
    test_backend = ObstoreBackend(fs=MemoryStore(), key="test_backend2")
    storage_registry.register_backend(test_backend)
    assert "test_backend2" in storage_registry.registered_backends()
    assert storage_registry.get_backend("test_backend2") is test_backend

    # Test error cases
    with pytest.raises(ImproperConfigurationError, match="key is required when registering a string value"):
        storage_registry.register_backend("memory://")  # type: ignore[arg-type]

    with pytest.raises(ImproperConfigurationError, match="key is not allowed when registering a StorageBackend"):
        storage_registry.register_backend(test_backend, key="invalid_key")  # type: ignore[arg-type]


@pytest.mark.xdist_group("file_object")
async def test_obstore_backend_storage_registry_error_handling(storage_registry: StorageRegistry) -> None:
    """Test StorageRegistry error handling."""
    # Test get_backend with non-existent key
    with pytest.raises(ImproperConfigurationError, match="No storage backend registered with key nonexistent"):
        storage_registry.get_backend("nonexistent")

    # Test unregister_backend with non-existent key
    storage_registry.unregister_backend("nonexistent")  # Should not raise an error

    # Test set_default_backend with invalid backend
    with pytest.raises(ImportError):
        storage_registry.set_default_backend("invalid.module.path.Backend")


@pytest.mark.xdist_group("file_object")
async def test_fsspec_backend_basic_operations(storage_registry: StorageRegistry) -> None:
    """Test basic operations with FSSpec backend."""
    try:
        import fsspec
    except ImportError:
        pytest.skip("fsspec not installed")

    # Create a local filesystem backend
    fs = fsspec.filesystem("file")
    backend = FSSpecBackend(fs=fs, key="fsspec_test")
    test_content = b"Test content"
    file_path = "test_fsspec.txt"

    # Test save and get content
    obj = FileObject(backend=backend, filename="test.txt", to_filename=file_path)
    await obj.save_async(data=test_content)
    assert await obj.get_content_async() == test_content

    # Test delete
    await obj.delete_async()
    with pytest.raises(FileNotFoundError):
        await obj.get_content_async()


@pytest.mark.xdist_group("file_object")
async def test_fsspec_backend_protocols(storage_registry: StorageRegistry) -> None:
    """Test FSSpec backend with different protocols."""
    try:
        import fsspec
    except ImportError:
        pytest.skip("fsspec not installed")

    # Test local filesystem
    fs_local = fsspec.filesystem("file")
    backend_local = FSSpecBackend(fs=fs_local, key="fsspec_local")
    assert backend_local.protocol == "file"

    # Test memory filesystem
    fs_memory = fsspec.filesystem("memory")
    backend_memory = FSSpecBackend(fs=fs_memory, key="fsspec_memory")
    assert backend_memory.protocol == "memory"

    # Test with protocol string
    backend_from_string = FSSpecBackend(fs="file", key="fsspec_string")
    assert backend_from_string.protocol == "file"


@pytest.mark.xdist_group("file_object")
async def test_fsspec_backend_content_types(storage_registry: StorageRegistry) -> None:
    """Test FSSpec backend with different content types."""
    try:
        import fsspec
    except ImportError:
        pytest.skip("fsspec not installed")

    fs = fsspec.filesystem("memory")
    backend = FSSpecBackend(fs=fs, key="fsspec_content")
    file_path = "test_content.txt"

    # Test with bytes
    content_bytes = b"Test bytes"
    obj_bytes = FileObject(backend=backend, filename="test_bytes.txt", to_filename=file_path)
    await obj_bytes.save_async(data=content_bytes)
    assert await obj_bytes.get_content_async() == content_bytes

    # Test with string
    content_str = "Test string"
    obj_str = FileObject(backend=backend, filename="test_str.txt", to_filename=file_path)
    await obj_str.save_async(data=content_str.encode("utf-8"))
    assert await obj_str.get_content_async() == content_str.encode("utf-8")


@pytest.mark.xdist_group("file_object")
async def test_fsspec_backend_multipart_upload(storage_registry: StorageRegistry) -> None:
    """Test FSSpec backend multipart upload."""
    try:
        import fsspec
    except ImportError:
        pytest.skip("fsspec not installed")

    fs = fsspec.filesystem("memory")
    backend = FSSpecBackend(fs=fs, key="fsspec_multipart")
    file_path = "test_multipart.txt"

    # Create large content for multipart upload
    large_content = b"x" * (5 * 1024 * 1024 + 1)  # 5MB + 1 byte
    obj = FileObject(backend=backend, filename="test.txt", to_filename=file_path)

    # Test with multipart upload
    await obj.save_async(
        data=large_content,
        use_multipart=True,
        chunk_size=1024 * 1024,  # 1MB chunks
        max_concurrency=4,
    )
    assert await obj.get_content_async() == large_content


@pytest.mark.xdist_group("file_object")
async def test_fsspec_backend_sign_urls(storage_registry: StorageRegistry, tmp_path: Path) -> None:
    """Test FSSpec backend URL signing."""
    try:
        import fsspec
    except ImportError:
        pytest.skip("fsspec not installed")

    fs = fsspec.filesystem("file")
    backend = FSSpecBackend(fs=fs, key="fsspec_sign", prefix=str(tmp_path))
    file_path = "test_sign.txt"

    # Create and save test file
    test_content = b"Test content for signing"
    obj = FileObject(backend=backend, filename="test.txt", to_filename=file_path)
    await obj.save_async(data=test_content)

    # Test sign method
    with pytest.raises(NotImplementedError, match="Signing URLs not supported by file backend"):
        _ = obj.sign(expires_in=3600)

    # Test sign_async method
    with pytest.raises(NotImplementedError, match="Signing URLs not supported by file backend"):
        _ = await obj.sign_async(expires_in=3600)

    # Test for_upload parameter
    with pytest.raises(
        NotImplementedError,
        match=r"Generating signed URLs for upload is generally not supported by fsspec's generic sign method.",
    ):
        _ = obj.sign(for_upload=True)
