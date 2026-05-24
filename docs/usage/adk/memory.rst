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

The vector mixin adds an ``embedding`` column. The memory service automatically
uses vector search when all vector components are available:

- the configured memory model has an ``embedding`` column,
- an ``embedding_provider`` is configured,
- the database bind is PostgreSQL.

.. code-block:: python

    async def embed_text(text: str) -> list[float]:
        ...


    memory_service = ADKAsyncMemoryService(
        db_session,
        memory_model=ADKVectorMemory,
        embedding_provider=embed_text,
    )

If any component is missing, the service falls back to PostgreSQL full-text
search or portable ``ILIKE`` matching. Set ``use_vector=True`` to require vector
search and raise an error when the vector components are not available.
