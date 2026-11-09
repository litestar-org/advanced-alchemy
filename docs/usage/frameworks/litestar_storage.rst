=================================
Litestar File and Object Storage
=================================

Uploading user avatars, invoices, or attachments usually creates headaches: if a database commit fails after uploading to S3, you get orphaned files; if a row is deleted, someone forgets to delete the file in storage.

``StoredObject`` and ``FileObject`` keep your files and database rows in lockstep—uploading files when your transaction commits and deleting old files automatically when rows are removed or replaced.

Uploading Files in Three Steps
------------------------------

.. tab-set::

    .. tab-item:: 1. Model Column

        .. literalinclude:: /examples/litestar/session_store.py
            :language: python
            :start-at: class AttachmentModel
            :end-before: class AttachmentRepository

    .. tab-item:: 2. Upload Route

        .. literalinclude:: /examples/litestar/session_store.py
            :language: python
            :pyobject: upload_attachment

    .. tab-item:: 3. Register Storage

        .. literalinclude:: /examples/litestar/session_store.py
            :language: python
            :pyobject: create_app

Custom JSON Encoders
--------------------

If your database driver needs custom JSON helpers for file metadata, pass ``json_serializer`` and ``json_deserializer`` on ``EngineConfig``:

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

.. dropdown:: View Complete Litestar Upload & Store App
    :icon: code

    .. literalinclude:: /examples/litestar/session_store.py
        :language: python

Related Guides
--------------

* :doc:`/usage/frameworks/litestar` — Core Litestar setup and controllers.
* :doc:`/usage/modeling/security_and_storage_types` — Storage backends (local disk, S3, GCS, Azure).
* :doc:`/reference/types` — ``StoredObject`` and ``FileObject`` API reference.
