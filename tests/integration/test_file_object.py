import logging
from collections.abc import AsyncGenerator, Generator
from contextlib import suppress
from pathlib import Path
from typing import Optional

import pytest
from minio import Minio  # type: ignore[import-untyped]
from pytest_databases.docker.minio import MinioService
from sqlalchemy import Engine, String, create_engine, event
from sqlalchemy.exc import InvalidRequestError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from advanced_alchemy._listeners import set_async_context, setup_file_object_listeners
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

# Setup logger
logger = logging.getLogger(__name__)

pytestmark = pytest.mark.integration


def remove_listeners() -> None:
    """Remove file object listeners safely to prevent test interactions."""
    from sqlalchemy.event import contains

    from advanced_alchemy._listeners import FileObjectListener

    # Only try to remove listeners if they're actually registered
    if contains(Session, "before_flush", FileObjectListener.before_flush):
        with suppress(InvalidRequestError):
            event.remove(Session, "before_flush", FileObjectListener.before_flush)

    if contains(Session, "after_commit", FileObjectListener.after_commit):
        with suppress(InvalidRequestError):
            event.remove(Session, "after_commit", FileObjectListener.after_commit)

    if contains(Session, "after_rollback", FileObjectListener.after_rollback):
        with suppress(InvalidRequestError):
            event.remove(Session, "after_rollback", FileObjectListener.after_rollback)

    # Reset async context flag to ensure clean state
    set_async_context(False)


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
    engine = create_engine(f"sqlite:///{db_file}", execution_options={"enable_file_object_listener": True})
    yield engine
    db_file.unlink(missing_ok=True)


@pytest.fixture()
def async_db_engine(tmp_path: Path) -> Generator[AsyncEngine, None, None]:
    """Provides an SQLite engine scoped to each function."""
    db_file = tmp_path / "test_file_object_async.db"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_file}", execution_options={"enable_file_object_listener": True}
    )
    yield engine
    db_file.unlink(missing_ok=True)


@pytest.fixture()
def session(
    sync_db_engine: Engine, storage_registry: "StorageRegistry"
) -> Generator[Session, None, None]:  # Depend on sqlalchemy_config to ensure setup runs
    """Provides a SQLAlchemy session scoped to each function."""
    Base.metadata.create_all(sync_db_engine)
    with Session(sync_db_engine) as db_session:
        yield db_session
    Base.metadata.drop_all(sync_db_engine)


@pytest.fixture()
async def async_session(
    async_db_engine: AsyncEngine, storage_registry: "StorageRegistry"
) -> AsyncGenerator[AsyncSession, None]:  # Depend on sqlalchemy_config to ensure setup runs
    """Provides a SQLAlchemy session scoped to each function."""
    async with async_db_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Create session with flag for listener to identify async operations
    set_async_context(True)
    # Create session factory
    async_session_factory = async_sessionmaker(
        async_db_engine,
        expire_on_commit=False,
    )

    # Create session
    async with async_session_factory() as db_session:
        # Add flag to session.info dictionary
        db_session.info["enable_file_object_listener"] = True
        logger.debug(f"Created async session: {id(db_session)}, with info: {db_session.info}")
        yield db_session

    # Reset async context flag
    set_async_context(False)

    async with async_db_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await async_db_engine.dispose()


@pytest.mark.xdist_group("file_object")
async def test_fsspec_s3_basic_operations_async(
    storage_registry: StorageRegistry,
    minio_client: "Minio",
    minio_service: "MinioService",
    minio_default_bucket_name: str,
) -> None:
    """Test basic save, get_content, delete via backend and FileObject with prefix."""
    remove_listeners()
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
    file_path = "test_basic_s3_async.txt"

    # Create initial FileObject with relative path
    obj = FileObject(backend=backend, filename="test_basic_s3_async.txt", to_filename=file_path)

    # Save using backend
    updated_obj = await backend.save_object_async(obj, test_content)

    # Assert FileObject updated
    assert updated_obj is obj  # Should update in-place
    assert obj.path == file_path  # Path should remain relative
    assert obj.filename == "test_basic_s3_async.txt"
    assert obj.etag is not None
    assert obj.size == len(test_content)
    assert obj.backend is backend
    assert obj.protocol == "s3"  # Based on s3fs filesystem

    # Retrieve content via FileObject method (uses relative obj.path, backend adds prefix)
    retrieved_content = await obj.get_content_async()
    assert retrieved_content == test_content

    # Test sign_async method
    url_async = await obj.sign_async(expires_in=3600)
    assert isinstance(url_async, str)
    assert url_async.startswith("http")

    # Test for_upload parameter
    with pytest.raises(
        NotImplementedError,
        match=r"Generating signed URLs for upload is generally not supported by fsspec's generic sign method.",
    ):
        _ = await obj.sign_async(for_upload=True)
    # Delete via FileObject method (uses relative obj.path, backend adds prefix)
    await obj.delete_async()

    # Verify deletion using relative path with backend (backend adds prefix)
    with pytest.raises(FileNotFoundError):
        await backend.get_content_async(file_path)


