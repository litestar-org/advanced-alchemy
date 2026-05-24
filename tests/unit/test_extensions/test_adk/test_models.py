import datetime

import pytest
from sqlalchemy import Column, String, create_engine, inspect
from sqlalchemy.schema import CreateIndex


def test_v1_models_match_adk_table_contract() -> None:
    from advanced_alchemy.extensions.adk.v1 import (
        ADKAppState,
        ADKEvent,
        ADKMetadata,
        ADKSession,
        ADKUserState,
        metadata,
    )
    from advanced_alchemy.types.datetime import DateTimeUTC

    assert metadata is ADKSession.metadata
    assert ADKSession.__tablename__ == "sessions"
    assert ADKEvent.__tablename__ == "events"
    assert ADKAppState.__tablename__ == "app_states"
    assert ADKUserState.__tablename__ == "user_states"
    assert ADKMetadata.__tablename__ == "adk_internal_metadata"

    assert [column.name for column in ADKSession.__table__.primary_key.columns] == ["app_name", "user_id", "id"]
    assert [column.name for column in ADKEvent.__table__.primary_key.columns] == [
        "id",
        "app_name",
        "user_id",
        "session_id",
    ]
    assert [column.name for column in ADKAppState.__table__.primary_key.columns] == ["app_name"]
    assert [column.name for column in ADKUserState.__table__.primary_key.columns] == ["app_name", "user_id"]
    assert [column.name for column in ADKMetadata.__table__.primary_key.columns] == ["key"]

    foreign_key = next(iter(ADKEvent.__table__.foreign_key_constraints))
    assert foreign_key.ondelete == "CASCADE"
    assert [element.parent.name for element in foreign_key.elements] == ["app_name", "user_id", "session_id"]
    assert [element.column.name for element in foreign_key.elements] == ["app_name", "user_id", "id"]

    index = next(index for index in ADKEvent.__table__.indexes if index.name == "idx_events_app_user_session_ts")
    assert "timestamp DESC" in str(CreateIndex(index).compile(dialect=create_engine("sqlite://").dialect))

    assert ADKSession.__table__.c.state.type.python_type is dict
    assert ADKEvent.__table__.c.event_data.nullable is True
    assert isinstance(ADKSession.__table__.c.create_time.type, DateTimeUTC)
    assert ADKSession.__table__.c.create_time.type.fsp == 6
    assert ADKSession.__table__.c.update_time.type.fsp == 6
    assert ADKEvent.__table__.c.timestamp.type.fsp == 6


def test_v1_metadata_create_all_produces_expected_sqlite_schema() -> None:
    from advanced_alchemy.extensions.adk.v1 import metadata

    engine = create_engine("sqlite://")
    metadata.create_all(engine)
    inspector = inspect(engine)

    assert set(inspector.get_table_names()) == {
        "adk_internal_metadata",
        "app_states",
        "events",
        "sessions",
        "user_states",
    }
    assert inspector.get_pk_constraint("sessions")["constrained_columns"] == ["app_name", "user_id", "id"]
    assert inspector.get_pk_constraint("events")["constrained_columns"] == ["id", "app_name", "user_id", "session_id"]
    assert inspector.get_foreign_keys("events")[0]["referred_table"] == "sessions"
    assert inspector.get_foreign_keys("events")[0]["options"] == {"ondelete": "CASCADE"}


def test_schema_registry_returns_v1_model_bundle() -> None:
    from advanced_alchemy.extensions.adk import ADKSchemaVersion, get_models
    from advanced_alchemy.extensions.adk.v1 import ADKEvent, ADKSession, metadata

    models = get_models(ADKSchemaVersion.V1)

    assert models.metadata is metadata
    assert models.session_model is ADKSession
    assert models.event_model is ADKEvent


def test_with_owner_column_returns_createable_session_model() -> None:
    from advanced_alchemy.extensions.adk.v1 import ADKSession, with_owner_column

    OwnedSession = with_owner_column(ADKSession, Column("owner_id", String(64), nullable=False))

    assert "owner_id" in OwnedSession.__table__.c
    assert OwnedSession.__table__.c.owner_id.type.length == 64

    engine = create_engine("sqlite://")
    OwnedSession.__table__.metadata.create_all(engine)
    assert "owner_id" in {column["name"] for column in inspect(engine).get_columns("sessions")}


def test_session_update_marker_matches_upstream_microsecond_format() -> None:
    from advanced_alchemy.extensions.adk.v1 import ADKSession

    session = ADKSession(
        app_name="app",
        user_id="user",
        id="session",
        state={},
        update_time=datetime.datetime(2026, 5, 24, 12, 30, 1, 123, tzinfo=datetime.timezone.utc),
    )

    assert session.get_update_marker() == "2026-05-24T12:30:01.000123+00:00"
    assert session.get_update_timestamp(is_sqlite=False) == pytest.approx(1779625801.000123)


def test_model_helpers_round_trip_adk_session_and_event_when_extra_is_installed() -> None:
    event_module = pytest.importorskip("google.adk.events.event")
    session_module = pytest.importorskip("google.adk.sessions.session")

    from advanced_alchemy.extensions.adk.v1 import ADKEvent, ADKSession

    session = session_module.Session(id="session", app_name="app", user_id="user", state={"key": "value"})
    event = event_module.Event(id="event", invocation_id="invocation", author="agent", timestamp=123.5)
    stored_event = ADKEvent.from_event(session, event)

    assert stored_event.id == "event"
    assert stored_event.session_id == "session"
    assert stored_event.event_data["author"] == "agent"

    round_tripped_event = stored_event.to_event()
    assert round_tripped_event.id == "event"
    assert round_tripped_event.invocation_id == "invocation"

    stored_session = ADKSession(
        app_name="app",
        user_id="user",
        id="session",
        state={},
        update_time=datetime.datetime.fromtimestamp(123.5, tz=datetime.timezone.utc),
    )
    round_tripped_session = stored_session.to_session(state={"key": "value"}, events=[round_tripped_event])
    assert round_tripped_session.id == "session"
    assert round_tripped_session.state == {"key": "value"}
    assert round_tripped_session.events[0].id == "event"
    assert round_tripped_session._storage_update_marker == stored_session.get_update_marker()
