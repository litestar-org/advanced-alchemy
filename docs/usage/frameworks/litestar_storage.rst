=====================================
Litestar File and Object Storage
=====================================

Advanced Alchemy integrates declarative file and object storage with Litestar via :class:`~advanced_alchemy.types.StoredObject`, :class:`~advanced_alchemy.types.FileObject`, and the global :data:`~advanced_alchemy.types.storages` registry.

Registering Storage Backends
----------------------------

Register a local filesystem URL, cloud bucket URL (S3, GCS, Azure Blob Storage via ``obstore`` or ``fsspec``), or explicit :class:`~advanced_alchemy.types.StorageBackend` instance with :data:`~advanced_alchemy.types.storages`:

.. literalinclude:: /examples/litestar/session_store.py
    :language: python
    :pyobject: create_app

Declarative Model Columns
-------------------------

Declare :class:`~advanced_alchemy.types.StoredObject` columns on your SQLAlchemy models. The SQLAlchemy session tracker (:class:`~advanced_alchemy._listeners.FileObjectSessionTracker`) automatically uploads pending content on transaction commit and deletes orphaned objects when records are removed or replaced:

.. literalinclude:: /examples/litestar/session_store.py
    :language: python
    :start-at: class AttachmentModel
    :end-before: class AttachmentRepository

Handling Uploads in Route Handlers
----------------------------------

Construct a :class:`~advanced_alchemy.types.FileObject` with ``content`` (raw ``bytes`` or an async byte stream such as Litestar's ``UploadFile.read()``) or ``source_path`` and pass it directly to your repository or service:

.. literalinclude:: /examples/litestar/session_store.py
    :language: python
    :pyobject: upload_attachment

Custom JSON Serialization
-------------------------

When storing ``StoredObject`` metadata on dialects that require custom JSON serializers (or when customizing Litestar's ``type_encoders``), configure ``json_serializer`` and ``json_deserializer`` on :class:`~advanced_alchemy.extensions.litestar.SQLAlchemyAsyncConfig` or :data:`~advanced_alchemy.types.storages`:

.. code-block:: python

    from advanced_alchemy.extensions.litestar import EngineConfig, SQLAlchemyAsyncConfig
    from advanced_alchemy.utils.serialization import decode_json, encode_json

    alchemy_config = SQLAlchemyAsyncConfig(
        connection_string="sqlite+aiosqlite:///:memory:",
        engine_config=EngineConfig(
            json_serializer=encode_json,
            json_deserializer=decode_json,
        ),
    )

Complete Runnable Example
-------------------------

The combined session store and file storage example in ``docs/examples/litestar/session_store.py`` runs inside a sandboxed ``tempfile.TemporaryDirectory()``:

.. literalinclude:: /examples/litestar/session_store.py
    :language: python

Related Documentation
---------------------

- :doc:`/usage/frameworks/litestar` — Core Litestar setup, DTOs, repositories, and controllers.
- :doc:`/usage/frameworks/litestar_sessions` — Request-scoped sessions and server-side session stores.
- :doc:`/reference/types` — :class:`~advanced_alchemy.types.StoredObject` and :class:`~advanced_alchemy.types.FileObject` API reference.