@pytest.mark.xdist_group("file_object")
def test_fsspec_s3_basic_operations_sync(
    storage_registry: StorageRegistry,
    minio_client: "Minio",
    minio_service: "MinioService",
    minio_default_bucket_name: str,
) -> None:
    """Test basic save, get_content, delete via backend and FileObject with prefix."""
    remove_listeners()
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
        asynchronous=False,
        loop=None,
    )

    # Initialize backend with prefix
    backend = FSSpecBackend(
        key="s3_test_store",
        fs=fs,
        prefix=minio_default_bucket_name,
    )

    test_content = b"Hello Storage!"
    # Use relative path, prefix handles the bucket
    file_path = "test_basic_s3_sync.txt"

    # Create initial FileObject with relative path
    obj = FileObject(backend=backend, filename="test_basic_s3_sync.txt", to_filename=file_path)

    # Save using backend
    updated_obj = backend.save_object(obj, test_content)

    # Assert FileObject updated
    assert updated_obj is obj  # Should update in-place
    assert obj.path == file_path  # Path should remain relative
    assert obj.filename == "test_basic_s3_sync.txt"
    assert obj.etag is not None
    assert obj.size == len(test_content)
    assert obj.backend is backend
    assert obj.protocol == "s3"  # Based on s3fs filesystem

    # Retrieve content via FileObject method (uses relative obj.path, backend adds prefix)
    retrieved_content = obj.get_content()
    assert retrieved_content == test_content

    # Test sign_async method
    url_async = obj.sign(expires_in=3600)
    assert isinstance(url_async, str)
    assert url_async.startswith("http")

    # Test for_upload parameter
    with pytest.raises(
        NotImplementedError,
        match=r"Generating signed URLs for upload is generally not supported by fsspec's generic sign method.",
    ):
        _ = obj.sign(for_upload=True)
    # Delete via FileObject method (uses relative obj.path, backend adds prefix)
    obj.delete()

    # Verify deletion using relative path with backend (backend adds prefix)
    with pytest.raises(FileNotFoundError):
        backend.get_content(file_path)


@pytest.mark.xdist_group("file_object")
async def test_obstore_s3_basic_operations_async(
    storage_registry: StorageRegistry,
    minio_client: "Minio",
    minio_service: "MinioService",
    minio_default_bucket_name: str,
) -> None:
    """Test basic save, get_content, delete via backend and FileObject."""
    remove_listeners()
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
    file_path = "test_basic_s3_async.txt"  # Relative path for the backend

    # Create initial FileObject
    obj = FileObject(backend=backend, filename="test_basic_s3_async.txt", to_filename=file_path)

    # Save using backend
    updated_obj = await backend.save_object_async(obj, test_content)

    # Assert FileObject updated
    assert updated_obj is obj  # Should update in-place
    assert obj.path == file_path
    assert obj.filename == "test_basic_s3_async.txt"
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

    url_for_upload_async = await obj.sign_async(for_upload=True)
    assert isinstance(url_for_upload_async, str)
    assert url_for_upload_async.startswith("http")

    # Delete via FileObject method
    await obj.delete_async()

    # Verify deletion (expect FileNotFoundError or similar from backend)
    with pytest.raises(FileNotFoundError):
        await backend.get_content_async(file_path)


@pytest.mark.xdist_group("file_object")
def test_obstore_s3_basic_operations_sync(
    storage_registry: StorageRegistry,
    minio_client: "Minio",
    minio_service: "MinioService",
    minio_default_bucket_name: str,
) -> None:
    """Test basic save, get_content, delete via backend and FileObject."""
    remove_listeners()
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
    file_path = "test_basic_s3_sync.txt"  # Relative path for the backend

    # Create initial FileObject
    obj = FileObject(backend=backend, filename="test_basic_s3_sync.txt", to_filename=file_path)

    # Save using backend
    updated_obj = backend.save_object(obj, test_content)

    # Assert FileObject updated
    assert updated_obj is obj  # Should update in-place
    assert obj.path == file_path
    assert obj.filename == "test_basic_s3_sync.txt"
    assert obj.etag is not None
    assert obj.size == len(test_content)
    assert obj.backend is backend
    assert obj.protocol == "s3"  # Based on LocalFileSystem

    # Retrieve content via FileObject method
    retrieved_content = obj.get_content()
    assert retrieved_content == test_content

    # Test sign method
    url = obj.sign(expires_in=3600)
    assert isinstance(url, str)
    assert url.startswith("http")

    # Test sign_async method
    url_async = obj.sign(expires_in=3600)
    assert isinstance(url_async, str)
    assert url_async.startswith("http")

    # Test for_upload parameter
    url_for_upload = obj.sign(for_upload=True)
    assert isinstance(url_for_upload, str)
    assert url_for_upload.startswith("http")

    # Delete via FileObject method
    obj.delete()

    # Verify deletion (expect FileNotFoundError or similar from backend)
    with pytest.raises(FileNotFoundError):
        backend.get_content(file_path)


