"""Unit tests for Litestar SQLAlchemySyncConfig listener registration.

Regression tests for https://github.com/litestar-org/advanced-alchemy/issues/709.
Sync variant: listeners are attached directly to the session_maker, not to a
synthetic sync_maker, so there is no sync_sessionmaker patch.
"""

from unittest.mock import MagicMock, patch

from sqlalchemy.orm import sessionmaker

from advanced_alchemy.config.common import GenericSQLAlchemyConfig
from advanced_alchemy.extensions.litestar.plugins.init.config.sync import (
    SQLAlchemySyncConfig,
)


def test_create_session_maker_registers_all_listeners() -> None:
    """Default config registers 6 listeners directly on the session_maker."""
    mock_session_maker = MagicMock(spec=sessionmaker)
    config = SQLAlchemySyncConfig(connection_string="sqlite:///")

    with (
        patch.object(
            GenericSQLAlchemyConfig,
            "create_session_maker",
            return_value=mock_session_maker,
        ),
        patch("sqlalchemy.event.listen") as mock_listen,
    ):
        result = config.create_session_maker()

    assert result is mock_session_maker
    assert mock_listen.call_count == 6
    for call in mock_listen.call_args_list:
        assert call.args[0] is mock_session_maker
    listener_events = {c.args[1] for c in mock_listen.call_args_list}
    assert {"before_flush", "after_commit", "after_rollback"} <= listener_events


def test_create_session_maker_file_object_listener_disabled() -> None:
    """With file-object listener disabled, only timestamp + cache listeners register (3)."""
    mock_session_maker = MagicMock(spec=sessionmaker)
    config = SQLAlchemySyncConfig(
        connection_string="sqlite:///",
        enable_file_object_listener=False,
    )

    with (
        patch.object(
            GenericSQLAlchemyConfig,
            "create_session_maker",
            return_value=mock_session_maker,
        ),
        patch("sqlalchemy.event.listen") as mock_listen,
    ):
        config.create_session_maker()

    assert mock_listen.call_count == 3


def test_create_session_maker_timestamp_listener_disabled() -> None:
    """With timestamp listener disabled, only file-object + cache listeners register (5)."""
    mock_session_maker = MagicMock(spec=sessionmaker)
    config = SQLAlchemySyncConfig(
        connection_string="sqlite:///",
        enable_touch_updated_timestamp_listener=False,
    )

    with (
        patch.object(
            GenericSQLAlchemyConfig,
            "create_session_maker",
            return_value=mock_session_maker,
        ),
        patch("sqlalchemy.event.listen") as mock_listen,
    ):
        config.create_session_maker()

    assert mock_listen.call_count == 5
