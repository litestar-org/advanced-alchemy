"""Flask-specific service classes.

This module provides Flask-specific service mixins and utilities for integrating
with the Advanced Alchemy service layer.
"""

from __future__ import annotations

from typing import Any

from flask import Response, current_app

from advanced_alchemy.extensions.flask.config import serializer


class FlaskServiceMixin:
    """A mixin class that adds Flask-specific functionality to services.

    This mixin provides methods and utilities for handling Flask-specific operations
    when working with service classes.

    :param serializer: The serializer instance to use for data transformation
    :type serializer: :class:`advanced_alchemy.extensions.flask.config.Serializer`

    Example:
    -------

    .. code-block:: python

        from advanced_alchemy.service import (
            SQLAlchemyAsyncRepositoryService,
        )
        from advanced_alchemy.extensions.flask import (
            FlaskServiceMixin,
        )


        class MyService(
            FlaskServiceMixin, SQLAlchemyAsyncRepositoryService
        ):
            pass
    """

    def jsonify(
        self,
        data: Any,
        *args: Any,
        status_code: int = 200,
        **kwargs: Any,
    ) -> Response:
        """Convert data to a Flask JSON response.

        Args:
            data: Data to serialize to JSON.
            *args: Additional positional arguments passed to Flask's response class.
            status_code: HTTP status code for the response. Defaults to 200.
            **kwargs: Additional keyword arguments passed to Flask's response class.

        Returns:
            :class:`flask.Response`: A Flask response with JSON content type.
        """
        return current_app.response_class(
            serializer(data),
            status=status_code,
            mimetype="application/json",
        )
