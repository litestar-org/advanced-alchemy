"""Flask-specific service classes."""

from __future__ import annotations

from typing import Any

from flask import Response, current_app

from advanced_alchemy.extensions.flask.config import serializer


class FlaskServiceMixin:
    """Mixin to add Flask-specific functionality to services."""

    def jsonify(
        self,
        data: Any,
        *args: Any,
        status_code: int = 200,
        **kwargs: Any,
    ) -> Response:
        """Convert data to a Flask JSON response.

        Args:
            data: Data to serialize
            *args: Additional arguments
            status_code: HTTP status code
            **kwargs: Additional arguments

        Returns:
            Flask JSON response
        """

        return current_app.response_class(
            serializer(data),
            status=status_code,
            mimetype="application/json",
        )