@pytest.mark.xdist_group("file_object")
async def test_obstore_basic_operations_async(storage_registry: StorageRegistry) -> None:
    """Test basic save, get_content, delete via backend and FileObject."""
    remove_listeners()
    backend = storage_registry.get_backend("local_test_store")
    test_content = b"Hello Storage!"
    file_path = "test_basic_async.txt"  # Relative path for the backend

    # Create initial FileObject
    obj = FileObject(backend=backend, filename="test_basic_async.txt", to_filename=file_path)

    # Save using backend
    updated_obj = await backend.save_object_async(obj, test_content)

    # Assert FileObject updated
    assert updated_obj is obj  # Should update in-place
    assert obj.path == file_path
    assert obj.filename == "test_basic_async.txt"
    assert obj.etag is not None
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


@pytest.mark.xdist_group("file_object")
def test_obstore_basic_operations_sync(storage_registry: StorageRegistry) -> None:
    """Test basic save, get_content, delete via backend and FileObject."""
    remove_listeners()
    backend = storage_registry.get_backend("local_test_store")
    test_content = b"Hello Storage!"
    file_path = "test_basic_sync.txt"  # Relative path for the backend

    # Create initial FileObject
    obj = FileObject(backend=backend, filename="test_basic_sync.txt", to_filename=file_path)

    # Save using backend
    updated_obj = backend.save_object(obj, test_content)

    # Assert FileObject updated
    assert updated_obj is obj  # Should update in-place
    assert obj.path == file_path
    assert obj.filename == "test_basic_sync.txt"
    assert obj.etag is not None
    assert obj.size == len(test_content)
    assert obj.backend is backend
    assert obj.protocol == "file"  # Based on LocalFileSystem

    # Retrieve content via FileObject method
    retrieved_content = obj.get_content()
    assert retrieved_content == test_content

    # Delete via FileObject method
    obj.delete()

    # Verify deletion (expect FileNotFoundError or similar from backend)
    with pytest.raises(FileNotFoundError):
        backend.get_content(file_path)


@pytest.mark.xdist_group("file_object")
async def test_obstore_single_file_async_no_listener(
    async_session: AsyncSession, storage_registry: StorageRegistry
) -> None:
    """Test saving and loading a model with a single StoredObject."""
    remove_listeners()
    file_content = b"SQLAlchemy Integration Test"
    doc_name = "Integration Doc"
    file_path = "sqlalchemy_single_async.bin"

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
    assert doc.attachment.filename == "sqlalchemy_single_async.bin"
    assert doc.attachment.path == file_path
    assert doc.attachment.size == len(file_content) or doc.attachment.size is None
    assert doc.attachment.content_type == "application/octet-stream"
    assert doc.attachment.backend.key == "local_test_store"

    # 3. Retrieve content via loaded FileObject
    loaded_content = await doc.attachment.get_content_async()
    assert loaded_content == file_content


@pytest.mark.xdist_group("file_object")
async def test_obstore_multiple_files_async_no_listener(
    async_session: AsyncSession, storage_registry: StorageRegistry
) -> None:
    """Test saving and loading a model with multiple StoredObjects."""
    remove_listeners()
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
async def test_obstore_update_async_with_listener(
    async_session: AsyncSession, storage_registry: StorageRegistry
) -> None:
    """Test listener deletes old file when attribute is updated and session committed."""
    # Set async context flag to enable async operations in the listener
    set_async_context(True)

    setup_file_object_listeners()
    backend = storage_registry.get_backend("local_test_store")
    old_content = b"Old file content"
    new_content = b"New file content"
    old_path = "old_file_async.txt"
    new_path = "new_file_async.txt"

    # Save initial file and model
    old_obj = FileObject(backend=backend, filename="old_file_async.txt", to_filename=old_path, content=old_content)
    # Make sure file is saved to the backend
    old_obj = await old_obj.save_async()

    doc = Document(name="DocToUpdate", attachment=old_obj)
    async_session.add(doc)
    await async_session.commit()
    await async_session.refresh(doc)

    # Verify old file exists
    assert await backend.get_content_async(old_path) == old_content

    # Prepare new file
    new_obj = FileObject(backend=backend, filename="new_file_async.txt", to_filename=new_path, content=new_content)

    # Update the document with the new file
    doc.attachment = new_obj
    async_session.add(doc)
    await async_session.commit()
    await async_session.refresh(doc)

    # Verify new file exists and attachment updated
    assert await backend.get_content_async(new_path) == new_content
    assert doc.attachment is not None and doc.attachment.path == new_path  # pyright: ignore

    # Verify the listener deleted the old file
    with pytest.raises(FileNotFoundError):
        await backend.get_content_async(old_path)


