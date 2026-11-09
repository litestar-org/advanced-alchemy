import datetime

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.schema import CreateIndex

from tests.unit.test_extensions.test_adk.fixtures import (
    SampleADKAppState,
    SampleADKArtifact,
    SampleADKEvent,
    SampleADKMemory,
    SampleADKSession,
    SampleADKUserState,
    metadata,
)


def test_adk_model_mixins_create_user_owned_tables_with_expected_columns() -> None:
    from advanced_alchemy.types.datetime import DateTimeUTC
    from advanced_alchemy.types.file_object import StoredObject

    assert SampleADKSession.__tablename__ == "test_adk_sessions"
    assert SampleADKEvent.__tablename__ == "test_adk_events"
    assert SampleADKAppState.__tablename__ == "test_adk_app_states"
    assert SampleADKUserState.__tablename__ == "test_adk_user_states"
    assert SampleADKArtifact.__tablename__ == "test_adk_artifacts"
    assert SampleADKMemory.__tablename__ == "test_adk_memory_entries"

    assert "owner_id" in SampleADKSession.__table__.c
    assert [column.name for column in SampleADKSession.__table__.primary_key.columns] == ["id"]
    assert [column.name for column in SampleADKEvent.__table__.primary_key.columns] == ["id"]

    session_unique = next(
        constraint
        for constraint in SampleADKSession.__table__.constraints
        if constraint.name == "uq_test_adk_sessions_adk_session"
    )
    assert [column.name for column in session_unique.columns] == ["app_name", "user_id", "session_id"]

    event_index = next(
        index for index in SampleADKEvent.__table__.indexes if index.name == "ix_test_adk_events_adk_session_ts"
    )
    assert "timestamp DESC" in str(CreateIndex(event_index).compile(dialect=create_engine("sqlite://").dialect))

    assert SampleADKSession.__table__.c.state.type.python_type is dict
    assert SampleADKEvent.__table__.c.event_data.nullable is True
    assert isinstance(SampleADKSession.__table__.c.create_time.type, DateTimeUTC)
    assert SampleADKSession.__table__.c.create_time.type.fsp == 6
    assert SampleADKEvent.__table__.c.timestamp.type.fsp == 6
    assert isinstance(SampleADKArtifact.__table__.c.blob.type, StoredObject)


def test_adk_mixins_autogenerate_with_advanced_alchemy_metadata() -> None:
    engine = create_engine("sqlite://")
    metadata.create_all(engine)
    inspector = inspect(engine)

    assert {
        "test_adk_app_states",
        "test_adk_artifacts",
        "test_adk_events",
        "test_adk_memory_entries",
        "test_adk_sessions",
        "test_adk_user_states",
    }.issubset(inspector.get_table_names())
    assert "owner_id" in {column["name"] for column in inspector.get_columns("test_adk_sessions")}


def test_session_update_marker_matches_upstream_microsecond_format() -> None:
    session = SampleADKSession(
        app_name="app",
        user_id="user",
        session_id="session",
        state={},
        update_time=datetime.datetime(2026, 5, 24, 12, 30, 1, 123, tzinfo=datetime.timezone.utc),
    )

    assert session.get_update_marker() == "2026-05-24T12:30:01.000123+00:00"
    assert session.get_update_timestamp(is_sqlite=False) == pytest.approx(1779625801.000123)


def test_model_helpers_round_trip_adk_session_and_event_when_extra_is_installed() -> None:
    event_module = pytest.importorskip("google.adk.events.event")
    session_module = pytest.importorskip("google.adk.sessions.session")

    session = session_module.Session(id="session", app_name="app", user_id="user", state={"key": "value"})
    event = event_module.Event(id="event", invocation_id="invocation", author="agent", timestamp=123.5)
    stored_event = SampleADKEvent.from_event(session, event)

    assert stored_event.event_id == "event"
    assert stored_event.session_id == "session"
    assert stored_event.event_data["author"] == "agent"

    round_tripped_event = stored_event.to_event()
    assert round_tripped_event.id == "event"
    assert round_tripped_event.invocation_id == "invocation"

    stored_session = SampleADKSession(
        app_name="app",
        user_id="user",
        session_id="session",
        state={},
        update_time=datetime.datetime.fromtimestamp(123.5, tz=datetime.timezone.utc),
    )
    round_tripped_session = stored_session.to_session(state={"key": "value"}, events=[round_tripped_event])
    assert round_tripped_session.id == "session"
    assert round_tripped_session.state == {"key": "value"}
    assert round_tripped_session.events[0].id == "event"
    assert round_tripped_session._storage_update_marker == stored_session.get_update_marker()
