from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session

from tests.unit.test_extensions.test_adk.fixtures import (
    SESSION_MODEL_CONFIG,
    SampleADKAppState,
    SampleADKEvent,
    SampleADKSession,
    SampleADKUserState,
    metadata,
)


@pytest.fixture
async def session_factory(tmp_path: Path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'adk.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(metadata.create_all)
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


def test_extract_state_delta_routes_adk_scoped_keys() -> None:
    from advanced_alchemy.extensions.adk._state import extract_state_delta

    assert extract_state_delta(
        {
            "app:theme": "dark",
            "user:name": "Ada",
            "session_counter": 3,
            "temp:trace": "drop",
        },
    ) == {
        "app": {"theme": "dark"},
        "user": {"name": "Ada"},
        "session": {"session_counter": 3},
    }


async def test_session_service_create_get_list_and_delete(session_factory: async_sessionmaker[AsyncSession]) -> None:
    from google.adk.sessions.base_session_service import BaseSessionService, GetSessionConfig

    from advanced_alchemy.extensions.adk import ADKAsyncSessionService

    async with session_factory() as db_session:
        service = ADKAsyncSessionService(db_session, model_config=SESSION_MODEL_CONFIG)

        assert isinstance(service, BaseSessionService)

        created = await service.create_session(
            app_name="app",
            user_id="user",
            session_id="custom-session",
            state={
                "app:theme": "dark",
                "user:name": "Ada",
                "session_counter": 3,
                "temp:trace": "drop",
            },
        )

        assert created.id == "custom-session"
        assert created.state == {
            "app:theme": "dark",
            "user:name": "Ada",
            "session_counter": 3,
        }

        stored_session = await db_session.scalar(select(SampleADKSession))
        stored_app_state = await db_session.scalar(select(SampleADKAppState))
        stored_user_state = await db_session.scalar(select(SampleADKUserState))
        assert stored_session is not None
        assert stored_session.state == {"session_counter": 3}
        assert stored_app_state is not None
        assert stored_app_state.state == {"theme": "dark"}
        assert stored_user_state is not None
        assert stored_user_state.state == {"name": "Ada"}

        loaded = await service.get_session(
            app_name="app",
            user_id="user",
            session_id="custom-session",
            config=GetSessionConfig(num_recent_events=0),
        )
        assert loaded is not None
        assert loaded.state == {
            "app:theme": "dark",
            "user:name": "Ada",
            "session_counter": 3,
        }
        assert loaded.events == []

        listed = await service.list_sessions(app_name="app", user_id="user")
        assert [session.id for session in listed.sessions] == ["custom-session"]

        await service.delete_session(app_name="app", user_id="user", session_id="custom-session")
        assert await service.get_session(app_name="app", user_id="user", session_id="custom-session") is None


async def test_session_service_append_event_persists_state_and_filters_temp(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    from google.adk.events.event import Event
    from google.adk.events.event_actions import EventActions

    from advanced_alchemy.extensions.adk import ADKAsyncSessionService

    async with session_factory() as db_session:
        service = ADKAsyncSessionService(db_session, model_config=SESSION_MODEL_CONFIG)
        session = await service.create_session(app_name="app", user_id="user", session_id="session")
        event = Event(
            id="event-1",
            invocation_id="invocation",
            author="agent",
            timestamp=123.5,
            actions=EventActions(
                state_delta={
                    "app:theme": "light",
                    "user:name": "Grace",
                    "turn": 1,
                    "temp:trace": "drop",
                },
            ),
        )

        returned = await service.append_event(session, event)

        assert returned is event
        assert session.events == [event]
        assert session.state["temp:trace"] == "drop"
        assert session.state["app:theme"] == "light"
        assert session.state["user:name"] == "Grace"
        assert session.state["turn"] == 1

        stored_event = await db_session.scalar(select(SampleADKEvent))
        stored_session = await db_session.scalar(select(SampleADKSession))
        stored_app_state = await db_session.scalar(select(SampleADKAppState))
        stored_user_state = await db_session.scalar(select(SampleADKUserState))
        assert stored_event is not None
        assert stored_event.event_data["actions"]["state_delta"] == {
            "app:theme": "light",
            "user:name": "Grace",
            "turn": 1,
        }
        assert stored_session is not None
        assert stored_session.state == {"turn": 1}
        assert stored_app_state is not None
        assert stored_app_state.state == {"theme": "light"}
        assert stored_user_state is not None
        assert stored_user_state.state == {"name": "Grace"}


async def test_session_service_rejects_stale_session_appends(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    from google.adk.events.event import Event
    from google.adk.events.event_actions import EventActions

    from advanced_alchemy.extensions.adk import ADKAsyncSessionService

    async with session_factory() as db_session:
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

        with pytest.raises(ValueError, match="Session has been modified"):
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


async def test_session_service_get_session_applies_event_config(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    from google.adk.events.event import Event
    from google.adk.events.event_actions import EventActions
    from google.adk.sessions.base_session_service import GetSessionConfig

    from advanced_alchemy.extensions.adk import ADKAsyncSessionService

    async with session_factory() as db_session:
        service = ADKAsyncSessionService(db_session, model_config=SESSION_MODEL_CONFIG)
        session = await service.create_session(app_name="app", user_id="user", session_id="session")

        for index in range(3):
            await service.append_event(
                session,
                Event(
                    id=f"event-{index}",
                    invocation_id=f"invocation-{index}",
                    author="agent",
                    timestamp=123.5 + index,
                    actions=EventActions(state_delta={"turn": index}),
                ),
            )

        loaded = await service.get_session(
            app_name="app",
            user_id="user",
            session_id="session",
            config=GetSessionConfig(num_recent_events=2, after_timestamp=124.0),
        )

        assert loaded is not None
        assert [event.id for event in loaded.events] == ["event-1", "event-2"]


async def test_session_service_get_session_rejects_identity_mismatch(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    from advanced_alchemy.extensions.adk import ADKAsyncSessionService

    async with session_factory() as db_session:
        service = ADKAsyncSessionService(db_session, model_config=SESSION_MODEL_CONFIG)
        await service.create_session(app_name="app", user_id="user", session_id="session")

        with pytest.raises(PermissionError, match="does not belong"):
            await service.get_session(app_name="other", user_id="user", session_id="session")


def test_sync_session_service_create_get_and_delete(tmp_path: Path) -> None:
    from advanced_alchemy.extensions.adk import ADKSyncSessionService

    engine = create_engine(f"sqlite:///{tmp_path / 'adk-sync.db'}")
    metadata.create_all(engine)

    with Session(engine, expire_on_commit=False) as db_session:
        service = ADKSyncSessionService(db_session, model_config=SESSION_MODEL_CONFIG)

        created = service.create_session(
            app_name="app",
            user_id="user",
            session_id="sync-session",
            state={"app:theme": "dark", "sync": True},
        )

        assert created.id == "sync-session"
        assert created.state == {"app:theme": "dark", "sync": True}

        loaded = service.get_session(app_name="app", user_id="user", session_id="sync-session")
        assert loaded is not None
        assert loaded.state == {"app:theme": "dark", "sync": True}

        service.delete_session(app_name="app", user_id="user", session_id="sync-session")
        assert service.get_session(app_name="app", user_id="user", session_id="sync-session") is None
