===============
Getting Started
===============

Install the optional ADK dependencies:

.. code-block:: console

    pip install "advanced-alchemy[adk]"

Define mapped models by subclassing the ADK mixins. The models are yours, so
Alembic autogenerate can discover them normally and you can add application
columns, constraints, indexes, and naming conventions.

.. code-block:: python

    from sqlalchemy import String
    from sqlalchemy.orm import Mapped, mapped_column

    from advanced_alchemy.extensions.adk import (
        ADKAppStateModelMixin,
        ADKArtifactModelMixin,
        ADKEventModelMixin,
        ADKMemoryModelMixin,
        ADKSessionModelConfig,
        ADKSessionModelMixin,
        ADKUserStateModelMixin,
    )


    class ADKSession(ADKSessionModelMixin):
        __tablename__ = "adk_sessions"

        tenant_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


    class ADKEvent(ADKEventModelMixin):
        __tablename__ = "adk_events"


    class ADKAppState(ADKAppStateModelMixin):
        __tablename__ = "adk_app_states"


    class ADKUserState(ADKUserStateModelMixin):
        __tablename__ = "adk_user_states"


    class ADKArtifact(ADKArtifactModelMixin):
        __tablename__ = "adk_artifacts"


    class ADKMemory(ADKMemoryModelMixin):
        __tablename__ = "adk_memory_entries"


    adk_models = ADKSessionModelConfig(
        session_model=ADKSession,
        event_model=ADKEvent,
        app_state_model=ADKAppState,
        user_state_model=ADKUserState,
        artifact_model=ADKArtifact,
    )

Create services from an existing SQLAlchemy session:

.. code-block:: python

    from advanced_alchemy.extensions.adk import ADKAsyncSessionService
    from advanced_alchemy.extensions.adk.artifacts import ADKAsyncArtifactService
    from advanced_alchemy.extensions.adk.memory import ADKAsyncMemoryService

    session_service = ADKAsyncSessionService(db_session, model_config=adk_models)
    artifact_service = ADKAsyncArtifactService(db_session, artifact_model=ADKArtifact)
    memory_service = ADKAsyncMemoryService(db_session, memory_model=ADKMemory)

The extension targets Google ADK 2.x and later. It does not ship a v1 schema
router or a prebuilt migration template; use normal Alembic autogeneration from
your mapped models.