@pytest.mark.xdist_group("file_object")
async def test_obstore_delete_async_on_update_clear_with_listener(
    async_session: AsyncSession, storage_registry: StorageRegistry
) -> None:
    """Test listener deletes file when attribute is cleared.

    Note that AsyncSession in SQLAlchemy 2.0 has limitations with event listeners.
    We will manually handle cleanup of files to ensure proper functionality.
    """
    # Set async context flag to enable async operations in the listener
    set_async_context(True)

    setup_file_object_listeners()
    backend = storage_registry.get_backend("local_test_store")
    old_content = b"File to clear"
    old_path = "clear_me_async.log"

    # Save initial file and model
    old_obj = FileObject(backend=backend, filename="clear_me_async.log", to_filename=old_path, content=old_content)
    old_obj = await old_obj.save_async()  # Make sure it's saved to the backend

    doc = Document(name="DocToClear", attachment=old_obj)
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

    # Verify attachment is None
    assert doc.attachment is None

    # Verify the listener deleted the file
    with pytest.raises(FileNotFoundError):
        await backend.get_content_async(old_path)


@pytest.mark.xdist_group("file_object")
async def test_obstore_delete_async_multiple_removed_with_listener(
    async_session: AsyncSession, storage_registry: StorageRegistry
) -> None:
    """Test listener deletes files removed from a multiple list.

    Note that AsyncSession in SQLAlchemy 2.0 has limitations with event listeners.
    MutableList tracking doesn't work properly with AsyncSession, so we use direct
    assignment for updates instead of mutating the list in-place.
    """
    # Set async context flag to enable async operations in the listener
    set_async_context(True)

    setup_file_object_listeners()
    backend = storage_registry.get_backend("local_test_store")
    content1 = b"img1"
    content2 = b"img2"
    path1 = "img1_list_async.jpg"
    path2 = "img2_list_async.png"

    # Create file objects and save them
    obj1 = FileObject(backend=backend, filename="img1_list_async.jpg", to_filename=path1, content=content1)
    obj1 = await obj1.save_async()

    obj2 = FileObject(backend=backend, filename="img2_list_async.png", to_filename=path2, content=content2)
    obj2 = await obj2.save_async()

    # Create and save model with both images
    img_list = MutableList[FileObject]([obj1, obj2])
    doc = Document(name="ImagesDoc", images=img_list)
    async_session.add(doc)
    await async_session.commit()
    await async_session.refresh(doc)

    # Verify files exist
    assert await backend.get_content_async(path1) == content1
    assert await backend.get_content_async(path2) == content2

    # Verify images are loaded
    assert doc.images is not None
    assert len(doc.images) == 2

    # With AsyncSession, mutations to MutableList may not be tracked correctly.
    # Instead of mutating the list in place, we'll create a new list with only obj2
    doc.images = MutableList[FileObject]([obj2])

    async_session.add(doc)
    await async_session.commit()
    await async_session.refresh(doc)

    # Verify only one image remains
    assert doc.images is not None
    assert len(doc.images or []) == 1
    assert doc.images[0].path == path2  # pyright: ignore

    # Verify first file is deleted and second still exists
    with pytest.raises(FileNotFoundError):
        await backend.get_content_async(path1)
    assert await backend.get_content_async(path2) == content2


@pytest.mark.xdist_group("file_object")
async def test_file_object_invalid_init(storage_registry: StorageRegistry) -> None:
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
async def test_file_object_metadata_management(storage_registry: StorageRegistry) -> None:
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
async def test_file_object_to_dict(storage_registry: StorageRegistry) -> None:
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
        "backend": "local_test_store",
    }


@pytest.mark.xdist_group("file_object")
async def test_obstore_local_sign_urls(storage_registry: StorageRegistry) -> None:
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
async def test_file_object_save_with_different_data_types(storage_registry: StorageRegistry) -> None:
    """Test FileObject save with different data types."""
    backend = storage_registry.get_backend("local_test_store")
    test_content = b"Test content"
    file_path = "test_data_types.txt"

    # Test with bytes
    obj1 = FileObject(backend=backend, filename="test1.txt", to_filename=file_path, content=test_content)
    obj1.save()
    assert await obj1.get_content_async() == test_content

    # Test with Path
    import tempfile

    with tempfile.NamedTemporaryFile(mode="wb", delete=False) as f:
        f.write(test_content)
        temp_path = Path(f.name)

    obj2 = FileObject(backend=backend, filename="test2.txt", to_filename=file_path)
    await obj2.save_async(data=temp_path)
    assert await obj2.get_content_async() == test_content
    assert obj2.get_content() == test_content
    # Cleanup
    temp_path.unlink()


