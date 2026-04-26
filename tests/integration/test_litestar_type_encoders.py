"""Tests for the Litestar serialization plugin's type-encoder/decoder wiring.

The wiring lives on :class:`SQLAlchemySerializationPlugin` (a
``SerializationPlugin`` that also implements ``InitPluginProtocol``), not on
``SQLAlchemyInitPlugin`` — encoder/decoder registration is a serialization
concern.
"""

from typing import Any
from unittest.mock import patch

import pytest
from litestar.config.app import AppConfig
from litestar.plugins import InitPluginProtocol, SerializationPlugin

from advanced_alchemy.extensions.litestar.plugins.init.config import SQLAlchemyAsyncConfig
from advanced_alchemy.extensions.litestar.plugins.init.plugin import SQLAlchemyInitPlugin
from advanced_alchemy.extensions.litestar.plugins.serialization import SQLAlchemySerializationPlugin


def test_serialization_plugin_implements_both_protocols() -> None:
    """It is registered as both a SerializationPlugin and an InitPluginProtocol."""
    plugin = SQLAlchemySerializationPlugin()
    assert isinstance(plugin, SerializationPlugin)
    assert isinstance(plugin, InitPluginProtocol)


def test_init_plugin_does_not_touch_type_encoders() -> None:
    """``SQLAlchemyInitPlugin`` no longer manages type encoders/decoders.

    This guards against regression of the responsibility split: anything
    related to JSON serialization belongs on the serialization plugin.
    """
    config = SQLAlchemyAsyncConfig(connection_string="sqlite+aiosqlite:///:memory:")
    plugin = SQLAlchemyInitPlugin(config=config)

    app_config = AppConfig()
    plugin.on_app_init(app_config)

    # No AA encoders/decoders should have been added by the init plugin.
    assert not app_config.type_encoders
    assert not app_config.type_decoders


@pytest.mark.anyio
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


@pytest.mark.anyio
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

        # User decoders ordered FIRST (higher precedence in Litestar's resolution).
        app_config = AppConfig(type_decoders=[(user_predicate, user_decoder)])
        plugin.on_app_init(app_config)
        assert app_config.type_decoders is not None
        assert (user_predicate, user_decoder) in app_config.type_decoders
        assert (fake_predicate, fake_decoder) in app_config.type_decoders


@pytest.mark.anyio
async def test_real_asyncpg_encoder_integration() -> None:
    """Real asyncpg pgproto.UUID gets registered when asyncpg is installed."""
    pgproto = pytest.importorskip("asyncpg.pgproto.pgproto")

    plugin = SQLAlchemySerializationPlugin()
    app_config = AppConfig()
    plugin.on_app_init(app_config)

    assert app_config.type_encoders is not None
    assert pgproto.UUID in app_config.type_encoders
    assert app_config.type_encoders[pgproto.UUID] is str


@pytest.mark.anyio
async def test_real_uuid_utils_encoder_integration() -> None:
    """Real uuid_utils.UUID gets registered when uuid_utils is installed."""
    uuid_utils = pytest.importorskip("uuid_utils")

    plugin = SQLAlchemySerializationPlugin()
    app_config = AppConfig()
    plugin.on_app_init(app_config)

    assert app_config.type_encoders is not None
    assert uuid_utils.UUID in app_config.type_encoders
    assert app_config.type_encoders[uuid_utils.UUID] is str
