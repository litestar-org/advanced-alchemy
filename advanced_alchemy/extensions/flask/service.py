"""Flask-specific service classes."""

from __future__ import annotations

from typing import Any

from flask import Response, current_app

from advanced_alchemy._serialization import encode_json
from advanced_alchemy.service import ModelT
from advanced_alchemy.service import SQLAlchemyAsyncRepositoryService as _SQLAlchemyAsyncRepositoryService
from advanced_alchemy.service import SQLAlchemySyncRepositoryService as _SQLAlchemySyncRepositoryService


class SQLAlchemySyncRepositoryService(_SQLAlchemySyncRepositoryService[ModelT]):
    """Flask-specific synchronous service."""

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
            encode_json(data),
            status=status_code,
            mimetype="application/json",
        )


class SQLAlchemyAsyncRepositoryService(_SQLAlchemyAsyncRepositoryService[ModelT]):
    """Flask-specific asynchronous service."""

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
            encode_json(data),
            status=status_code,
            mimetype="application/json",
        )