@pytest.mark.xdist_group("file_object")
async def test_file_object_pending_data_property(storage_registry: StorageRegistry) -> None:
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
async def test_file_object_delete_methods(storage_registry: StorageRegistry) -> None:
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
    assert storage_registry.default_backend == "advanced_alchemy.types.file_object.backends.obstore.ObstoreBackend"

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
    with pytest.raises(ImproperConfigurationError, match='No storage backend registered with key "nonexistent"'):
        storage_registry.get_backend("nonexistent")

    # Test unregister_backend with non-existent key
    storage_registry.unregister_backend("nonexistent")  # Should not raise an error

    # Test set_default_backend with invalid backend
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


@pytest.mark.xdist_group("file_object")
def test_file_object_sync_save_and_get_content(storage_registry: StorageRegistry) -> None:
    """Test FileObject synchronous save and get_content methods."""
    backend = storage_registry.get_backend("local_test_store")
    test_content = b"Test synchronous content"
    file_path = "test_sync_save.txt"

    # Create FileObject with content
    obj = FileObject(backend=backend, filename="test_sync.txt", to_filename=file_path, content=test_content)

    # Test synchronous save method
    updated_obj = obj.save()

    # Verify save worked correctly
    assert updated_obj is obj  # Should update in-place
    assert obj.path == file_path
    assert obj.size == len(test_content) or obj.size is None

    # Test synchronous get_content method
    retrieved_content = obj.get_content()
    assert retrieved_content == test_content

    # Clean up
    obj.delete()


@pytest.mark.xdist_group("file_object")
def test_file_object_save_with_source_path(storage_registry: StorageRegistry, tmp_path: Path) -> None:
    """Test FileObject save with source_path."""
    backend = storage_registry.get_backend("local_test_store")
    test_content = b"Test content from file"
    file_path = "test_source_path.txt"

    # Create a temporary file
    source_file = tmp_path / "source.txt"
    source_file.write_bytes(test_content)

    # Create FileObject with source_path
    obj = FileObject(backend=backend, filename="test_source.txt", to_filename=file_path, source_path=source_file)

    # Test save method with source_path
    obj.save()

    # Verify save worked correctly
    retrieved_content = obj.get_content()
    assert retrieved_content == test_content

    # Clean up
    obj.delete()


@pytest.mark.xdist_group("file_object")
def test_file_object_equality_and_hash(storage_registry: StorageRegistry) -> None:
    """Test FileObject __eq__ and __hash__ methods."""
    backend = storage_registry.get_backend("local_test_store")

    # Create two identical FileObjects
    obj1 = FileObject(backend=backend, filename="test.txt", to_filename="same_path.txt")
    obj2 = FileObject(backend=backend, filename="different.txt", to_filename="same_path.txt")

    # They should be equal because they have the same path and backend
    assert obj1 == obj2
    assert hash(obj1) == hash(obj2)

    # Create a different FileObject
    obj3 = FileObject(backend=backend, filename="test.txt", to_filename="different_path.txt")

    # They should not be equal because they have different paths
    assert obj1 != obj3
    assert hash(obj1) != hash(obj3)

    # Compare with a non-FileObject
    assert obj1 != "not a file object"


@pytest.mark.xdist_group("file_object")
def test_file_object_property_setters(storage_registry: StorageRegistry) -> None:
    """Test FileObject property setters."""
    backend = storage_registry.get_backend("local_test_store")

    obj = FileObject(backend=backend, filename="test.txt")

    # Test size property
    obj.size = 100
    assert obj.size == 100

    # Test last_modified property
    timestamp = 1234567890.0
    obj.last_modified = timestamp
    assert obj.last_modified == timestamp

    # Test checksum property
    obj.checksum = "abc123"
    assert obj.checksum == "abc123"

    # Test etag property
    obj.etag = "etag123"
    assert obj.etag == "etag123"

    # Test version_id property
    obj.version_id = "v1"
    assert obj.version_id == "v1"

    # Test metadata property
    new_metadata = {"key": "value"}
    obj.metadata = new_metadata
    assert obj.metadata == new_metadata


@pytest.mark.xdist_group("file_object")
def test_file_object_repr(storage_registry: StorageRegistry) -> None:
    """Test FileObject __repr__ method."""
    backend = storage_registry.get_backend("local_test_store")

    # Create a FileObject with all attributes set
    obj = FileObject(
        backend=backend,
        filename="test.txt",
        size=100,
        content_type="text/plain",
        last_modified=1234567890.0,
        etag="etag123",
        version_id="v1",
    )

    # Test __repr__ method
    repr_str = repr(obj)
    assert "FileObject" in repr_str
    assert "filename=test.txt" in repr_str
    assert "backend=local_test_store" in repr_str
    assert "size=100" in repr_str
    assert "content_type=text/plain" in repr_str
    assert "etag=etag123" in repr_str
    assert "last_modified=1234567890.0" in repr_str
    assert "version_id=v1" in repr_str


