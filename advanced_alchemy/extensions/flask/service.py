"""Flask-specific service classes."""

from __future__ import annotations

from typing import Any

from flask import Response, current_app

from advanced_alchemy.extensions.flask.config import serializer


class FlaskServiceMixin:
    """Mixin to add Flask-specific functionality to services.

    Example:
        .. code-block:: python

            from advanced_alchemy.service import (
                SQLAlchemyAsyncRepositoryService,
            )
            from advanced_alchemy.extensions.flask import (
                FlaskServiceMixin,
            )


            class UserService(
                FlaskServiceMixin,
                SQLAlchemyAsyncRepositoryService[User],
            ):
                class Repo(repository.SQLAlchemySyncRepository[User]):
                    model_type = User

                repository_type = Repo

                def get_user_response(self, user_id: int) -> Response:
                    user = self.get(user_id)
                    return self.jsonify(user.dict())
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
