from __future__ import annotations

from typing import TYPE_CHECKING, Any

from litestar.connection import Request
from litestar.connection.base import AuthT, StateT, UserT
from litestar.exceptions import (
    HTTPException,
    InternalServerException,
)
from litestar.exceptions.responses import (
    create_debug_response,  # pyright: ignore[reportUnknownVariableType]
    create_exception_response,  # pyright: ignore[reportUnknownVariableType]
)
from litestar.response import Response
from litestar.status_codes import (
    HTTP_404_NOT_FOUND,
    HTTP_409_CONFLICT,
)

from advanced_alchemy.exceptions import (
    DuplicateKeyError,
    ForeignKeyError,
    IntegrityError,
    NotFoundError,
    RepositoryError,
)

if TYPE_CHECKING:
    from litestar.connection import Request
    from litestar.connection.base import AuthT, StateT, UserT
    from litestar.response import Response


class _HTTPConflictException(HTTPException):
    """Request conflict with the current state of the target resource."""

    status_code: int = HTTP_409_CONFLICT


class _HTTPNotFoundException(HTTPException):
    """Request not found with the current state of the target resource."""

    status_code: int = HTTP_404_NOT_FOUND


def exception_to_http_response(request: Request[UserT, AuthT, StateT], exc: RepositoryError) -> Response[Any]:
    """Handler for all exceptions subclassed from HTTPException."""
    if isinstance(exc, NotFoundError):
        http_exc: type[HTTPException] = _HTTPNotFoundException
    elif isinstance(exc, (DuplicateKeyError, IntegrityError, ForeignKeyError)):
        http_exc = _HTTPConflictException
    else:
        http_exc = InternalServerException
    if request.app.debug:
        return create_debug_response(request, exc)  # pyright: ignore[reportUnknownVariableType]
    return create_exception_response(request, http_exc(detail=str(exc.detail)))  # pyright: ignore[reportUnknownVariableType]