@pytest.mark.xdist_group("file_object")
def test_file_object_content_type_guessing(storage_registry: StorageRegistry) -> None:
    """Test content_type guessing from filename."""
    backend = storage_registry.get_backend("local_test_store")

    # Test common file types
    file_types = {
        "test.txt": "text/plain",
        "image.jpg": "image/jpeg",
        "doc.pdf": "application/pdf",
        "data.json": "application/json",
        "unknown": "application/octet-stream",
    }

    for filename, expected_type in file_types.items():
        obj = FileObject(backend=backend, filename=filename)
        assert obj.content_type == expected_type


@pytest.mark.xdist_group("file_object")
def test_file_object_save_no_data(storage_registry: StorageRegistry) -> None:
    """Test save method with no data."""
    backend = storage_registry.get_backend("local_test_store")

    # Create a FileObject with no content or source_path
    obj = FileObject(backend=backend, filename="test.txt")

    # Saving with no data should raise a TypeError
    with pytest.raises(TypeError, match="No data provided and no pending content/path found to save."):
        obj.save()


@pytest.mark.xdist_group("file_object")
async def test_file_object_save_async_no_data(storage_registry: StorageRegistry) -> None:
    """Test save_async method with no data."""
    backend = storage_registry.get_backend("local_test_store")

    # Create a FileObject with no content or source_path
    obj = FileObject(backend=backend, filename="test.txt")

    # Saving with no data should raise a TypeError
    with pytest.raises(TypeError, match="No data provided and no pending content/path found to save."):
        await obj.save_async()


@pytest.mark.xdist_group("file_object")
def test_obstore_backend_sqlalchemy_single_file_persist_sync(
    session: Session, storage_registry: StorageRegistry
) -> None:
    """Test saving and loading a model with a single StoredObject using synchronous SQLAlchemy session."""
    remove_listeners()
    file_content = b"SQLAlchemy Sync Integration Test"
    doc_name = "Sync Integration Doc"
    file_path = "sqlalchemy_single_sync.bin"

    # 1. Prepare FileObject and save via backend
    initial_obj = FileObject(
        backend="local_test_store",
        filename="report.bin",
        to_filename=file_path,
        content_type="application/octet-stream",
    )
    updated_obj = initial_obj.save(data=file_content)

    # 2. Create and save model instance
    doc = Document(name=doc_name, attachment=updated_obj)
    session.add(doc)
    session.commit()
    session.refresh(doc)

    assert doc.id is not None
    assert doc.attachment is not None
    assert isinstance(doc.attachment, FileObject)
    assert doc.attachment.filename == "sqlalchemy_single_sync.bin"
    assert doc.attachment.path == file_path
    assert doc.attachment.size == len(file_content) or doc.attachment.size is None
    assert doc.attachment.content_type == "application/octet-stream"
    assert doc.attachment.backend.key == "local_test_store"

    # 3. Retrieve content via loaded FileObject
    loaded_content = doc.attachment.get_content()
    assert loaded_content == file_content


@pytest.mark.xdist_group("file_object")
async def test_obstore_backend_listener_sqlalchemy_single_file_persist_async(
    async_session: AsyncSession, storage_registry: StorageRegistry
) -> None:
    """Test saving and loading a model with a single StoredObject using synchronous SQLAlchemy session."""
    setup_file_object_listeners()
    set_async_context(True)
    file_content = b"SQLAlchemy Async Integration Test"
    doc_name = "Sync Integration Doc"
    file_path = "sqlalchemy_single_async.bin"

    # 1. Prepare FileObject and save via backend
    initial_obj = FileObject(
        backend="local_test_store",
        filename="report.bin",
        to_filename=file_path,
        content_type="application/octet-stream",
        content=file_content,
    )
    # 2. Create and save model instance
    doc = Document(name=doc_name, attachment=initial_obj)
    async_session.add(doc)
    await async_session.commit()
    await async_session.refresh(doc)

    assert doc.id is not None
    assert doc.attachment is not None
    assert isinstance(doc.attachment, FileObject)
    assert doc.attachment.filename == "sqlalchemy_single_async.bin"
    assert doc.attachment.path == file_path
    assert doc.attachment.size == len(file_content) or doc.attachment.size is None
    assert doc.attachment.content_type == "application/octet-stream"
    assert doc.attachment.backend.key == "local_test_store"

    # 3. Retrieve content via loaded FileObject
    loaded_content = doc.attachment.get_content()
    assert loaded_content == file_content


