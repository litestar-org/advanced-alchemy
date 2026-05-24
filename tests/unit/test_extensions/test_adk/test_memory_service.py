from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, Optional, cast

import pytest
from sqlalchemy import DateTime, Integer, String, Text, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Mapped, mapped_column, registry

from advanced_alchemy.extensions.adk.models import ADKMemoryModelMixin
from advanced_alchemy.types import JsonB
from tests.unit.test_extensions.test_adk.fixtures import SampleADKMemory, metadata


@pytest.fixture
async def memory_session(tmp_path: Path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    from advanced_alchemy.extensions.adk.memory import ADKAsyncMemoryService

    _ = ADKAsyncMemoryService
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'adk-memory.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(metadata.create_all)
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


def _event(event_id: str, text: str, *, author: str = "user", timestamp: float = 123.5):
    from google.adk.events.event import Event
    from google.genai import types

    return Event(
        id=event_id,
        invocation_id=f"invocation-{event_id}",
        author=author,
        timestamp=timestamp,
        content=types.Content(role=author, parts=[types.Part(text=text)]),
    )


def _vector_memory_model() -> type[Any]:
    pgvector = pytest.importorskip("pgvector.sqlalchemy")

    mapper_registry = registry()

    @mapper_registry.mapped
    class VectorMemory:
        __tablename__ = "test_adk_vector_memory_entries"

        id: Mapped[int] = mapped_column(Integer, primary_key=True)
        memory_id: Mapped[str] = mapped_column(String(128))
        app_name: Mapped[str] = mapped_column(String(128))
        user_id: Mapped[str] = mapped_column(String(128))
        session_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
        event_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
        author: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
        timestamp: Mapped[Any] = mapped_column(DateTime(timezone=True))
        content_json: Mapped[dict[str, Any]] = mapped_column(JsonB)
        content_text: Mapped[str] = mapped_column(Text)
        metadata_json: Mapped[dict[str, Any]] = mapped_column(JsonB)
        embedding: Mapped[Optional[list[float]]] = mapped_column(pgvector.Vector(3), nullable=True)

    return VectorMemory


class _ScalarResult:
    def all(self) -> list[Any]:
        return []


class _PostgreSQLBind:
    def __init__(self) -> None:
        from sqlalchemy.dialects import postgresql

        self.dialect = postgresql.dialect()


class _RecordingAsyncSession:
    def __init__(self) -> None:
        self.added: list[Any] = []
        self.flushed = False

    def get_bind(self) -> _PostgreSQLBind:
        return _PostgreSQLBind()

    async def scalars(self, statement: object) -> _ScalarResult:
        return _ScalarResult()

    def add(self, instance: object) -> None:
        self.added.append(instance)

    async def flush(self) -> None:
        self.flushed = True


async def test_memory_service_add_session_deduplicates_and_searches_content(
    memory_session: async_sessionmaker[AsyncSession],
) -> None:
    from google.adk.memory.base_memory_service import BaseMemoryService
    from google.adk.sessions.session import Session

    from advanced_alchemy.extensions.adk.memory import ADKAsyncMemoryService

    async with memory_session() as db_session:
        service = ADKAsyncMemoryService(db_session, memory_model=SampleADKMemory)
        session = Session(
            app_name="app",
            user_id="user",
            id="session",
            events=[
                _event("event-1", "Remember that my favorite color is blue."),
                _event("event-2", "This turn mentions a temporary detail."),
            ],
        )

        assert isinstance(service, BaseMemoryService)

        await service.add_session_to_memory(session)
        await service.add_session_to_memory(session)
        await db_session.commit()

        assert await db_session.scalar(select(func.count()).select_from(SampleADKMemory)) == 2

        response = await service.search_memory(app_name="app", user_id="user", query="BLUE")

        assert len(response.memories) == 1
        assert response.memories[0].id == "event-1"
        assert response.memories[0].author == "user"
        assert response.memories[0].content.parts[0].text == "Remember that my favorite color is blue."
        assert response.memories[0].timestamp is not None


async def test_memory_service_add_events_to_memory_preserves_metadata_and_scope(
    memory_session: async_sessionmaker[AsyncSession],
) -> None:
    from advanced_alchemy.extensions.adk.memory import ADKAsyncMemoryService

    async with memory_session() as db_session:
        service = ADKAsyncMemoryService(db_session, memory_model=SampleADKMemory)
        await service.add_events_to_memory(
            app_name="app",
            user_id="user",
            session_id="session",
            events=[_event("event-1", "Project codename is Helios.")],
            custom_metadata={"source": "delta"},
        )
        await service.add_events_to_memory(
            app_name="app",
            user_id="other-user",
            session_id="session",
            events=[_event("event-2", "Project codename is Helios.")],
        )
        await db_session.commit()

        response = await service.search_memory(app_name="app", user_id="user", query="helios")
        stored = await db_session.scalar(select(SampleADKMemory).where(SampleADKMemory.event_id == "event-1"))

        assert [memory.id for memory in response.memories] == ["event-1"]
        assert stored is not None
        assert stored.session_id == "session"
        assert stored.metadata_json == {"source": "delta"}


async def test_memory_service_add_memory_direct_writes_are_searchable(
    memory_session: async_sessionmaker[AsyncSession],
) -> None:
    from google.adk.memory.memory_entry import MemoryEntry
    from google.genai import types

    from advanced_alchemy.extensions.adk.memory import ADKAsyncMemoryService

    async with memory_session() as db_session:
        service = ADKAsyncMemoryService(db_session, memory_model=SampleADKMemory)
        await service.add_memory(
            app_name="app",
            user_id="user",
            memories=[
                MemoryEntry(
                    id="manual-1",
                    author="agent",
                    content=types.Content(role="model", parts=[types.Part(text="The launch window is Friday.")]),
                    custom_metadata={"kind": "manual"},
                ),
            ],
        )
        await db_session.commit()

        response = await service.search_memory(app_name="app", user_id="user", query="friday")

        assert len(response.memories) == 1
        assert response.memories[0].id == "manual-1"
        assert response.memories[0].custom_metadata == {"kind": "manual"}


def test_vector_memory_model_import_is_optional() -> None:
    pytest.importorskip("pgvector")

    from advanced_alchemy.extensions.adk.memory.vector import ADKVectorMemoryModelMixin

    assert ADKVectorMemoryModelMixin.__abstract__ is True


async def test_memory_service_auto_writes_embeddings_for_vector_memory_model() -> None:
    from google.adk.memory.memory_entry import MemoryEntry
    from google.genai import types

    from advanced_alchemy.extensions.adk.memory import ADKAsyncMemoryService

    session = _RecordingAsyncSession()
    vector_model = cast("type[ADKMemoryModelMixin]", _vector_memory_model())

    async def embed_text(text: str) -> list[float]:
        assert "launch" in text.lower()
        return [0.1, 0.2, 0.3]

    service = ADKAsyncMemoryService(
        cast("AsyncSession", session),
        memory_model=vector_model,
        embedding_provider=embed_text,
    )
    await service.add_memory(
        app_name="app",
        user_id="user",
        memories=[
            MemoryEntry(
                id="manual-1",
                author="agent",
                content=types.Content(role="model", parts=[types.Part(text="The launch window is Friday.")]),
            ),
        ],
    )

    assert session.flushed is True
    assert session.added[0].embedding == [0.1, 0.2, 0.3]


async def test_memory_service_auto_prefers_vector_search_when_available() -> None:
    from sqlalchemy.dialects import postgresql

    from advanced_alchemy.extensions.adk.memory import ADKAsyncMemoryService

    session = _RecordingAsyncSession()
    vector_model = cast("type[ADKMemoryModelMixin]", _vector_memory_model())
    calls: list[str] = []

    def embed_text(text: str) -> list[float]:
        calls.append(text)
        return [0.3, 0.2, 0.1]

    service = ADKAsyncMemoryService(
        cast("AsyncSession", session),
        memory_model=vector_model,
        embedding_provider=embed_text,
    )

    statement = await service._search_statement(app_name="app", user_id="user", query="billing")
    compiled = str(statement.compile(dialect=postgresql.dialect()))

    assert calls == ["billing"]
    assert "<=>" in compiled
    assert "to_tsvector" not in compiled
