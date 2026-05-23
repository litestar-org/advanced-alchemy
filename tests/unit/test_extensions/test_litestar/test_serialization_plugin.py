from types import ModuleType
from typing import Any, Callable
from unittest.mock import patch

import pytest
from litestar import get
from litestar.config.app import AppConfig
from litestar.plugins import InitPluginProtocol, SerializationPlugin
from litestar.status_codes import HTTP_200_OK
from litestar.testing import RequestFactory, create_test_client
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from advanced_alchemy.base import UUIDAuditBase
from advanced_alchemy.extensions.litestar import (
    SQLAlchemyAsyncConfig,
    SQLAlchemyInitPlugin,
    SQLAlchemySerializationPlugin,
)
from advanced_alchemy.service.pagination import OffsetPagination


def test_serialization_plugin_implements_both_protocols() -> None:
    """It is registered as both a SerializationPlugin and an InitPluginProtocol."""
    plugin = SQLAlchemySerializationPlugin()
    assert isinstance(plugin, SerializationPlugin)
    assert isinstance(plugin, InitPluginProtocol)


def test_init_plugin_preserves_legacy_uuid_type_encoder_registration() -> None:
    """``SQLAlchemyInitPlugin`` keeps the direct-registration UUID encoders."""
    config = SQLAlchemyAsyncConfig(connection_string="sqlite+aiosqlite:///:memory:")
    plugin = SQLAlchemyInitPlugin(config=config)

    class FakeType:
        pass

    class OtherType:
        pass

    def fake_encoder(_: Any) -> str:
        return "fake"

    def other_encoder(_: Any) -> str:
        return "other"

    def override_encoder(_: Any) -> str:
        return "override"

    def fake_predicate(_: Any) -> bool:
        return False

    def fake_decoder(_t: type, _v: Any) -> Any:
        return None

    def user_predicate(_: Any) -> bool:
        return False

    def user_decoder(_t: type, _v: Any) -> Any:
        return None

    with (
        patch(
            "advanced_alchemy.extensions.litestar.plugins.serialization._get_aa_litestar_type_encoders",
            return_value={FakeType: fake_encoder, OtherType: other_encoder},
        ),
        patch(
            "advanced_alchemy.extensions.litestar.plugins.serialization._get_aa_type_decoders",
            return_value=[(fake_predicate, fake_decoder)],
        ),
    ):
        app_config = AppConfig(
            type_encoders={FakeType: override_encoder},
            type_decoders=[(user_predicate, user_decoder)],
        )
        plugin.on_app_init(app_config)

    assert app_config.type_encoders is not None
    assert app_config.type_encoders[FakeType] == override_encoder
    assert app_config.type_encoders[OtherType] == other_encoder
    assert app_config.type_decoders == [
        (user_predicate, user_decoder),
        (fake_predicate, fake_decoder),
    ]


async def test_aa_type_encoders_merging_logic() -> None:
    """Built-in AA encoders are added; user encoders override on collision."""

    class FakeType:
        pass

    def fake_encoder(_: Any) -> str:
        return "fake"

    with patch(
        "advanced_alchemy.extensions.litestar.plugins.serialization._get_aa_type_encoders",
        return_value={FakeType: fake_encoder},
    ):
        plugin = SQLAlchemySerializationPlugin()

        # 1. No user encoders: built-in is added.
        app_config = AppConfig()
        plugin.on_app_init(app_config)
        assert app_config.type_encoders is not None
        assert app_config.type_encoders[FakeType] == fake_encoder

        # 2. User encoder for a different type: both coexist.
        class OtherType:
            pass

        def other_encoder(_: Any) -> str:
            return "other"

        app_config = AppConfig(type_encoders={OtherType: other_encoder})
        plugin.on_app_init(app_config)
        assert app_config.type_encoders is not None
        assert app_config.type_encoders[FakeType] == fake_encoder
        assert app_config.type_encoders[OtherType] == other_encoder

        # 3. User encoder OVERRIDES the AA built-in.
        def override_encoder(_: Any) -> str:
            return "override"

        app_config = AppConfig(type_encoders={FakeType: override_encoder})
        plugin.on_app_init(app_config)
        assert app_config.type_encoders is not None
        assert app_config.type_encoders[FakeType] == override_encoder


async def test_aa_type_decoders_merging_logic() -> None:
    """Built-in AA decoders are added; user decoders take precedence."""

    def fake_predicate(_: Any) -> bool:
        return False

    def fake_decoder(_t: type, _v: Any) -> Any:
        return None

    def user_predicate(_: Any) -> bool:
        return False

    def user_decoder(_t: type, _v: Any) -> Any:
        return None

    with patch(
        "advanced_alchemy.extensions.litestar.plugins.serialization._get_aa_type_decoders",
        return_value=[(fake_predicate, fake_decoder)],
    ):
        plugin = SQLAlchemySerializationPlugin()

        # User decoders must be ordered FIRST because Litestar uses the first
        # matching predicate when resolving decoders.
        app_config = AppConfig(type_decoders=[(user_predicate, user_decoder)])
        plugin.on_app_init(app_config)
        assert app_config.type_decoders is not None
        assert app_config.type_decoders == [
            (user_predicate, user_decoder),
            (fake_predicate, fake_decoder),
        ]


def test_aa_type_decoder_registration_is_idempotent() -> None:
    """``SQLAlchemyInitPlugin`` and ``SQLAlchemySerializationPlugin`` can both run."""
    config = SQLAlchemyAsyncConfig(connection_string="sqlite+aiosqlite:///:memory:")

    def fake_predicate(_: Any) -> bool:
        return False

    def fake_decoder(_t: type, _v: Any) -> Any:
        return None

    decoder = (fake_predicate, fake_decoder)

    with patch(
        "advanced_alchemy.extensions.litestar.plugins.serialization._get_aa_type_decoders",
        return_value=[decoder],
    ):
        app_config = AppConfig()
        SQLAlchemyInitPlugin(config=config).on_app_init(app_config)
        SQLAlchemySerializationPlugin().on_app_init(app_config)

    assert app_config.type_decoders == [decoder]


async def test_real_asyncpg_encoder_integration() -> None:
    """Real asyncpg pgproto.UUID gets registered when asyncpg is installed."""
    pgproto = pytest.importorskip("asyncpg.pgproto.pgproto")

    plugin = SQLAlchemySerializationPlugin()
    app_config = AppConfig()
    plugin.on_app_init(app_config)

    assert app_config.type_encoders is not None
    assert pgproto.UUID in app_config.type_encoders
    assert app_config.type_encoders[pgproto.UUID] is str


async def test_real_uuid_utils_encoder_integration() -> None:
    """Real uuid_utils.UUID gets registered when uuid_utils is installed."""
    uuid_utils = pytest.importorskip("uuid_utils")

    plugin = SQLAlchemySerializationPlugin()
    app_config = AppConfig()
    plugin.on_app_init(app_config)

    assert app_config.type_encoders is not None
    assert uuid_utils.UUID in app_config.type_encoders
    assert app_config.type_encoders[uuid_utils.UUID] is str


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
