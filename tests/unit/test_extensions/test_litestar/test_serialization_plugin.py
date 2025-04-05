from types import ModuleType
from typing import Callable

from litestar import get
from litestar.status_codes import HTTP_200_OK
from litestar.testing import RequestFactory, create_test_client
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from advanced_alchemy.base import UUIDAuditBase
from advanced_alchemy.extensions.litestar import SQLAlchemySerializationPlugin
from advanced_alchemy.service.pagination import OffsetPagination


async def test_serialization_plugin(
    create_module: Callable[[str], ModuleType],
    request_factory: RequestFactory,
) -> None:
    module = create_module(
        """
from __future__ import annotations

from typing import Dict, List, Set, Tuple, Type, List

from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from litestar import Litestar, get, post
from advanced_alchemy.extensions.litestar import SQLAlchemySerializationPlugin

class Base(DeclarativeBase):
    id: Mapped[int] = mapped_column(primary_key=True)

class A(Base):
    __tablename__ = "a"
    a: Mapped[str]

@post("/a")
def post_handler(data: A) -> A:
    return data

@get("/a")
def get_handler() -> List[A]:
    return [A(id=1, a="test"), A(id=2, a="test2")]

@get("/a/1")
def get_a() -> A:
    return A(id=1, a="test")
""",
    )
    with create_test_client(
        route_handlers=[module.post_handler, module.get_handler, module.get_a],
        plugins=[SQLAlchemySerializationPlugin()],
    ) as client:
        response = client.post("/a", json={"id": 1, "a": "test"})
        assert response.status_code == 201
        assert response.json() == {"id": 1, "a": "test"}
        response = client.get("/a")
        assert response.json() == [{"id": 1, "a": "test"}, {"id": 2, "a": "test2"}]
        response = client.get("/a/1")
        assert response.json() == {"id": 1, "a": "test"}


class User(UUIDAuditBase):
    first_name: Mapped[str] = mapped_column(String(200))


def test_pagination_serialization() -> None:
    users = [User(first_name="ASD"), User(first_name="qwe")]

    @get("/paginated")
    async def paginated_handler() -> OffsetPagination[User]:
        return OffsetPagination[User](items=users, limit=2, offset=0, total=2)

    with create_test_client(paginated_handler, plugins=[SQLAlchemySerializationPlugin()]) as client:
        response = client.get("/paginated")
        assert response.status_code == HTTP_200_OK