@pytest.mark.xdist_group("file_object")
def test_obstore_backend_sqlalchemy_multiple_files_persist_sync(
    session: Session, storage_registry: StorageRegistry
) -> None:
    """Test saving and loading a model with multiple StoredObjects using synchronous SQLAlchemy session."""
    remove_listeners()
    backend = storage_registry.get_backend("local_test_store")
    img1_content = b"img_data_1_sync"
    img2_content = b"img_data_2_sync"
    doc_name = "Multi Image Doc Sync"
    img1_path = "img1_list_sync.jpg"
    img2_path = "img2_list_sync.png"

    # 1. Prepare FileObjects and save via backend
    obj1 = FileObject(
        backend=backend, filename="image1_list_sync.jpg", to_filename=img1_path, content_type="image/jpeg"
    )
    obj1_updated = obj1.save(img1_content)

    obj2 = FileObject(backend=backend, filename="image2_list_sync.png", to_filename=img2_path, content_type="image/png")
    obj2_updated = obj2.save(img2_content)

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
    assert loaded_obj1.filename == "img1_list_sync.jpg"
    assert loaded_obj1.path == img1_path
    assert loaded_obj1.size == len(img1_content) or loaded_obj1.size is None
    assert loaded_obj1.backend and loaded_obj1.backend.driver == backend.driver

    assert isinstance(loaded_obj2, FileObject)
    assert loaded_obj2.filename == "img2_list_sync.png"
    assert loaded_obj2.path == img2_path
    assert loaded_obj2.size == len(img2_content) or loaded_obj2.size is None
    assert loaded_obj2.backend and loaded_obj2.backend.driver == backend.driver

    # Verify content
    assert loaded_obj1.get_content() == img1_content
    assert loaded_obj2.get_content() == img2_content


@pytest.mark.xdist_group("file_object")
def test_obstore_backend_listener_delete_on_update_clear_sync(
    session: Session, storage_registry: StorageRegistry
) -> None:
    """Test listener deletes old file when attribute is cleared using synchronous SQLAlchemy session."""
    setup_file_object_listeners()
    backend = storage_registry.get_backend("local_test_store")
    old_content = b"File to clear sync"
    old_path = "clear_me_sync.log"

    # Save initial file and model
    old_obj = FileObject(backend=backend, filename="clear.log", to_filename=old_path, content=old_content)
    doc = Document(name="DocToClearSync", attachment=old_obj)
    session.add(doc)
    session.commit()
    session.refresh(doc)

    # Verify old file exists
    assert backend.get_content(old_path) == old_content

    # Clear the attachment
    doc.attachment = None
    session.add(doc)
    session.commit()
    session.refresh(doc)

    # Verify attachment is None
    assert doc.attachment is None

    # Verify the listener deleted the file from storage
    with pytest.raises(FileNotFoundError):
        backend.get_content(old_path)


@pytest.mark.flaky(reruns=5)
@pytest.mark.xdist_group("file_object")
async def test_obstore_backend_listener_delete_on_update_clear_async(
    async_session: AsyncSession, storage_registry: StorageRegistry
) -> None:
    """Test listener deletes old file when attribute is cleared using asynchronous SQLAlchemy session."""
    setup_file_object_listeners()
    set_async_context(True)
    backend = storage_registry.get_backend("local_test_store")
    old_content = b"File to clear sync"
    old_path = "clear_me_sync.log"

    # Save initial file and model
    old_obj = FileObject(backend=backend, filename="clear.log", to_filename=old_path, content=old_content)
    doc = Document(name="DocToClearSync", attachment=old_obj)
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

    # Verify attachment is None
    assert doc.attachment is None

    # Verify the listener deleted the file from storage
    with pytest.raises(FileNotFoundError):
        await backend.get_content_async(old_path)


@pytest.mark.flaky(reruns=5)
@pytest.mark.xdist_group("file_object")
def test_obstore_backend_listener_update_file_object_sync(session: Session, storage_registry: StorageRegistry) -> None:
    """Test listener deletes old file when attribute is updated and session committed using synchronous SQLAlchemy session."""
    setup_file_object_listeners()
    backend = storage_registry.get_backend("local_test_store")
    old_content = b"Old file content sync"
    new_content = b"New file content sync"
    old_path = "old_file_sync_update.txt"
    new_path = "new_file_sync_update.txt"

    # Save initial file and model
    old_obj = FileObject(
        backend=backend, filename="old_file_sync_update.txt", to_filename=old_path, content=old_content
    )
    doc = Document(name="DocToUpdateSync", attachment=old_obj)
    session.add(doc)
    session.commit()
    session.refresh(doc)

    # Verify old file exists
    assert backend.get_content(old_path) == old_content

    # Update the document's attachment (inline creation)
    new_obj = FileObject(
        backend=backend, filename="new_file_sync_update.txt", to_filename=new_path, content=new_content
    )
    doc.attachment = new_obj
    session.add(doc)  # Add again as it's modified
    session.commit()  # Listener should save new_obj and queue deletion of old_obj
    session.refresh(doc)

    # Verify new file exists and attachment updated
    assert backend.get_content(new_path) == new_content
    assert doc.attachment is not None and doc.attachment.path == new_path  # pyright: ignore

    # Verify the listener deleted the old file from storage
    with pytest.raises(FileNotFoundError):
        backend.get_content(old_path)


