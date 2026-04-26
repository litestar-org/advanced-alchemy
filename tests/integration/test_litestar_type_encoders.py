from typing import Any
from unittest.mock import patch

import pytest
from litestar.config.app import AppConfig

from advanced_alchemy.extensions.litestar.plugins.init.config import SQLAlchemyAsyncConfig
from advanced_alchemy.extensions.litestar.plugins.init.plugin import SQLAlchemyInitPlugin


@pytest.mark.anyio
async def test_aa_type_encoders_merging_logic() -> None:
    """Verify that AA built-in encoders are added and user encoders take precedence."""

    class FakeType:
        pass

    def fake_encoder(_: Any) -> str:
        return "fake"

    # Mock _get_aa_type_encoders to return a predictable set of encoders
    # This allows testing the merging logic independently of the environment
    with patch(
        "advanced_alchemy.extensions.litestar.plugins.init.plugin._get_aa_type_encoders",
        return_value={FakeType: fake_encoder},
    ):
        config = SQLAlchemyAsyncConfig(connection_string="sqlite+aiosqlite:///:memory:")
        plugin = SQLAlchemyInitPlugin(config=config)

        # 1. No user encoders: built-in should be added
        app_config = AppConfig()
        plugin.on_app_init(app_config)
        assert app_config.type_encoders is not None
        assert app_config.type_encoders[FakeType] == fake_encoder

        # 2. User encoder for DIFFERENT type: both should exist
        class OtherType:
            pass

        def other_encoder(_: Any) -> str:
            return "other"

        app_config = AppConfig(type_encoders={OtherType: other_encoder})
        plugin.on_app_init(app_config)
        assert app_config.type_encoders is not None
        assert app_config.type_encoders[FakeType] == fake_encoder
        assert app_config.type_encoders[OtherType] == other_encoder

        # 3. User encoder OVERRIDES AA encoder: user version must win
        def override_encoder(_: Any) -> str:
            return "override"

        app_config = AppConfig(type_encoders={FakeType: override_encoder})
        plugin.on_app_init(app_config)
        assert app_config.type_encoders is not None
        assert app_config.type_encoders[FakeType] == override_encoder


@pytest.mark.anyio
async def test_real_asyncpg_encoder_integration() -> None:
    """Verify integration with real asyncpg if available."""
    pgproto = pytest.importorskip("asyncpg.pgproto.pgproto")

    config = SQLAlchemyAsyncConfig(connection_string="sqlite+aiosqlite:///:memory:")
    plugin = SQLAlchemyInitPlugin(config=config)

    app_config = AppConfig()
    plugin.on_app_init(app_config)

    assert app_config.type_encoders is not None
    assert pgproto.UUID in app_config.type_encoders
    assert app_config.type_encoders[pgproto.UUID] is str


@pytest.mark.anyio
async def test_real_uuid_utils_encoder_integration() -> None:
    """Verify integration with real uuid_utils if available."""
    uuid_utils = pytest.importorskip("uuid_utils")

    config = SQLAlchemyAsyncConfig(connection_string="sqlite+aiosqlite:///:memory:")
    plugin = SQLAlchemyInitPlugin(config=config)

    app_config = AppConfig()
    plugin.on_app_init(app_config)

    assert app_config.type_encoders is not None
    assert uuid_utils.UUID in app_config.type_encoders
    assert app_config.type_encoders[uuid_utils.UUID] is str
