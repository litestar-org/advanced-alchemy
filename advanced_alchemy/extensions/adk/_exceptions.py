"""Exceptions for Google ADK integration."""


class StaleSessionError(ValueError):
    """Raised when a persisted ADK session was updated by another writer."""


__all__ = ("StaleSessionError",)
