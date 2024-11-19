from litestar import MediaType, Request, Response

from advanced_alchemy.exceptions import NotFoundError


def not_found_error_handler(_request: Request, _exc: NotFoundError) -> Response:
    return Response(
        media_type=MediaType.JSON,
        content={"detail": "Not Found", "status_code": 404},
        status_code=404,
    )
