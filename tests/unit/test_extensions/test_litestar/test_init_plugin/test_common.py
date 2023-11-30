from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
from litestar.datastructures import State
from sqlalchemy import create_engine

from advanced_alchemy.exceptions import ImproperConfigurationError
from advanced_alchemy.extensions.litestar._utils import _SCOPE_NAMESPACE
from advanced_alchemy.extensions.litestar.plugins import SQLAlchemyAsyncConfig, SQLAlchemySyncConfig
from advanced_alchemy.extensions.litestar.plugins.init.config.common import SESSION_SCOPE_KEY

if TYPE_CHECKING:
    from typing import Any

    from litestar.types import Scope
    from pytest import MonkeyPatch


@pytest.fixture(name="config_cls", params=[SQLAlchemySyncConfig, SQLAlchemyAsyncConfig])
def _config_cls(request: Any) -> type[SQLAlchemySyncConfig | SQLAlchemyAsyncConfig]:
    """Return SQLAlchemy config class."""
    return request.param  # type:ignore[no-any-return]


def test_raise_improperly_configured_exception(config_cls: type[SQLAlchemySyncConfig]) -> None:
    """Test raise ImproperlyConfiguredException if both engine and connection string are provided."""
    with pytest.raises(ImproperConfigurationError):
        config_cls(connection_string="sqlite://", engine_instance=create_engine("sqlite://"))


def test_engine_config_dict_with_no_provided_config(
    config_cls: type[SQLAlchemySyncConfig],
) -> None:
    """Test engine_config_dict with no provided config."""
    config = config_cls()
    assert config.engine_config_dict.keys() == {"json_deserializer", "json_serializer"}


def test_session_config_dict_with_no_provided_config(
    config_cls: type[SQLAlchemySyncConfig],
) -> None:
    """Test session_config_dict with no provided config."""
    config = config_cls()
    assert config.session_config_dict == {}


def test_config_create_engine_if_engine_instance_provided(
    config_cls: type[SQLAlchemySyncConfig],
) -> None:
    """Test create_engine if engine instance provided."""
    engine = create_engine("sqlite://")
    config = config_cls(engine_instance=engine)
    assert config.get_engine() == engine


def test_create_engine_if_no_engine_instance_or_connection_string_provided(
    config_cls: type[SQLAlchemySyncConfig],
) -> None:
    """Test create_engine if no engine instance or connection string provided."""
    config = config_cls()
    with pytest.raises(ImproperConfigurationError):
        config.get_engine()


def test_call_create_engine_callable_type_error_handling(
    config_cls: type[SQLAlchemySyncConfig],
    monkeypatch: MonkeyPatch,
) -> None:
    """If the dialect doesn't support JSON types, we get a ValueError.
    This should be handled by removing the JSON serializer/deserializer kwargs.
    """
    call_count = 0

    def side_effect(*args: Any, **kwargs: Any) -> None:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise TypeError()

    config = config_cls(connection_string="sqlite://")
    create_engine_callable_mock = MagicMock(side_effect=side_effect)
    monkeypatch.setattr(config, "create_engine_callable", create_engine_callable_mock)

    config.get_engine()

    assert create_engine_callable_mock.call_count == 2
    first_call, second_call = create_engine_callable_mock.mock_calls
    assert first_call.kwargs.keys() == {"json_deserializer", "json_serializer"}
    assert second_call.kwargs.keys() == set()


def test_create_session_maker_if_session_maker_provided(
    config_cls: type[SQLAlchemySyncConfig],
) -> None:
    """Test create_session_maker if session maker provided to config."""
    session_maker = MagicMock()
    config = config_cls(session_maker=session_maker)
    assert config.create_session_maker() == session_maker


def test_create_session_maker_if_no_session_maker_or_bind_provided(
    config_cls: type[SQLAlchemySyncConfig],
    monkeypatch: MonkeyPatch,
) -> None:
    """Test create_session_maker if no session maker or bind provided to config."""
    config = config_cls()
    create_engine_mock = MagicMock(return_value=create_engine("sqlite://"))
    monkeypatch.setattr(config, "get_engine", create_engine_mock)
    assert config.session_maker is None
    assert isinstance(config.create_session_maker(), config.session_maker_class)
    create_engine_mock.assert_called_once()


def test_create_session_instance_if_session_not_in_scope_state(
    config_cls: type[SQLAlchemySyncConfig],
) -> None:
    """Test provide_session if session not in scope state."""
    with patch(
        "advanced_alchemy.extensions.litestar._utils.get_aa_scope_state",
    ) as get_scope_state_mock:
        get_scope_state_mock.return_value = None
        config = config_cls()
        state = State()
        state[config.session_maker_app_state_key] = MagicMock()
        scope: Scope = {}  # type:ignore[assignment]
        assert isinstance(config.provide_session(state, scope), MagicMock)
        assert SESSION_SCOPE_KEY in scope[_SCOPE_NAMESPACE]  # type: ignore[literal-required]


def test_app_state(config_cls: type[SQLAlchemySyncConfig], monkeypatch: MonkeyPatch) -> None:
    """Test app_state."""
    config = config_cls(connection_string="sqlite://")
    with patch.object(config, "create_session_maker") as create_session_maker_mock, patch.object(
        config,
        "get_engine",
    ) as create_engine_mock:
        assert config.create_app_state_items().keys() == {
            config.engine_app_state_key,
            config.session_maker_app_state_key,
        }
        create_session_maker_mock.assert_called_once()
        create_engine_mock.assert_called_once()
