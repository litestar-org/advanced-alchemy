"""Repository classes for Google ADK persistence models."""

from advanced_alchemy.extensions.adk.v1 import ADKAppState, ADKEvent, ADKSession, ADKUserState
from advanced_alchemy.repository import SQLAlchemyAsyncRepository


class ADKSessionRepository(SQLAlchemyAsyncRepository[ADKSession]):
    """Repository for ADK sessions."""

    model_type = ADKSession


class ADKEventRepository(SQLAlchemyAsyncRepository[ADKEvent]):
    """Repository for ADK events."""

    model_type = ADKEvent


class ADKAppStateRepository(SQLAlchemyAsyncRepository[ADKAppState]):
    """Repository for ADK app-scoped state."""

    model_type = ADKAppState


class ADKUserStateRepository(SQLAlchemyAsyncRepository[ADKUserState]):
    """Repository for ADK user-scoped state."""

    model_type = ADKUserState


__all__ = ("ADKAppStateRepository", "ADKEventRepository", "ADKSessionRepository", "ADKUserStateRepository")
