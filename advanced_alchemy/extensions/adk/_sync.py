"""Sync Google ADK session service helpers for synchronous SQLAlchemy stacks."""

import datetime
from typing import Any, Optional

from google.adk.events.event import Event
from google.adk.platform import uuid as platform_uuid
from google.adk.sessions.base_session_service import GetSessionConfig, ListSessionsResponse
from google.adk.sessions.session import Session as ADKSessionModel
from google.adk.sessions.state import State
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from advanced_alchemy.extensions.adk._async import STALE_SESSION_ERROR_MESSAGE
from advanced_alchemy.extensions.adk._exceptions import StaleSessionError
from advanced_alchemy.extensions.adk._state import extract_state_delta, merge_scoped_state
from advanced_alchemy.extensions.adk.models import (
    ADKAppStateModelMixin,
    ADKEventModelMixin,
    ADKSessionModelConfig,
    ADKSessionModelMixin,
    ADKUserStateModelMixin,
)


class ADKSyncSessionService:
    """Synchronous SQLAlchemy helper with the same persistence behavior as the async ADK service."""

    def __init__(self, session: Session, *, model_config: ADKSessionModelConfig) -> None:
        self.session = session
        self.model_config = model_config
        self.session_model = model_config.session_model
        self.event_model = model_config.event_model
        self.app_state_model = model_config.app_state_model
        self.user_state_model = model_config.user_state_model
        self.artifact_model = model_config.artifact_model

    @property
    def _is_sqlite(self) -> bool:
        bind = self.session.get_bind()
        return bool(bind and bind.dialect.name == "sqlite")

    def create_session(
        self,
        *,
        app_name: str,
        user_id: str,
        state: Optional[dict[str, Any]] = None,
        session_id: Optional[str] = None,
    ) -> ADKSessionModel:
        """Create a new ADK session."""
        session_id = session_id or platform_uuid.new_uuid()
        state_deltas = extract_state_delta(state or {})
        app_state = self._get_or_create_app_state(app_name)
        user_state = self._get_or_create_user_state(app_name, user_id)
        app_state.state = {**(app_state.state or {}), **state_deltas["app"]}
        user_state.state = {**(user_state.state or {}), **state_deltas["user"]}

        storage_session = self.session_model(
            app_name=app_name,
            user_id=user_id,
            session_id=session_id,
            state=state_deltas["session"],
        )
        self.session.add(storage_session)
        self.session.flush()
        self.session.refresh(storage_session)
        return storage_session.to_session(
            state=merge_scoped_state(
                storage_session.state,
                app_state.state or {},
                user_state.state or {},
            ),
            events=[],
            is_sqlite=self._is_sqlite,
        )

    def get_session(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: str,
        config: Optional[GetSessionConfig] = None,
    ) -> Optional[ADKSessionModel]:
        """Get a session by app, user, and session ID."""
        storage_session = self._get_storage_session(app_name, user_id, session_id)
        if storage_session is None:
            existing = self.session.scalar(
                select(self.session_model).where(self.session_model.session_id == session_id)
            )
            if existing is not None:
                msg = f"Session {session_id!r} does not belong to app/user {app_name!r}/{user_id!r}"
                raise PermissionError(msg)
            return None

        app_state = self._get_or_create_app_state(app_name)
        user_state = self._get_or_create_user_state(app_name, user_id)
        events = self._get_events(storage_session, config=config)
        return storage_session.to_session(
            state=merge_scoped_state(
                storage_session.state,
                app_state.state or {},
                user_state.state or {},
            ),
            events=[event.to_event() for event in events],
            is_sqlite=self._is_sqlite,
        )

    def list_sessions(self, *, app_name: str, user_id: Optional[str] = None) -> ListSessionsResponse:
        """List sessions for an app, optionally filtered by user."""
        statement = (
            select(self.session_model)
            .where(self.session_model.app_name == app_name)
            .order_by(self.session_model.session_id)
        )
        if user_id is not None:
            statement = statement.where(self.session_model.user_id == user_id)
        sessions = [
            storage_session.to_session(state=storage_session.state, events=[], is_sqlite=self._is_sqlite)
            for storage_session in self.session.scalars(statement).all()
        ]
        return ListSessionsResponse(sessions=sessions)

    def delete_session(self, *, app_name: str, user_id: str, session_id: str) -> None:
        """Delete a session and its owned events and artifacts."""
        storage_session = self._get_storage_session(app_name, user_id, session_id)
        if storage_session is not None:
            self._delete_session_events(app_name, user_id, session_id)
            self._delete_session_artifacts(app_name, user_id, session_id)
            self.session.delete(storage_session)
            self.session.flush()

    def append_event(self, session: ADKSessionModel, event: Event) -> Event:
        """Append and persist an event with optimistic stale-session detection."""
        if event.partial:
            return event

        self._apply_temp_state_delta(session, event)
        event = self._trim_temp_delta_state_for_storage(event)
        storage_session = self._get_storage_session(session.app_name, session.user_id, session.id)
        if storage_session is None:
            msg = f"Session {session.id} not found."
            raise ValueError(msg)

        storage_marker = storage_session.get_update_marker()
        session_marker = getattr(session, "_storage_update_marker", None)
        if session_marker is not None and session_marker != storage_marker:
            raise StaleSessionError(STALE_SESSION_ERROR_MESSAGE)
        setattr(session, "_storage_update_marker", storage_marker)

        state_delta = event.actions.state_delta or {}
        state_deltas = extract_state_delta(state_delta)
        app_state = self._get_or_create_app_state(session.app_name)
        user_state = self._get_or_create_user_state(session.app_name, session.user_id)
        if state_deltas["app"]:
            app_state.state = {**(app_state.state or {}), **state_deltas["app"]}
        if state_deltas["user"]:
            user_state.state = {**(user_state.state or {}), **state_deltas["user"]}
        if state_deltas["session"]:
            storage_session.state = {**(storage_session.state or {}), **state_deltas["session"]}

        storage_session.update_time = datetime.datetime.fromtimestamp(event.timestamp, tz=datetime.timezone.utc)
        self.session.add(self.event_model.from_event(session, event))
        self.session.flush()

        session.last_update_time = storage_session.get_update_timestamp(is_sqlite=self._is_sqlite)
        setattr(session, "_storage_update_marker", storage_session.get_update_marker())
        self._update_session_state(session, event)
        session.events.append(event)
        return event

    def _get_storage_session(self, app_name: str, user_id: str, session_id: str) -> Optional[ADKSessionModelMixin]:
        statement = (
            select(self.session_model)
            .where(self.session_model.app_name == app_name)
            .where(self.session_model.user_id == user_id)
            .where(self.session_model.session_id == session_id)
        )
        return self.session.scalar(statement)

    def _delete_session_events(self, app_name: str, user_id: str, session_id: str) -> None:
        events = self.session.scalars(
            select(self.event_model)
            .where(self.event_model.app_name == app_name)
            .where(self.event_model.user_id == user_id)
            .where(self.event_model.session_id == session_id),
        )
        for event in events.all():
            self.session.delete(event)

    def _delete_session_artifacts(self, app_name: str, user_id: str, session_id: str) -> None:
        if self.artifact_model is None:
            return
        artifacts = self.session.scalars(
            select(self.artifact_model)
            .where(self.artifact_model.app_name == app_name)
            .where(self.artifact_model.user_id == user_id)
            .where(self.artifact_model.session_id == session_id),
        )
        for artifact in artifacts.all():
            self.session.delete(artifact)

    def _get_or_create_app_state(self, app_name: str) -> ADKAppStateModelMixin:
        app_state = self.session.scalar(select(self.app_state_model).where(self.app_state_model.app_name == app_name))
        if app_state is None:
            app_state = self.app_state_model(app_name=app_name, state={})
            self.session.add(app_state)
            self.session.flush()
        return app_state

    def _get_or_create_user_state(self, app_name: str, user_id: str) -> ADKUserStateModelMixin:
        user_state = self.session.scalar(
            select(self.user_state_model)
            .where(self.user_state_model.app_name == app_name)
            .where(self.user_state_model.user_id == user_id),
        )
        if user_state is None:
            user_state = self.user_state_model(app_name=app_name, user_id=user_id, state={})
            self.session.add(user_state)
            self.session.flush()
        return user_state

    def _get_events(
        self, storage_session: ADKSessionModelMixin, config: Optional[GetSessionConfig]
    ) -> list[ADKEventModelMixin]:
        statement = self._event_statement(storage_session)
        if config is not None and config.after_timestamp is not None:
            after_timestamp = datetime.datetime.fromtimestamp(config.after_timestamp, tz=datetime.timezone.utc)
            statement = statement.where(self.event_model.timestamp >= after_timestamp)
        statement = statement.order_by(self.event_model.timestamp)
        if config is not None and config.num_recent_events == 0:
            return []
        if config is not None and config.num_recent_events is not None:
            statement = statement.limit(config.num_recent_events)
        return list(self.session.scalars(statement).all())

    def _event_statement(self, storage_session: ADKSessionModelMixin) -> Select[tuple[ADKEventModelMixin]]:
        return (
            select(self.event_model)
            .where(self.event_model.app_name == storage_session.app_name)
            .where(self.event_model.user_id == storage_session.user_id)
            .where(self.event_model.session_id == storage_session.session_id)
        )

    @staticmethod
    def _apply_temp_state_delta(session: ADKSessionModel, event: Event) -> None:
        if not event.actions.state_delta:
            return
        for key, value in event.actions.state_delta.items():
            if key.startswith(State.TEMP_PREFIX):
                session.state[key] = value

    @staticmethod
    def _trim_temp_delta_state_for_storage(event: Event) -> Event:
        if not event.actions.state_delta:
            return event
        event.actions.state_delta = {
            key: value for key, value in event.actions.state_delta.items() if not key.startswith(State.TEMP_PREFIX)
        }
        return event

    @staticmethod
    def _update_session_state(session: ADKSessionModel, event: Event) -> None:
        if not event.actions.state_delta:
            return
        for key, value in event.actions.state_delta.items():
            session.state.update({key: value})


__all__ = ("ADKSyncSessionService",)
