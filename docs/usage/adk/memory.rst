======
Memory
======

``ADKAsyncMemoryService`` persists long-term ADK memory entries in a user-owned
model that subclasses ``ADKMemoryModelMixin``.

.. code-block:: python

    from advanced_alchemy.extensions.adk.memory import ADKAsyncMemoryService

    memory_service = ADKAsyncMemoryService(
        db_session,
        memory_model=ADKMemory,
    )

    await memory_service.add_session_to_memory(session)
    results = await memory_service.search_memory(
        app_name="support-bot",
        user_id="user-123",
        query="billing",
    )

On PostgreSQL, the service uses full-text search by default. Other dialects use
portable ``ILIKE`` matching against the text and JSON content columns.

Vector Memory
-------------

Install the optional vector extra to add the pgvector dependency:

.. code-block:: console

    pip install "advanced-alchemy[adk-vector]"

Then subclass ``ADKVectorMemoryModelMixin`` instead of ``ADKMemoryModelMixin``:

.. code-block:: python

    from advanced_alchemy.extensions.adk.memory.vector import ADKVectorMemoryModelMixin


    class ADKVectorMemory(ADKVectorMemoryModelMixin):
        __tablename__ = "adk_vector_memory_entries"

The vector mixin adds an ``embedding`` column and leaves embedding generation to
the application so projects can choose their own model and dimensionality policy.
