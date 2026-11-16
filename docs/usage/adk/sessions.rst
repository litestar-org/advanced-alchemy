========
Sessions
========

``ADKAsyncSessionService`` implements Google ADK's async session contract on top
of SQLAlchemy. It stores session, event, app-state, and user-state rows through
the user-owned model classes in ``ADKSessionModelConfig``.

.. code-block:: python

    from sqlalchemy.ext.asyncio import AsyncSession

    from advanced_alchemy.extensions.adk import (
        ADKAppStateModelMixin,
        ADKArtifactModelMixin,
        ADKAsyncSessionService,
        ADKEventModelMixin,
        ADKSessionModelConfig,
        ADKSessionModelMixin,
        ADKUserStateModelMixin,
    )


    class SessionRow(ADKSessionModelMixin):
        __tablename__ = "doc_adk_sessions"


    class EventRow(ADKEventModelMixin):
        __tablename__ = "doc_adk_events"


    class AppStateRow(ADKAppStateModelMixin):
        __tablename__ = "doc_adk_app_states"


    class UserStateRow(ADKUserStateModelMixin):
        __tablename__ = "doc_adk_user_states"


    class ArtifactRow(ADKArtifactModelMixin):
        __tablename__ = "doc_adk_session_artifacts"


    adk_models = ADKSessionModelConfig(
        session_model=SessionRow,
        event_model=EventRow,
        app_state_model=AppStateRow,
        user_state_model=UserStateRow,
        artifact_model=ArtifactRow,
    )


    async def create_support_session(db_session: AsyncSession) -> None:
        service = ADKAsyncSessionService(db_session, model_config=adk_models)
        await service.create_session(
            app_name="support-bot",
            user_id="user-123",
            session_id="external-session-id",
            state={
                "app:theme": "dark",
                "user:name": "Ada",
                "turn": 1,
            },
        )

State keys follow ADK semantics:

- ``app:`` keys are stored in the app-state model.
- ``user:`` keys are stored in the user-state model.
- unprefixed keys are stored on the session model.
- ``temp:`` keys are kept in memory for the current event and are not persisted.

The service records a storage update marker on loaded ADK sessions. If another
writer updates the same session before an append, ``StaleSessionError`` is
raised so framework integrations can return HTTP 409.

For synchronous stacks, ``ADKSyncSessionService`` provides the same persistence
behavior for direct SQLAlchemy ``Session`` usage. Google ADK's runner APIs are
async-first, so application code that talks directly to ADK should normally use
``ADKAsyncSessionService``.
