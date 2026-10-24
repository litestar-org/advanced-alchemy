=========================================
Migrating from ADK DatabaseSessionService
=========================================

Advanced Alchemy does not take ownership of your ADK tables. Instead of using an
ADK-provided database URL and schema, define models with the ADK mixins and pass
those models to the services.

.. list-table::
    :header-rows: 1

    * - Upstream ADK
      - Advanced Alchemy
    * - ``DatabaseSessionService(db_url=...)``
      - ``ADKAsyncSessionService(db_session, model_config=adk_models)``
    * - ADK-owned tables
      - User-owned models subclassing ADK mixins
    * - ADK schema setup
      - Normal Alembic autogenerate from your metadata
    * - ``GcsArtifactService``
      - ``ADKAsyncArtifactService`` with any Advanced Alchemy storage backend

The migration usually has three steps:

1. Add mapped models for sessions, events, app state, user state, artifacts, and
   memory.
2. Generate an Alembic migration from those mapped models.
3. Replace direct ADK service construction with the Advanced Alchemy service or
   framework plugin for your application.

Artifact paths keep ADK's app/user/session/version layout, but blob storage is
delegated to the configured ``FileObject`` backend.
