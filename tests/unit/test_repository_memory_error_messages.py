from __future__ import annotations

from typing import Any, cast
from unittest.mock import create_autospec

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import Session

from advanced_alchemy.repository._util import DEFAULT_ERROR_MESSAGE_TEMPLATES
from advanced_alchemy.repository.memory import (
    SQLAlchemyAsyncMockRepository,
    SQLAlchemySyncMockRepository,
)


def _make_async_session() -> AsyncSession:
    session = cast(AsyncSession, create_autospec(AsyncSession, instance=True))
    engine = cast(AsyncEngine, create_autospec(AsyncEngine, instance=True))
    engine.dialect.name = "mock"
    session.bind = engine
    session.get_bind.return_value = engine
    return session


def _make_sync_session() -> Session:
    session = cast(Session, create_autospec(Session, instance=True))
    session.bind = cast(Any, create_autospec(object, instance=True))
    return session


def test_async_mock_repository_error_messages_isolated() -> None:
    class BaseRepo(SQLAlchemyAsyncMockRepository[Any]):
        model_type = object

    class RepoA(BaseRepo):
        error_messages = {"not_found": "Async Repo A"}

    class RepoB(BaseRepo):
        error_messages = {"not_found": "Async Repo B"}

    repo_a_first = RepoA(session=_make_async_session())
    repo_b = RepoB(session=_make_async_session())
    repo_a_second = RepoA(session=_make_async_session())

    assert repo_a_first.error_messages is not DEFAULT_ERROR_MESSAGE_TEMPLATES
    assert repo_a_first.error_messages is not repo_b.error_messages
    assert repo_a_first.error_messages["not_found"] == "Async Repo A"
    assert repo_b.error_messages["not_found"] == "Async Repo B"
    assert repo_a_second.error_messages["not_found"] == "Async Repo A"
    assert DEFAULT_ERROR_MESSAGE_TEMPLATES["not_found"] == "The requested resource was not found"


def test_async_mock_repository_instance_override_does_not_mutate_class() -> None:
    class Repo(SQLAlchemyAsyncMockRepository[Any]):
        model_type = object
        error_messages = {"other": "default other"}

    repo_custom = Repo(session=_make_async_session(), error_messages={"other": "custom other"})
    repo_plain = Repo(session=_make_async_session())

    assert repo_custom.error_messages["other"] == "custom other"
    assert repo_plain.error_messages["other"] == "default other"
    assert Repo.error_messages["other"] == "default other"


def test_sync_mock_repository_error_messages_isolated() -> None:
    class BaseRepo(SQLAlchemySyncMockRepository[Any]):
        model_type = object

    class RepoA(BaseRepo):
        error_messages = {"not_found": "Sync Repo A"}

    class RepoB(BaseRepo):
        error_messages = {"not_found": "Sync Repo B"}

    repo_a_first = RepoA(session=_make_sync_session())
    repo_b = RepoB(session=_make_sync_session())
    repo_a_second = RepoA(session=_make_sync_session())

    assert repo_a_first.error_messages is not DEFAULT_ERROR_MESSAGE_TEMPLATES
    assert repo_a_first.error_messages is not repo_b.error_messages
    assert repo_a_first.error_messages["not_found"] == "Sync Repo A"
    assert repo_b.error_messages["not_found"] == "Sync Repo B"
    assert repo_a_second.error_messages["not_found"] == "Sync Repo A"


def test_sync_mock_repository_instance_override_does_not_mutate_class() -> None:
    class Repo(SQLAlchemySyncMockRepository[Any]):
        model_type = object
        error_messages = {"duplicate_key": "sync default"}

    repo_custom = Repo(session=_make_sync_session(), error_messages={"duplicate_key": "custom sync"})
    repo_plain = Repo(session=_make_sync_session())

    assert repo_custom.error_messages["duplicate_key"] == "custom sync"
    assert repo_plain.error_messages["duplicate_key"] == "sync default"
    assert Repo.error_messages["duplicate_key"] == "sync default"
