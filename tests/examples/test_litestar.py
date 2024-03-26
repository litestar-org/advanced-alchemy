from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Iterator

import pytest
from litestar.testing import AsyncTestClient, TestClient

from advanced_alchemy.config import AsyncSessionConfig
from advanced_alchemy.extensions.litestar.plugins import SQLAlchemyAsyncConfig

if TYPE_CHECKING:
    from litestar import Litestar


@pytest.fixture()
def app() -> Litestar:
    # Import of example must be done within fixture so that these models don't
    # effect other tests.
    from examples.litestar import init_app

    sqlalchemy_config = SQLAlchemyAsyncConfig(
        create_all=True,
        # Use the same session instance for all requests so the database doesn't disappear
        engine_instance=SQLAlchemyAsyncConfig.create_engine_callable("sqlite+aiosqlite:///:memory:"),
        session_config=AsyncSessionConfig(expire_on_commit=False),
    )

    app = init_app(sqlalchemy_config=sqlalchemy_config)
    app.debug = True
    return app


@pytest.fixture()
def test_client(app: Litestar) -> Iterator[TestClient[Litestar]]:
    with TestClient(app=app) as client:
        yield client


@pytest.fixture()
async def test_asyncclient(app: Litestar) -> AsyncIterator[AsyncTestClient[Litestar]]:
    async with AsyncTestClient(app=app) as client:
        yield client


def test_create_list(test_client: TestClient[Litestar]) -> None:
    # see _patch_bases in conftest.py
    from examples.litestar import Author

    author = Author(name="foo")

    response = test_client.post(
        "/authors",
        json=author.to_dict(),
    )
    assert response.status_code == 201, response.text
    assert response.json()["name"] == author.name

    response = test_client.get("/authors")
    assert response.status_code == 200, response.text
    assert response.json()["items"][0]["name"] == author.name


def test_create_get_update_delete(test_client: TestClient[Litestar]) -> None:
    # see _patch_bases in conftest.py
    from examples.litestar import Author

    author = Author(name="foo")

    response = test_client.post(
        "/authors",
        json=author.to_dict(),
    )
    assert response.status_code == 201, response.text
    assert response.json()["name"] == author.name
    author_id = response.json()["id"]

    response = test_client.get(f"/authors/{author_id}")
    assert response.status_code == 200, response.text
    assert response.json()["name"] == author.name
    assert response.json()["id"] == author_id

    response = test_client.patch(
        f"/authors/{author_id}",
        json={"name": "bar"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["name"] == "bar"
    assert response.json()["id"] == author_id

    response = test_client.delete(f"/authors/{author_id}")
    assert response.status_code == 204, response.text

    response = test_client.get(f"/authors/{author_id}")
    assert response.status_code == 404, response.text
