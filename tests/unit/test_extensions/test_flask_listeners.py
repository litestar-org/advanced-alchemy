"""Unit tests for Flask SQLAlchemy config listener registration.

Regression tests for https://github.com/litestar-org/advanced-alchemy/issues/709.
Both Flask async and sync configs override ``create_session_maker`` without
delegating to ``super()``, silently dropping the listener registration
performed by the base class. These tests lock the contract per subclass.

Shared assertions live in ``_listener_contract.py``.
"""

from advanced_alchemy.extensions.flask.config import (
    SQLAlchemyAsyncConfig,
    SQLAlchemySyncConfig,
)
from tests.unit.test_extensions._listener_contract import (
    assert_async_file_object_listener_disabled,
    assert_async_registers_all_listeners,
    assert_async_timestamp_listener_disabled,
    assert_sync_file_object_listener_disabled,
    assert_sync_registers_all_listeners,
    assert_sync_timestamp_listener_disabled,
)


def test_async_create_session_maker_registers_all_listeners() -> None:
    assert_async_registers_all_listeners(SQLAlchemyAsyncConfig)


def test_async_create_session_maker_file_object_listener_disabled() -> None:
    assert_async_file_object_listener_disabled(SQLAlchemyAsyncConfig)


def test_async_create_session_maker_timestamp_listener_disabled() -> None:
    assert_async_timestamp_listener_disabled(SQLAlchemyAsyncConfig)


def test_sync_create_session_maker_registers_all_listeners() -> None:
    assert_sync_registers_all_listeners(SQLAlchemySyncConfig)


def test_sync_create_session_maker_file_object_listener_disabled() -> None:
    assert_sync_file_object_listener_disabled(SQLAlchemySyncConfig)


def test_sync_create_session_maker_timestamp_listener_disabled() -> None:
    assert_sync_timestamp_listener_disabled(SQLAlchemySyncConfig)