@pytest.mark.flaky(reruns=5)
@pytest.mark.xdist_group("file_object")
async def test_obstore_backend_listener_update_file_object_async(
    async_session: AsyncSession, storage_registry: StorageRegistry
) -> None:
    """Test listener deletes old file when attribute is updated and session committed using asynchronous SQLAlchemy session."""
    setup_file_object_listeners()
    backend = storage_registry.get_backend("local_test_store")
    old_content = b"Old file content sync"
    new_content = b"New file content sync"
    old_path = "old_file_async_update.txt"
    new_path = "new_file_async_update.txt"

    # Save initial file and model
    old_obj = FileObject(
        backend=backend, filename="old_file_async_update.txt", to_filename=old_path, content=old_content
    )
    doc = Document(name="DocToUpdateSync", attachment=old_obj)
    async_session.add(doc)
    await async_session.commit()
    await async_session.refresh(doc)

    # Verify old file exists
    assert backend.get_content(old_path) == old_content

    # Update the document's attachment (inline creation)
    new_obj = FileObject(
        backend=backend, filename="new_file_async_update.txt", to_filename=new_path, content=new_content
    )
    doc.attachment = new_obj
    async_session.add(doc)  # Add again as it's modified
    await async_session.commit()  # Listener should save new_obj and queue deletion of old_obj
    await async_session.refresh(doc)

    assert backend.get_content(new_path) == new_content
    assert doc.attachment is not None and doc.attachment.path == new_path  # pyright: ignore

    # Verify the listener deleted the old file from storage
    with pytest.raises(FileNotFoundError):
        backend.get_content(old_path)


@pytest.mark.flaky(reruns=5)
@pytest.mark.xdist_group("file_object")
def test_obstore_backend_listener_delete_multiple_removed_sync(
    session: Session, storage_registry: StorageRegistry
) -> None:
    """Test listener deletes files removed from a multiple list using synchronous SQLAlchemy session."""
    set_async_context(False)
    setup_file_object_listeners()
    backend = storage_registry.get_backend("local_test_store")
    content1 = b"img1_sync_multi"
    content2 = b"img2_sync_multi"
    path1 = "multi_del_1_sync.dat"
    path2 = "multi_del_2_sync.dat"

    # Save files
    obj1 = FileObject(backend=backend, filename=path1, content=content1)
    obj2 = FileObject(backend=backend, filename=path2, content=content2)

    # Create model with initial list
    doc = Document(name="MultiDeleteSyncTest", images=[obj1, obj2])
    session.add(doc)
    session.commit()
    session.refresh(doc)

    # Verify all files exist
    assert backend.get_content(path1) == content1
    assert backend.get_content(path2) == content2

    # Remove items from the list (triggers MutableList tracking)
    assert doc.images is not None
    current_images = list(doc.images)  # Create standard list copy
    removed_item = current_images.pop(1)  # Mutate copy
    assert removed_item.path == obj2.path
    del current_images[0]  # Mutate copy
    assert len(current_images) == 0
    doc.images = MutableList(current_images)  # Wrap in MutableList before reassignment

    session.add(doc)
    # Commit the session to trigger listener
    session.commit()
    session.refresh(doc)
    assert doc.images == []
    # Verify the listener deleted the files
    with pytest.raises(FileNotFoundError):
        backend.get_content(path1)
    with pytest.raises(FileNotFoundError):
        backend.get_content(path2)


@pytest.mark.flaky(reruns=5)
@pytest.mark.xdist_group("file_object")
async def test_obstore_backend_listener_delete_multiple_removed_async(
    async_session: AsyncSession, storage_registry: StorageRegistry
) -> None:
    """Test listener deletes files removed from a multiple list using asynchronous SQLAlchemy session."""
    set_async_context(True)
    setup_file_object_listeners()
    backend = storage_registry.get_backend("local_test_store")
    content1 = b"img1_async_multi"
    content2 = b"img2_async_multi"
    path1 = "multi_del_1_async.dat"
    path2 = "multi_del_2_async.dat"

    # Save files
    obj1 = FileObject(backend=backend, filename=path1, content=content1)
    obj2 = FileObject(backend=backend, filename=path2, content=content2)

    # Create model with initial list
    doc = Document(name="MultiDeleteAsyncTest", images=[obj1, obj2])
    async_session.add(doc)
    await async_session.commit()
    await async_session.refresh(doc)

    # Verify all files exist
    assert await backend.get_content_async(path1) == content1
    assert await backend.get_content_async(path2) == content2

    # Remove items from the list (triggers MutableList tracking)
    assert doc.images is not None
    current_images = list(doc.images)  # Create standard list copy
    removed_item = current_images.pop(1)  # Mutate copy
    assert removed_item.path == obj2.path
    del current_images[0]  # Mutate copy
    assert len(current_images) == 0
    doc.images = MutableList(current_images)  # Wrap in MutableList before reassignment

    # Commit the session to trigger listener
    await async_session.commit()
    await async_session.refresh(doc)

    # Verify the listener deleted the files
    with pytest.raises(FileNotFoundError):
        await backend.get_content_async(path1)
    with pytest.raises(FileNotFoundError):
        await backend.get_content_async(path2)
