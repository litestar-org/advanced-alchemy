"""Type encoders for Google ADK models."""

from collections.abc import Callable
from typing import Any


def _dump_model(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value


def get_adk_type_encoders() -> dict[type[Any], Callable[[Any], Any]]:
    """Return Litestar-compatible type encoders for ADK and GenAI models."""
    try:
        from google.adk.events.event import Event
        from google.adk.sessions.session import Session
        from google.genai.types import Content, Part
    except ImportError:
        return {}
    return {
        Content: _dump_model,
        Event: _dump_model,
        Part: _dump_model,
        Session: _dump_model,
    }


__all__ = ("get_adk_type_encoders",)
