"""Common configuration for Flask SQLAlchemy integration."""

from __future__ import annotations

from typing import Final

SESSION_SCOPE_KEY: Final = "aa_session"
"""Key under which to store the SQLAlchemy session in the Flask application context."""

SESSION_TERMINUS_EVENTS: Final = {"response_finished", "request_finished"}
"""Events that signal the end of a request/response cycle."""
