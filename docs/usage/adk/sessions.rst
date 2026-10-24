========
Sessions
========

``ADKAsyncSessionService`` implements Google ADK's async session contract on top
of SQLAlchemy. It stores session, event, app-state, and user-state rows through
the user-owned model classes in ``ADKSessionModelConfig``.

.. code-block:: python

    service = ADKAsyncSessionService(db_session, model_config=adk_models)

    session = await service.create_session(
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
