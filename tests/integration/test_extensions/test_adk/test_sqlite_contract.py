import sys
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

if sys.version_info < (3, 10):
    pytest.skip("google-adk v2 requires Python 3.10+", allow_module_level=True)

from tests.unit.test_extensions.test_adk.fixtures import SESSION_MODEL_CONFIG, SampleADKMemory, metadata

pytestmark = [pytest.mark.integration, pytest.mark.aiosqlite]


@pytest.fixture
async def adk_session_factory(tmp_path: Path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'adk-contract.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(metadata.create_all)
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


class TestSQLiteADKContract:
    async def test_session_service_contract(self, adk_session_factory: async_sessionmaker[AsyncSession]) -> None:
        from google.adk.events.event import Event
        from google.adk.events.event_actions import EventActions

        from advanced_alchemy.extensions.adk import ADKAsyncSessionService, StaleSessionError

        async with adk_session_factory() as db_session:
            service = ADKAsyncSessionService(db_session, model_config=SESSION_MODEL_CONFIG)
            first = await service.create_session(app_name="app", user_id="user", session_id="session")
            second = await service.get_session(app_name="app", user_id="user", session_id="session")
            assert second is not None

            await service.append_event(
                first,
                Event(
                    id="event-1",
                    invocation_id="invocation-1",
                    author="agent",
                    timestamp=123.5,
                    actions=EventActions(state_delta={"turn": 1}),
                ),
            )

            loaded = await service.get_session(app_name="app", user_id="user", session_id="session")
            assert loaded is not None
            assert loaded.state["turn"] == 1
            assert [event.id for event in loaded.events] == ["event-1"]

            with pytest.raises(StaleSessionError):
                await service.append_event(
                    second,
                    Event(
                        id="event-2",
                        invocation_id="invocation-2",
                        author="agent",
                        timestamp=124.5,
                        actions=EventActions(state_delta={"turn": 2}),
                    ),
                )

    async def test_memory_service_contract(self, adk_session_factory: async_sessionmaker[AsyncSession]) -> None:
        from google.adk.events.event import Event
        from google.genai import types

        from advanced_alchemy.extensions.adk.memory import ADKAsyncMemoryService

        async with adk_session_factory() as db_session:
            service = ADKAsyncMemoryService(db_session, memory_model=SampleADKMemory)
            await service.add_events_to_memory(
                app_name="app",
                user_id="user",
                session_id="session",
                events=[
                    Event(
                        id="event-1",
                        invocation_id="invocation",
                        author="agent",
                        timestamp=123.5,
                        content=types.Content(parts=[types.Part(text="billing plan changed")]),
                    ),
                ],
            )

            results = await service.search_memory(app_name="app", user_id="user", query="billing")

            assert [memory.id for memory in results.memories] == ["event-1"]
