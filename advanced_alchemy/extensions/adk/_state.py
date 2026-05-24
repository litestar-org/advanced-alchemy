"""State routing helpers for Google ADK session persistence."""

from typing import Any

from google.adk.sessions.state import State

_APP_BUCKET = "app"
_USER_BUCKET = "user"
_SESSION_BUCKET = "session"


def extract_state_delta(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Split ADK state keys into app, user, and session persistence buckets."""
    deltas: dict[str, dict[str, Any]] = {_APP_BUCKET: {}, _USER_BUCKET: {}, _SESSION_BUCKET: {}}
    for key, value in state.items():
        if key.startswith(State.APP_PREFIX):
            deltas[_APP_BUCKET][key.removeprefix(State.APP_PREFIX)] = value
        elif key.startswith(State.USER_PREFIX):
            deltas[_USER_BUCKET][key.removeprefix(State.USER_PREFIX)] = value
        elif not key.startswith(State.TEMP_PREFIX):
            deltas[_SESSION_BUCKET][key] = value
    return deltas


def merge_scoped_state(
    session_state: dict[str, Any],
    app_state: dict[str, Any],
    user_state: dict[str, Any],
) -> dict[str, Any]:
    """Merge stored ADK state buckets back into ADK's prefixed session state."""
    return {
        **{f"{State.APP_PREFIX}{key}": value for key, value in app_state.items()},
        **{f"{State.USER_PREFIX}{key}": value for key, value in user_state.items()},
        **session_state,
    }


__all__ = ("extract_state_delta", "merge_scoped_state")
