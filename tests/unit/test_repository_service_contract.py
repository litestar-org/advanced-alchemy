"""Behavior shared by repositories and services that callers rely on across refactors."""

import asyncio
import logging
from collections.abc import Iterator
from typing import Generic, Optional, TypeVar

import pytest
from pydantic import BaseModel
from sqlalchemy import Engine, ForeignKey, create_engine, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship
from sqlalchemy.pool import StaticPool

from advanced_alchemy._listeners import (
    _register_session_async_task,  # pyright: ignore[reportPrivateUsage]
    flush_pending_async_listener_tasks,
)
from advanced_alchemy.exceptions import RepositoryError
from advanced_alchemy.repository import SQLAlchemySyncRepository
from advanced_alchemy.repository.memory import SQLAlchemySyncMockRepository
from advanced_alchemy.service import SQLAlchemySyncRepositoryService

ModelT = TypeVar("ModelT")
CreateT = TypeVar("CreateT")


class _Base(DeclarativeBase):
    pass


class _Renamed(_Base):
    __tablename__ = "contract_renamed"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column("title_col")


class _Parent(_Base):
    __tablename__ = "contract_parent"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[Optional[str]]
    children: Mapped[list["_Child"]] = relationship()


class _Child(_Base):
    __tablename__ = "contract_child"

    id: Mapped[int] = mapped_column(primary_key=True)
    parent_id: Mapped[int] = mapped_column(ForeignKey("contract_parent.id"))


class _RenamedRepository(SQLAlchemySyncRepository[_Renamed]):
    model_type = _Renamed


class _RenamedService(SQLAlchemySyncRepositoryService[_Renamed]):
    repository_type = _RenamedRepository


class _ParentRepository(SQLAlchemySyncRepository[_Parent]):
    model_type = _Parent


class _ParentMockRepository(SQLAlchemySyncMockRepository[_Parent]):
    model_type = _Parent


class _FakeSession:
    info: dict[str, object] = {}
    bind = None


@pytest.fixture(name="engine")
def fixture_engine() -> Iterator[Engine]:
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    _Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture(name="mock_repository")
def fixture_mock_repository() -> Iterator[_ParentMockRepository]:
    _ParentMockRepository.__database_clear__()
    repository = _ParentMockRepository(session=_FakeSession())  # type: ignore[arg-type]
    repository.add(_Parent(id=1, name="alpha"))
    repository.add(_Parent(id=2, name=None))
    repository.add(_Parent(id=3, name="gamma"))
    yield repository
    _ParentMockRepository.__database_clear__()


def test_update_applies_attribute_mapped_to_differently_named_column(engine: Engine) -> None:
    with Session(engine, expire_on_commit=False) as session:
        session.add(_Renamed(id=1, title="old"))
        session.commit()

        _RenamedService(session=session).update({"title": "new"}, item_id=1, auto_commit=True)

        session.expire_all()
        assert session.get(_Renamed, 1).title == "new"  # type: ignore[union-attr]


def test_explicit_uniquify_false_overrides_repository_default(engine: Engine) -> None:
    with Session(engine, expire_on_commit=False) as session:
        session.add(_Parent(id=1, name="p", children=[_Child(id=1), _Child(id=2)]))
        session.commit()
        statement = select(_Parent).join(_Parent.children)

        repository = _ParentRepository(session=session, statement=statement, uniquify=True)

        assert len(repository.get_many()) == 1
        assert len(repository.get_many(uniquify=False)) == 2


def test_inherited_repository_type_survives_extra_generic_parameters() -> None:
    class Create(BaseModel):
        name: str

    class BaseService(SQLAlchemySyncRepositoryService[ModelT], Generic[ModelT, CreateT]):  # type: ignore[type-var]
        pass

    class ParentService(BaseService[_Parent, Create]):
        repository_type = _ParentRepository

    class LeafService(ParentService):
        pass

    assert LeafService.repository_type is _ParentRepository


def test_mock_repository_evaluates_between(mock_repository: _ParentMockRepository) -> None:
    assert sorted(item.id for item in mock_repository.get_many(_Parent.id.between(1, 2))) == [1, 2]


def test_mock_repository_evaluates_null_comparison(mock_repository: _ParentMockRepository) -> None:
    assert [item.id for item in mock_repository.get_many(_Parent.name.is_(None))] == [2]


def test_mock_repository_rejects_unsupported_expression(mock_repository: _ParentMockRepository) -> None:
    with pytest.raises(RepositoryError, match="not supported in mock repositories"):
        mock_repository.get_many(func.lower(_Parent.name) == "alpha")


def test_flush_logs_failed_listener_task(caplog: pytest.LogCaptureFixture) -> None:
    async def fail() -> None:
        msg = "cache backend down"
        raise RuntimeError(msg)

    async def run() -> None:
        session = _FakeSession()
        session.info = {}
        _register_session_async_task(session, asyncio.create_task(fail()))
        await flush_pending_async_listener_tasks(session)

    with caplog.at_level(logging.WARNING, logger="advanced_alchemy"):
        asyncio.run(run())

    assert "cache backend down" in caplog.text
