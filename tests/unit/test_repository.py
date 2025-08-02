"""Unit tests for the SQLAlchemy Repository implementation."""

from __future__ import annotations

import datetime
import decimal
from collections.abc import AsyncGenerator, Collection, Generator
from typing import TYPE_CHECKING, Any, Union, cast
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from msgspec import Struct
from pydantic import BaseModel
from pytest_lazy_fixtures import lf
from sqlalchemy import Integer, String
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute, Mapped, Session, mapped_column
from sqlalchemy.types import TypeEngine

from advanced_alchemy import base
from advanced_alchemy.exceptions import IntegrityError, RepositoryError, wrap_sqlalchemy_exception
from advanced_alchemy.filters import (
    BeforeAfter,
    CollectionFilter,
    LimitOffset,
    NotInCollectionFilter,
    OnBeforeAfter,
)
from advanced_alchemy.repository import (
    SQLAlchemyAsyncRepository,
    SQLAlchemySyncRepository,
)
from advanced_alchemy.repository._util import column_has_defaults
from advanced_alchemy.service.typing import (
    is_msgspec_struct,
    is_pydantic_model,
    is_schema,
    is_schema_or_dict,
    is_schema_or_dict_with_field,
    is_schema_or_dict_without_field,
    is_schema_with_field,
    is_schema_without_field,
)
from tests.helpers import maybe_async

if TYPE_CHECKING:
    from _pytest.fixtures import FixtureRequest
    from pytest import MonkeyPatch
    from pytest_mock import MockerFixture


AnyMock = Union[MagicMock, AsyncMock]


class UUIDModel(base.UUIDAuditBase):
    """Inheriting from UUIDAuditBase gives the model 'created_at' and 'updated_at'
    columns.
    """


class BigIntModel(base.BigIntAuditBase):
    """Inheriting from BigIntAuditBase gives the model 'created_at' and 'updated_at'
    columns.
    """


@pytest.fixture()
async def async_mock_repo() -> AsyncGenerator[SQLAlchemyAsyncRepository[MagicMock], None]:
    """SQLAlchemy repository with a mock model type."""

    class Repo(SQLAlchemyAsyncRepository[MagicMock]):
        """Repo with mocked out stuff."""

        model_type = MagicMock(__name__="MagicMock")  # pyright:ignore[reportGeneralTypeIssues,reportAssignmentType]

    session = AsyncMock(spec=AsyncSession, bind=MagicMock())
    yield Repo(session=session, statement=MagicMock())


@pytest.fixture()
def sync_mock_repo() -> Generator[SQLAlchemySyncRepository[MagicMock], None, None]:
    """SQLAlchemy repository with a mock model type."""

    class Repo(SQLAlchemySyncRepository[MagicMock]):
        """Repo with mocked out stuff."""

        model_type = MagicMock(__name__="MagicMock")  # pyright:ignore[reportGeneralTypeIssues,reportAssignmentType]

    yield Repo(session=MagicMock(spec=Session, bind=MagicMock()), statement=MagicMock())


@pytest.fixture(params=[lf("sync_mock_repo"), lf("async_mock_repo")])
def mock_repo(request: FixtureRequest) -> Generator[SQLAlchemyAsyncRepository[MagicMock], None, None]:
    yield cast(SQLAlchemyAsyncRepository[Any], request.param)


@pytest.fixture()
def mock_session_scalars(  # pyright: ignore[reportUnknownParameterType]
    mock_repo: SQLAlchemyAsyncRepository[MagicMock], mocker: MockerFixture
) -> Generator[AnyMock, None, None]:
    yield mocker.patch.object(mock_repo.session, "scalars")


@pytest.fixture()
def mock_session_execute(  # pyright: ignore[reportUnknownParameterType]
    mock_repo: SQLAlchemyAsyncRepository[MagicMock], mocker: MockerFixture
) -> Generator[AnyMock, None, None]:
    yield mocker.patch.object(mock_repo.session, "scalars")


@pytest.fixture()
def mock_repo_list(  # pyright: ignore[reportUnknownParameterType]
    mock_repo: SQLAlchemyAsyncRepository[MagicMock], mocker: MockerFixture
) -> Generator[AnyMock, None, None]:
    yield mocker.patch.object(mock_repo, "list")


@pytest.fixture()
def mock_repo_execute(  # pyright: ignore[reportUnknownParameterType]
    mock_repo: SQLAlchemyAsyncRepository[MagicMock], mocker: MockerFixture
) -> Generator[AnyMock, None, None]:
    yield mocker.patch.object(mock_repo, "_execute")


@pytest.fixture()
def mock_repo_attach_to_session(  # pyright: ignore[reportUnknownParameterType]
    mock_repo: SQLAlchemyAsyncRepository[MagicMock], mocker: MockerFixture
) -> Generator[AnyMock, None, None]:
    yield mocker.patch.object(mock_repo, "_attach_to_session")


@pytest.fixture()
def mock_repo_count(  # pyright: ignore[reportUnknownParameterType]
    mock_repo: SQLAlchemyAsyncRepository[MagicMock], mocker: MockerFixture
) -> Generator[AnyMock, None, None]:
    yield mocker.patch.object(mock_repo, "count")


def test_sqlalchemy_tablename() -> None:
    """Test the snake case conversion for table names."""

    class BigModel(base.UUIDAuditBase):
        """Inheriting from UUIDAuditBase gives the model 'created_at' and 'updated_at'
        columns.
        """

    class TESTModel(base.UUIDAuditBase):
        """Inheriting from UUIDAuditBase gives the model 'created_at' and 'updated_at'
        columns.
        """

    class OtherBigIntModel(base.BigIntAuditBase):
        """Inheriting from BigIntAuditBase gives the model 'created_at' and 'updated_at'
        columns.
        """

    assert BigModel.__tablename__ == "big_model"
    assert TESTModel.__tablename__ == "test_model"
    assert OtherBigIntModel.__tablename__ == "other_big_int_model"


def test_sqlalchemy_sentinel(monkeypatch: MonkeyPatch) -> None:
    """Test the sqlalchemy sentinel column only exists on `UUIDPrimaryKey` models."""

    class AnotherModel(base.UUIDAuditBase):
        """Inheriting from UUIDAuditBase gives the model 'created_at' and 'updated_at'
        columns.
        """

        the_extra_col: Mapped[str] = mapped_column(String(length=100), nullable=True)  # pyright: ignore

    class TheTestModel(base.UUIDBase):
        """Inheriting from DeclarativeBase gives the model 'id'  columns."""

        the_extra_col: Mapped[str] = mapped_column(String(length=100), nullable=True)  # pyright: ignore

    class TheBigIntModel(base.BigIntBase):
        """Inheriting from DeclarativeBase gives the model 'id'  columns."""

        the_extra_col: Mapped[str] = mapped_column(String(length=100), nullable=True)  # pyright: ignore

    unloaded_cols = {"the_extra_col"}
    sa_instance_mock = MagicMock(unloaded=unloaded_cols)

    assert isinstance(AnotherModel._sentinel, InstrumentedAttribute)  # pyright: ignore
    assert isinstance(TheTestModel._sentinel, InstrumentedAttribute)  # pyright: ignore
    assert not hasattr(TheBigIntModel, "_sentinel")

    model1, model2, model3 = AnotherModel(), TheTestModel(), TheBigIntModel()
    monkeypatch.setattr(model1, "_sa_instance_state", sa_instance_mock)
    monkeypatch.setattr(model2, "_sa_instance_state", sa_instance_mock)
    monkeypatch.setattr(model3, "_sa_instance_state", sa_instance_mock)

    assert "created_at" not in model1.to_dict(exclude={"created_at"})
    assert "the_extra_col" not in model1.to_dict(exclude={"created_at"})
    assert "sa_orm_sentinel" not in model1.to_dict()
    assert "sa_orm_sentinel" not in model2.to_dict()
    assert "sa_orm_sentinel" not in model3.to_dict()
    assert "_sentinel" not in model1.to_dict()
    assert "_sentinel" not in model2.to_dict()
    assert "_sentinel" not in model3.to_dict()
    assert "the_extra_col" not in model1.to_dict()


def test_wrap_sqlalchemy_integrity_error() -> None:
    """Test to ensure we wrap IntegrityError."""
    with pytest.raises(IntegrityError), wrap_sqlalchemy_exception():
        raise IntegrityError(None, None, Exception())


def test_wrap_sqlalchemy_generic_error() -> None:
    """Test to ensure we wrap generic SQLAlchemy exceptions."""
    with pytest.raises(RepositoryError), wrap_sqlalchemy_exception():
        raise SQLAlchemyError


async def test_sqlalchemy_repo_add(mock_repo: SQLAlchemyAsyncRepository[Any]) -> None:
    """Test expected method calls for add operation."""
    mock_instance = MagicMock()

    instance = await maybe_async(mock_repo.add(mock_instance))

    assert instance is mock_instance
    mock_repo.session.add.assert_called_once_with(mock_instance)  # pyright: ignore[reportFunctionMemberAccess]
    mock_repo.session.flush.assert_called_once()  # pyright: ignore[reportFunctionMemberAccess]
    mock_repo.session.refresh.assert_called_once_with(  # pyright: ignore[reportFunctionMemberAccess]
        instance=mock_instance,
        attribute_names=None,
        with_for_update=None,
    )
    mock_repo.session.expunge.assert_not_called()  # pyright: ignore[reportFunctionMemberAccess]
    mock_repo.session.commit.assert_not_called()  # pyright: ignore[reportFunctionMemberAccess]


async def test_sqlalchemy_repo_add_many(
    mock_repo: SQLAlchemyAsyncRepository[Any],
    monkeypatch: MonkeyPatch,
    mocker: MockerFixture,
    request: FixtureRequest,
) -> None:
    """Test expected method calls for add many operation."""

    mock_instances = [MagicMock(), MagicMock(), MagicMock()]
    monkeypatch.setattr(mock_repo, "model_type", UUIDModel)
    mocker.patch.object(mock_repo.session, "scalars", return_value=mock_instances)

    instances = await maybe_async(mock_repo.add_many(mock_instances))

    assert len(instances) == 3
    for row in instances:
        assert row.id is not None
    mock_repo.session.expunge.assert_not_called()  # pyright: ignore[reportFunctionMemberAccess]
    mock_repo.session.commit.assert_not_called()  # pyright: ignore[reportFunctionMemberAccess]


async def test_sqlalchemy_repo_update_many(
    mock_repo: SQLAlchemyAsyncRepository[Any],
    monkeypatch: MonkeyPatch,
    mocker: MockerFixture,
) -> None:
    """Test expected method calls for update many operation."""

    mock_instances = [MagicMock(), MagicMock(), MagicMock()]
    monkeypatch.setattr(mock_repo, "model_type", UUIDModel)
    mocker.patch.object(mock_repo.session, "scalars", return_value=mock_instances)

    instances = await maybe_async(mock_repo.update_many(mock_instances))

    assert len(instances) == 3
    for row in instances:
        assert row.id is not None

    mock_repo.session.flush.assert_called_once()  # pyright: ignore[reportFunctionMemberAccess]
    mock_repo.session.commit.assert_not_called()  # pyright: ignore[reportFunctionMemberAccess]


async def test_sqlalchemy_repo_upsert_many(
    mock_repo: SQLAlchemyAsyncRepository[Any],
    monkeypatch: MonkeyPatch,
    mocker: MockerFixture,
) -> None:
    """Test expected method calls for update many operation."""

    mock_instances = [MagicMock(), MagicMock(), MagicMock()]
    monkeypatch.setattr(mock_repo, "model_type", UUIDModel)
    mocker.patch.object(mock_repo.session, "scalars", return_value=mock_instances)
    mocker.patch.object(mock_repo, "list", return_value=mock_instances)
    mocker.patch.object(mock_repo, "add_many", return_value=mock_instances)
    mocker.patch.object(mock_repo, "update_many", return_value=mock_instances)

    instances = await maybe_async(mock_repo.upsert_many(mock_instances))

    assert len(instances) == 3
    for row in instances:
        assert row.id is not None

    mock_repo.session.commit.assert_not_called()  # pyright: ignore[reportFunctionMemberAccess]


async def test_sqlalchemy_repo_delete(mock_repo: SQLAlchemyAsyncRepository[Any], mocker: MockerFixture) -> None:
    """Test expected method calls for delete operation."""
    mock_instance = MagicMock()
    mocker.patch.object(mock_repo, "get", return_value=mock_instance)
    instance = await maybe_async(mock_repo.delete("instance-id"))

    assert instance is mock_instance

    mock_repo.session.delete.assert_called_once_with(mock_instance)  # pyright: ignore[reportFunctionMemberAccess]
    mock_repo.session.flush.assert_called_once()  # pyright: ignore[reportFunctionMemberAccess]
    mock_repo.session.expunge.assert_not_called()  # pyright: ignore[reportFunctionMemberAccess]
    mock_repo.session.commit.assert_not_called()  # pyright: ignore[reportFunctionMemberAccess]


async def test_sqlalchemy_repo_delete_many_uuid(
    mock_repo: SQLAlchemyAsyncRepository[Any],
    monkeypatch: MonkeyPatch,
    mock_session_scalars: AnyMock,
    mock_session_execute: AnyMock,
    mock_repo_list: AnyMock,
) -> None:
    """Test expected method calls for delete operation."""

    mock_instances = [MagicMock(), MagicMock(id=uuid4())]
    mock_session_scalars.return_value = mock_instances
    mock_session_execute.return_value = mock_instances
    mock_repo_list.return_value = mock_instances
    monkeypatch.setattr(mock_repo, "model_type", UUIDModel)
    monkeypatch.setattr(mock_repo.session.bind.dialect, "insertmanyvalues_max_parameters", 2)

    added_instances = await maybe_async(mock_repo.add_many(mock_instances))
    instances = await maybe_async(mock_repo.delete_many([obj.id for obj in added_instances]))

    assert len(instances) == len(mock_instances)
    mock_repo.session.flush.assert_called()  # pyright: ignore[reportFunctionMemberAccess]
    mock_repo.session.commit.assert_not_called()  # pyright: ignore[reportFunctionMemberAccess]


async def test_sqlalchemy_repo_delete_many_bigint(
    mock_repo: SQLAlchemyAsyncRepository[Any],
    monkeypatch: MonkeyPatch,
    mock_session_scalars: AnyMock,
    mock_session_execute: AnyMock,
    mock_repo_list: AnyMock,
    testrun_uid: str,
) -> None:
    """Test expected method calls for delete operation."""

    mock_instances = [MagicMock(), MagicMock(id=uuid4())]
    mock_session_scalars.return_value = mock_instances
    mock_session_execute.return_value = mock_instances
    mock_repo_list.return_value = mock_instances
    monkeypatch.setattr(mock_repo, "model_type", BigIntModel)
    monkeypatch.setattr(mock_repo.session.bind.dialect, "insertmanyvalues_max_parameters", 2)

    added_instances = await maybe_async(mock_repo.add_many(mock_instances))
    instances = await maybe_async(mock_repo.delete_many([obj.id for obj in added_instances]))

    assert len(instances) == len(mock_instances)
    mock_repo.session.flush.assert_called()  # pyright: ignore[reportFunctionMemberAccess]
    mock_repo.session.commit.assert_not_called()  # pyright: ignore[reportFunctionMemberAccess]


async def test_sqlalchemy_repo_get_member(
    mock_repo: SQLAlchemyAsyncRepository[Any],
    monkeypatch: MonkeyPatch,
    mock_repo_execute: AnyMock,
) -> None:
    """Test expected method calls for member get operation."""
    mock_instance = MagicMock()
    mock_repo_execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=mock_instance))

    instance = await maybe_async(mock_repo.get("instance-id"))

    assert instance is mock_instance
    mock_repo.session.expunge.assert_not_called()  # pyright: ignore[reportFunctionMemberAccess]
    mock_repo.session.commit.assert_not_called()  # pyright: ignore[reportFunctionMemberAccess]


async def test_sqlalchemy_repo_get_one_member(
    mock_repo: SQLAlchemyAsyncRepository[Any],
    monkeypatch: MonkeyPatch,
    mock_repo_execute: AnyMock,
) -> None:
    """Test expected method calls for member get one operation."""
    mock_instance = MagicMock()
    mock_repo_execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=mock_instance))

    instance = await maybe_async(mock_repo.get_one(id="instance-id"))

    assert instance is mock_instance
    mock_repo.session.expunge.assert_not_called()  # pyright: ignore[reportFunctionMemberAccess]
    mock_repo.session.commit.assert_not_called()  # pyright: ignore[reportFunctionMemberAccess]


async def test_sqlalchemy_repo_get_or_upsert_member_existing(
    mock_repo: SQLAlchemyAsyncRepository[Any],
    monkeypatch: MonkeyPatch,
    mock_repo_execute: AnyMock,
    mock_repo_attach_to_session: AnyMock,
) -> None:
    """Test expected method calls for member get or create operation (existing)."""
    mock_instance = MagicMock()
    mock_repo_execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=mock_instance))
    mock_repo_attach_to_session.return_value = mock_instance

    instance, created = await maybe_async(mock_repo.get_or_upsert(id="instance-id", upsert=False))

    assert instance is mock_instance
    assert created is False
    mock_repo.session.expunge.assert_not_called()  # pyright: ignore[reportFunctionMemberAccess]
    mock_repo.session.merge.assert_not_called()  # pyright: ignore[reportFunctionMemberAccess]
    mock_repo.session.refresh.assert_not_called()  # pyright: ignore[reportFunctionMemberAccess]


async def test_sqlalchemy_repo_get_or_upsert_member_existing_upsert(
    mock_repo: SQLAlchemyAsyncRepository[Any],
    monkeypatch: MonkeyPatch,
    mock_repo_execute: AnyMock,
    mock_repo_attach_to_session: AnyMock,
) -> None:
    """Test expected method calls for member get or create operation (existing)."""
    mock_instance = MagicMock()
    mock_repo_execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=mock_instance))
    mock_repo_attach_to_session.return_value = mock_instance

    instance, created = await maybe_async(
        mock_repo.get_or_upsert(id="instance-id", upsert=True, an_extra_attribute="yep"),
    )

    assert instance is mock_instance
    assert created is False
    mock_repo.session.expunge.assert_not_called()  # pyright: ignore[reportFunctionMemberAccess]
    mock_repo._attach_to_session.assert_called_once()  # pyright: ignore[reportFunctionMemberAccess,reportPrivateUsage]
    mock_repo.session.flush.assert_called_once()  # pyright: ignore[reportFunctionMemberAccess]
    mock_repo.session.refresh.assert_called_once_with(  # pyright: ignore[reportFunctionMemberAccess]
        instance=mock_instance,
        attribute_names=None,
        with_for_update=None,
    )


async def test_sqlalchemy_repo_get_or_upsert_member_existing_no_upsert(
    mock_repo: SQLAlchemyAsyncRepository[Any],
    monkeypatch: MonkeyPatch,
    mock_repo_execute: AnyMock,
) -> None:
    """Test expected method calls for member get or create operation (existing)."""
    mock_instance = MagicMock()
    mock_repo_execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=mock_instance))

    instance, created = await maybe_async(
        mock_repo.get_or_upsert(id="instance-id", upsert=False, an_extra_attribute="yep"),
    )

    assert instance is mock_instance
    assert created is False
    mock_repo.session.expunge.assert_not_called()  # pyright: ignore[reportFunctionMemberAccess]
    mock_repo.session.add.assert_not_called()  # pyright: ignore[reportFunctionMemberAccess]
    mock_repo.session.refresh.assert_not_called()  # pyright: ignore[reportFunctionMemberAccess]


async def test_sqlalchemy_repo_get_or_upsert_member_created(
    mock_repo: SQLAlchemyAsyncRepository[Any],
    monkeypatch: MonkeyPatch,
    mock_repo_execute: AnyMock,
) -> None:
    """Test expected method calls for member get or create operation (created)."""
    mock_repo_execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=None))

    instance, created = await maybe_async(mock_repo.get_or_upsert(id="new-id"))

    assert instance is not None
    assert created is True
    mock_repo.session.expunge.assert_not_called()  # pyright: ignore[reportFunctionMemberAccess]
    mock_repo.session.add.assert_called_once_with(instance)  # pyright: ignore[reportFunctionMemberAccess]
    mock_repo.session.refresh.assert_called_once_with(instance=instance, attribute_names=None, with_for_update=None)  # pyright: ignore[reportFunctionMemberAccess]


async def test_sqlalchemy_repo_get_one_or_none_member(
    mock_repo: SQLAlchemyAsyncRepository[Any],
    monkeypatch: MonkeyPatch,
    mock_repo_execute: AnyMock,
) -> None:
    """Test expected method calls for member get one or none operation (found)."""
    mock_instance = MagicMock()
    mock_repo_execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=mock_instance))

    instance = await maybe_async(mock_repo.get_one_or_none(id="instance-id"))

    assert instance is mock_instance
    mock_repo.session.expunge.assert_not_called()  # pyright: ignore[reportFunctionMemberAccess]
    mock_repo.session.commit.assert_not_called()  # pyright: ignore[reportFunctionMemberAccess]


async def test_sqlalchemy_repo_get_one_or_none_not_found(
    mock_repo: SQLAlchemyAsyncRepository[Any],
    monkeypatch: MonkeyPatch,
    mock_repo_execute: AnyMock,
) -> None:
    """Test expected method calls for member get one or none operation (Not found)."""

    mock_repo_execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=None))

    instance = await maybe_async(mock_repo.get_one_or_none(id="instance-id"))

    assert instance is None
    mock_repo.session.expunge.assert_not_called()  # pyright: ignore[reportFunctionMemberAccess]
    mock_repo.session.commit.assert_not_called()  # pyright: ignore[reportFunctionMemberAccess]


async def test_sqlalchemy_repo_list(
    mock_repo: SQLAlchemyAsyncRepository[Any],
    monkeypatch: MonkeyPatch,
    mock_repo_execute: AnyMock,
) -> None:
    """Test expected method calls for list operation."""
    mock_instances = [MagicMock(), MagicMock()]
    mock_repo_execute.return_value = MagicMock(scalars=MagicMock(return_value=mock_instances))

    instances = await maybe_async(mock_repo.list())

    assert instances == mock_instances
    mock_repo.session.expunge.assert_not_called()  # pyright: ignore[reportFunctionMemberAccess]
    mock_repo.session.commit.assert_not_called()  # pyright: ignore[reportFunctionMemberAccess]


async def test_sqlalchemy_repo_list_and_count(mock_repo: SQLAlchemyAsyncRepository[Any], mocker: MockerFixture) -> None:
    """Test expected method calls for list operation."""
    mock_instances = [MagicMock(), MagicMock()]
    mock_count = len(mock_instances)
    mocker.patch.object(mock_repo, "_list_and_count_window", return_value=(mock_instances, mock_count))

    instances, instance_count = await maybe_async(mock_repo.list_and_count())

    assert instances == mock_instances
    assert instance_count == mock_count
    mock_repo.session.expunge.assert_not_called()  # pyright: ignore[reportFunctionMemberAccess]
    mock_repo.session.commit.assert_not_called()  # pyright: ignore[reportFunctionMemberAccess]


async def test_sqlalchemy_repo_list_and_count_basic(
    mock_repo: SQLAlchemyAsyncRepository[Any],
    mocker: MockerFixture,
) -> None:
    """Test expected method calls for list operation."""
    mock_instances = [MagicMock(), MagicMock()]
    mock_count = len(mock_instances)
    mocker.patch.object(mock_repo, "_list_and_count_basic", return_value=(mock_instances, mock_count))

    instances, instance_count = await maybe_async(mock_repo.list_and_count(count_with_window_function=False))

    assert instances == mock_instances
    assert instance_count == mock_count
    mock_repo.session.expunge.assert_not_called()  # pyright: ignore[reportFunctionMemberAccess]
    mock_repo.session.commit.assert_not_called()  # pyright: ignore[reportFunctionMemberAccess]


async def test_sqlalchemy_repo_exists(
    mock_repo: SQLAlchemyAsyncRepository[Any],
    monkeypatch: MonkeyPatch,
    mock_repo_execute: AnyMock,
    mock_repo_count: AnyMock,
) -> None:
    """Test expected method calls for exists operation."""
    mock_repo_count.return_value = 1

    exists = await maybe_async(mock_repo.exists(id="my-id"))

    assert exists
    mock_repo.session.commit.assert_not_called()  # pyright: ignore[reportFunctionMemberAccess]


async def test_sqlalchemy_repo_exists_with_filter(
    mock_repo: SQLAlchemyAsyncRepository[Any],
    monkeypatch: MonkeyPatch,
    mock_repo_execute: AnyMock,
    mock_repo_count: AnyMock,
) -> None:
    """Test expected method calls for exists operation. with filter argument"""
    limit_filter = LimitOffset(limit=1, offset=0)
    mock_repo_count.return_value = 1

    exists = await maybe_async(mock_repo.exists(limit_filter, id="my-id"))

    assert exists
    mock_repo.session.commit.assert_not_called()  # pyright: ignore[reportFunctionMemberAccess]


async def test_sqlalchemy_repo_count(
    mock_repo: SQLAlchemyAsyncRepository[Any],
    monkeypatch: MonkeyPatch,
    mock_repo_execute: AnyMock,
    mock_repo_count: AnyMock,
) -> None:
    """Test expected method calls for list operation."""
    mock_repo_count.return_value = 1

    count = await maybe_async(mock_repo.count())

    assert count == 1
    mock_repo.session.commit.assert_not_called()  # pyright: ignore[reportFunctionMemberAccess]


async def test_sqlalchemy_repo_list_with_pagination(
    mock_repo: SQLAlchemyAsyncRepository[Any],
    monkeypatch: MonkeyPatch,
    mock_repo_execute: AnyMock,
    mocker: MockerFixture,
) -> None:
    """Test list operation with pagination."""
    statement = MagicMock()
    mock_repo_execute.return_value = MagicMock()
    mocker.patch.object(LimitOffset, "append_to_statement", return_value=statement)
    mock_repo_execute.return_value = MagicMock()
    await maybe_async(mock_repo.list(LimitOffset(2, 3)))
    mock_repo._execute.assert_called_with(statement, uniquify=False)  # pyright: ignore[reportFunctionMemberAccess,reportPrivateUsage]


async def test_sqlalchemy_repo_list_with_before_after_filter(
    mock_repo: SQLAlchemyAsyncRepository[Any],
    mock_repo_execute: AnyMock,
    mocker: MockerFixture,
) -> None:
    """Test list operation with BeforeAfter filter."""
    statement = MagicMock()
    mocker.patch.object(mock_repo.model_type.updated_at, "__lt__", return_value="lt")
    mocker.patch.object(mock_repo.model_type.updated_at, "__gt__", return_value="gt")
    mocker.patch.object(BeforeAfter, "append_to_statement", return_value=statement)
    mock_repo_execute.return_value = MagicMock()
    await maybe_async(mock_repo.list(BeforeAfter("updated_at", datetime.datetime.max, datetime.datetime.min)))
    mock_repo._execute.assert_called_with(statement, uniquify=False)  # pyright: ignore[reportFunctionMemberAccess,reportPrivateUsage]


async def test_sqlalchemy_repo_list_with_on_before_after_filter(
    mock_repo: SQLAlchemyAsyncRepository[Any],
    monkeypatch: MonkeyPatch,
    mock_repo_execute: AnyMock,
    mocker: MockerFixture,
) -> None:
    """Test list operation with BeforeAfter filter."""
    statement = MagicMock()
    mocker.patch.object(mock_repo.model_type.updated_at, "__le__", return_value="le")
    mocker.patch.object(mock_repo.model_type.updated_at, "__ge__", return_value="ge")
    mocker.patch.object(OnBeforeAfter, "append_to_statement", return_value=statement)

    mock_repo_execute.return_value = MagicMock()
    await maybe_async(mock_repo.list(OnBeforeAfter("updated_at", datetime.datetime.max, datetime.datetime.min)))
    mock_repo._execute.assert_called_with(statement, uniquify=False)  # pyright: ignore[reportFunctionMemberAccess,reportPrivateUsage]


async def test_sqlalchemy_repo_list_with_collection_filter(
    mock_repo: SQLAlchemyAsyncRepository[Any],
    monkeypatch: MonkeyPatch,
    mock_repo_execute: AnyMock,
    mocker: MockerFixture,
) -> None:
    """Test behavior of list operation given CollectionFilter."""
    field_name = "id"
    mock_repo_execute.return_value = MagicMock()
    mock_repo.statement.where.return_value = mock_repo.statement  # pyright: ignore[reportFunctionMemberAccess]
    mocker.patch.object(CollectionFilter, "append_to_statement", return_value=mock_repo.statement)
    values = [1, 2, 3]
    await maybe_async(mock_repo.list(CollectionFilter(field_name, values)))
    mock_repo._execute.assert_called_with(mock_repo.statement, uniquify=False)  # pyright: ignore[reportFunctionMemberAccess,reportPrivateUsage]


async def test_sqlalchemy_repo_list_with_null_collection_filter(
    mock_repo: SQLAlchemyAsyncRepository[Any],
    monkeypatch: MonkeyPatch,
    mock_repo_execute: AnyMock,
    mocker: MockerFixture,
) -> None:
    """Test behavior of list operation given CollectionFilter."""
    field_name = "id"
    mock_repo_execute.return_value = MagicMock()
    mock_repo.statement.where.return_value = mock_repo.statement  # pyright: ignore[reportFunctionMemberAccess]
    monkeypatch.setattr(
        CollectionFilter,
        "append_to_statement",
        MagicMock(return_value=mock_repo.statement),
    )
    await maybe_async(mock_repo.list(CollectionFilter(field_name, None)))  # pyright: ignore[reportFunctionMemberAccess,reportUnknownArgumentType]
    mock_repo._execute.assert_called_with(mock_repo.statement, uniquify=False)  # pyright: ignore[reportFunctionMemberAccess,reportPrivateUsage]


async def test_sqlalchemy_repo_empty_list_with_collection_filter(
    mock_repo: SQLAlchemyAsyncRepository[Any],
    monkeypatch: MonkeyPatch,
    mock_repo_execute: AnyMock,
    mocker: MockerFixture,
) -> None:
    """Test behavior of list operation given CollectionFilter."""
    field_name = "id"
    mock_repo_execute.return_value = MagicMock()
    mock_repo.statement.where.return_value = mock_repo.statement  # pyright: ignore[reportFunctionMemberAccess]
    values: Collection[Any] = []
    await maybe_async(mock_repo.list(CollectionFilter(field_name, values)))
    monkeypatch.setattr(
        CollectionFilter,
        "append_to_statement",
        MagicMock(return_value=mock_repo.statement),
    )
    await maybe_async(mock_repo.list(CollectionFilter(field_name, values)))
    mock_repo._execute.assert_called_with(mock_repo.statement, uniquify=False)  # pyright: ignore[reportFunctionMemberAccess,reportPrivateUsage]


async def test_sqlalchemy_repo_list_with_not_in_collection_filter(
    mock_repo: SQLAlchemyAsyncRepository[Any],
    monkeypatch: MonkeyPatch,
    mock_repo_execute: AnyMock,
    mocker: MockerFixture,
) -> None:
    """Test behavior of list operation given CollectionFilter."""
    field_name = "id"
    mock_repo_execute.return_value = MagicMock()
    mock_repo.statement.where.return_value = mock_repo.statement  # pyright: ignore[reportFunctionMemberAccess]
    monkeypatch.setattr(
        NotInCollectionFilter,
        "append_to_statement",
        MagicMock(return_value=mock_repo.statement),
    )
    values = [1, 2, 3]
    await maybe_async(mock_repo.list(NotInCollectionFilter(field_name, values)))
    mock_repo._execute.assert_called_with(mock_repo.statement, uniquify=False)  # pyright: ignore[reportFunctionMemberAccess,reportPrivateUsage]


async def test_sqlalchemy_repo_list_with_null_not_in_collection_filter(
    mock_repo: SQLAlchemyAsyncRepository[Any],
    monkeypatch: MonkeyPatch,
    mock_repo_execute: AnyMock,
    mocker: MockerFixture,
) -> None:
    """Test behavior of list operation given CollectionFilter."""
    field_name = "id"
    mock_repo_execute.return_value = MagicMock()
    mock_repo.statement.where.return_value = mock_repo.statement  # pyright: ignore[reportFunctionMemberAccess]
    monkeypatch.setattr(
        NotInCollectionFilter,
        "append_to_statement",
        MagicMock(return_value=mock_repo.statement),
    )
    await maybe_async(mock_repo.list(NotInCollectionFilter[str](field_name, None)))  # pyright: ignore[reportFunctionMemberAccess]
    mock_repo._execute.assert_called_with(mock_repo.statement, uniquify=False)  # pyright: ignore[reportFunctionMemberAccess,reportPrivateUsage]


async def test_sqlalchemy_repo_unknown_filter_type_raises(mock_repo: SQLAlchemyAsyncRepository[Any]) -> None:
    """Test that repo raises exception if list receives unknown filter type."""
    with pytest.raises(RepositoryError):
        await maybe_async(mock_repo.list("not a filter"))  # type: ignore


async def test_sqlalchemy_repo_update(
    mock_repo: SQLAlchemyAsyncRepository[Any],
    monkeypatch: MonkeyPatch,
    mocker: MockerFixture,
) -> None:
    """Test the sequence of repo calls for update operation."""
    id_ = 3
    mock_instance = MagicMock()
    existing_instance = MagicMock()
    mocker.patch.object(mock_repo, "get_id_attribute_value", return_value=id_)
    mocker.patch.object(mock_repo, "get", return_value=existing_instance)
    mock_repo.session.merge.return_value = existing_instance  # pyright: ignore[reportFunctionMemberAccess]

    instance = await maybe_async(mock_repo.update(mock_instance))

    assert instance is existing_instance
    mock_repo.session.merge.assert_called_once_with(existing_instance, load=True)  # pyright: ignore[reportFunctionMemberAccess]
    mock_repo.session.flush.assert_called_once()  # pyright: ignore[reportFunctionMemberAccess]
    mock_repo.session.expunge.assert_not_called()  # pyright: ignore[reportFunctionMemberAccess]
    mock_repo.session.commit.assert_not_called()  # pyright: ignore[reportFunctionMemberAccess]
    mock_repo.session.refresh.assert_called_once_with(  # pyright: ignore[reportFunctionMemberAccess]
        instance=existing_instance,
        attribute_names=None,
        with_for_update=None,
    )


async def test_sqlalchemy_repo_upsert(mock_repo: SQLAlchemyAsyncRepository[Any], mocker: MockerFixture) -> None:
    """Test the sequence of repo calls for upsert operation."""
    mock_instance = MagicMock()
    mock_repo.session.merge.return_value = mock_instance  # pyright: ignore[reportFunctionMemberAccess]

    instance = await maybe_async(mock_repo.upsert(mock_instance))
    mocker.patch.object(mock_repo, "exists", return_value=True)
    mocker.patch.object(mock_repo, "count", return_value=1)

    assert instance is mock_instance
    mock_repo.session.flush.assert_called_once()  # pyright: ignore[reportFunctionMemberAccess]
    mock_repo.session.expunge.assert_not_called()  # pyright: ignore[reportFunctionMemberAccess]
    mock_repo.session.commit.assert_not_called()  # pyright: ignore[reportFunctionMemberAccess]
    mock_repo.session.refresh.assert_called_once_with(  # pyright: ignore[reportFunctionMemberAccess]
        instance=mock_instance,
        attribute_names=None,
        with_for_update=None,
    )


async def test_attach_to_session_unexpected_strategy_raises_valueerror(
    mock_repo: SQLAlchemyAsyncRepository[Any],
) -> None:
    """Test to hit the error condition in SQLAlchemy._attach_to_session()."""
    with pytest.raises(ValueError):
        await maybe_async(mock_repo._attach_to_session(MagicMock(), strategy="t-rex"))  # type:ignore[arg-type]


async def test_execute(mock_repo: SQLAlchemyAsyncRepository[Any]) -> None:
    """Simple test of the abstraction over `AsyncSession.execute()`"""
    _ = await maybe_async(mock_repo._execute(mock_repo.statement))  # pyright: ignore[reportFunctionMemberAccess,reportPrivateUsage]
    mock_repo.session.execute.assert_called_once_with(mock_repo.statement)  # pyright: ignore[reportFunctionMemberAccess]


async def test_filter_in_collection_noop_if_collection_empty(mock_repo: SQLAlchemyAsyncRepository[Any]) -> None:
    """Ensures we don't filter on an empty collection."""
    statement = MagicMock()
    filter = CollectionFilter(field_name="id", values=[])  # type:ignore[var-annotated]
    statement = filter.append_to_statement(statement, MagicMock())  # type:ignore[assignment]
    mock_repo.statement.where.assert_not_called()  # pyright: ignore[reportFunctionMemberAccess]


@pytest.mark.parametrize(
    ("before", "after"),
    [
        (datetime.datetime.max, datetime.datetime.min),
        (None, datetime.datetime.min),
        (datetime.datetime.max, None),
    ],
)
async def test_filter_on_datetime_field(
    before: datetime.datetime,
    after: datetime.datetime,
    mock_repo: SQLAlchemyAsyncRepository[Any],
    mocker: MockerFixture,
    monkeypatch: MonkeyPatch,
) -> None:
    """Test through branches of _filter_on_datetime_field()"""
    field_mock = MagicMock(return_value=before or after)
    statement = MagicMock()
    field_mock.__gt__ = field_mock.__lt__ = lambda self, other: True  # pyright: ignore[reportFunctionMemberAccess,reportUnknownLambdaType]
    monkeypatch.setattr(
        BeforeAfter,
        "append_to_statement",
        MagicMock(return_value=mock_repo.statement),
    )
    filter = BeforeAfter(field_name="updated_at", before=before, after=after)
    statement = filter.append_to_statement(statement, MagicMock(return_value=before or after))  # type:ignore[assignment]
    mock_repo.model_type.updated_at = field_mock
    mock_repo.statement.where.assert_not_called()  # pyright: ignore[reportFunctionMemberAccess]


# Type compatibility test fixtures and classes
class MockComplexType:
    """Mock complex type that would have DBAPI serialization issues."""

    def __init__(self, value: Any):
        self.value = value


class MockPostgreSQLRange:
    """Mock PostgreSQL Range type."""

    def __init__(self, lower: Any, upper: Any):
        self.lower = lower
        self.upper = upper


class MockTypeWithoutPythonType(TypeEngine[Any]):
    """Mock SQLAlchemy type that doesn't implement python_type."""

    def __init__(self) -> None:
        super().__init__()

    @property
    def python_type(self) -> type[Any]:
        raise NotImplementedError("This type doesn't have a python_type")


async def test_type_must_use_in_empty_list(mock_repo: SQLAlchemyAsyncRepository[Any]) -> None:
    """Test that empty list returns False."""
    result = mock_repo._type_must_use_in_instead_of_any([])
    assert result is False


async def test_type_must_use_in_standard_python_types(mock_repo: SQLAlchemyAsyncRepository[Any]) -> None:
    """Test that standard Python types can use ANY() operator."""
    # Test integers
    result = mock_repo._type_must_use_in_instead_of_any([1, 2, 3])
    assert result is False

    # Test strings
    result = mock_repo._type_must_use_in_instead_of_any(["a", "b", "c"])
    assert result is False

    # Test booleans
    result = mock_repo._type_must_use_in_instead_of_any([True, False])
    assert result is False

    # Test floats
    result = mock_repo._type_must_use_in_instead_of_any([1.1, 2.2])
    assert result is False

    # Test bytes
    result = mock_repo._type_must_use_in_instead_of_any([b"test", b"data"])
    assert result is False


async def test_type_must_use_in_safe_datetime_decimal_types(mock_repo: SQLAlchemyAsyncRepository[Any]) -> None:
    """Test that datetime and decimal types can use ANY() operator."""
    # Test datetime.date
    result = mock_repo._type_must_use_in_instead_of_any([datetime.date(2024, 1, 1)])
    assert result is False

    # Test datetime.datetime
    result = mock_repo._type_must_use_in_instead_of_any([datetime.datetime.now()])
    assert result is False

    # Test datetime.time
    result = mock_repo._type_must_use_in_instead_of_any([datetime.time(12, 30)])
    assert result is False

    # Test datetime.timedelta
    result = mock_repo._type_must_use_in_instead_of_any([datetime.timedelta(days=1)])
    assert result is False

    # Test decimal.Decimal
    result = mock_repo._type_must_use_in_instead_of_any([decimal.Decimal("10.5")])
    assert result is False


async def test_type_must_use_in_complex_types(mock_repo: SQLAlchemyAsyncRepository[Any]) -> None:
    """Test that complex types must use IN() operator."""
    # Test mock PostgreSQL Range
    ranges = [MockPostgreSQLRange(1, 10), MockPostgreSQLRange(20, 30)]
    result = mock_repo._type_must_use_in_instead_of_any(ranges)
    assert result is True

    # Test custom complex type
    complex_types = [MockComplexType("test")]
    result = mock_repo._type_must_use_in_instead_of_any(complex_types)
    assert result is True


async def test_type_must_use_in_mixed_types_with_complex(mock_repo: SQLAlchemyAsyncRepository[Any]) -> None:
    """Test that mixed types containing complex types use IN() operator."""
    mixed_values = [1, "test", MockComplexType("complex")]
    result = mock_repo._type_must_use_in_instead_of_any(mixed_values)
    assert result is True


async def test_type_must_use_in_none_values_ignored(mock_repo: SQLAlchemyAsyncRepository[Any]) -> None:
    """Test that None values are properly ignored."""
    values_with_none = [1, None, 3]
    result = mock_repo._type_must_use_in_instead_of_any(values_with_none)
    assert result is False

    # Test only None values
    only_none = [None, None]
    result = mock_repo._type_must_use_in_instead_of_any(only_none)
    assert result is False


async def test_type_must_use_in_sqlalchemy_type_matching(mock_repo: SQLAlchemyAsyncRepository[Any]) -> None:
    """Test SQLAlchemy type introspection with matching types."""
    # Test Integer type with integer values
    int_type = Integer()
    result = mock_repo._type_must_use_in_instead_of_any([1, 2, 3], int_type)
    assert result is False

    # Test String type with string values
    str_type = String()
    result = mock_repo._type_must_use_in_instead_of_any(["a", "b"], str_type)
    assert result is False


async def test_type_must_use_in_sqlalchemy_type_mismatched(mock_repo: SQLAlchemyAsyncRepository[Any]) -> None:
    """Test SQLAlchemy type introspection with mismatched types."""
    # Test Integer type with string values (mismatch)
    int_type = Integer()
    result = mock_repo._type_must_use_in_instead_of_any(["not_an_int"], int_type)
    assert result is True

    # Test String type with integer values (mismatch)
    str_type = String()
    result = mock_repo._type_must_use_in_instead_of_any([123], str_type)
    assert result is True


async def test_type_must_use_in_sqlalchemy_type_without_python_type(mock_repo: SQLAlchemyAsyncRepository[Any]) -> None:
    """Test SQLAlchemy type that doesn't implement python_type."""
    mock_type: MockTypeWithoutPythonType = MockTypeWithoutPythonType()
    result = mock_repo._type_must_use_in_instead_of_any([1, 2, 3], mock_type)
    assert result is True  # Should use IN() for safety


async def test_type_must_use_in_sqlalchemy_type_with_none_python_type(
    mock_repo: SQLAlchemyAsyncRepository[Any],
) -> None:
    """Test SQLAlchemy type that has None as python_type."""
    mock_type = MagicMock()
    mock_type.python_type = None

    # Should fall back to Python type checking
    result = mock_repo._type_must_use_in_instead_of_any([1, 2, 3], mock_type)
    assert result is False  # Standard integers should use ANY()

    result = mock_repo._type_must_use_in_instead_of_any([MockComplexType("test")], mock_type)
    assert result is True  # Complex types should use IN()


async def test_type_must_use_in_missing_python_type_attribute(mock_repo: SQLAlchemyAsyncRepository[Any]) -> None:
    """Test fallback when python_type attribute is missing from type."""
    # Create a mock that doesn't have python_type attribute at all
    mock_type = type("MockType", (), {})()  # Empty object with no attributes

    result = mock_repo._type_must_use_in_instead_of_any([1, 2, 3], mock_type)
    assert result is False  # Should fall back to Python type checking for safe types


class MyModel(BaseModel):
    name: str
    age: int


class MyStruct(Struct):
    name: str
    age: int


def test_is_pydantic_model() -> None:
    pydantic_model = MyModel(name="Pydantic John", age=30)
    msgspec_struct = MyStruct(name="Msgspec Joe", age=30)
    old_dict = {"name": "Old Greg", "age": 30}
    int_value = 1

    assert is_pydantic_model(pydantic_model)
    assert not is_pydantic_model(msgspec_struct)
    assert not is_pydantic_model(old_dict)
    assert not is_pydantic_model(int_value)


def test_is_msgspec_struct() -> None:
    pydantic_model = MyModel(name="Pydantic John", age=30)
    msgspec_struct = MyStruct(name="Msgspec Joe", age=30)
    old_dict = {"name": "Old Greg", "age": 30}

    assert not is_msgspec_struct(pydantic_model)
    assert is_msgspec_struct(msgspec_struct)
    assert not is_msgspec_struct(old_dict)


def test_is_schema() -> None:
    pydantic_model = MyModel(name="Pydantic John", age=30)
    msgspec_struct = MyStruct(name="Msgspec Joe", age=30)
    old_dict = {"name": "Old Greg", "age": 30}
    int_value = 1
    assert is_schema(pydantic_model)
    assert is_schema(msgspec_struct)
    assert not is_schema(old_dict)
    assert not is_schema(int_value)
    assert is_schema_with_field(pydantic_model, "name")
    assert not is_schema_with_field(msgspec_struct, "name2")
    assert is_schema_without_field(pydantic_model, "name2")
    assert not is_schema_without_field(msgspec_struct, "name")


def test_is_schema_or_dict() -> None:
    pydantic_model = MyModel(name="Pydantic John", age=30)
    msgspec_struct = MyStruct(name="Msgspec Joe", age=30)
    old_dict = {"name": "Old Greg", "age": 30}
    int_value = 1
    assert is_schema_or_dict(pydantic_model)
    assert is_schema_or_dict(msgspec_struct)
    assert is_schema_or_dict(old_dict)
    assert not is_schema_or_dict(int_value)
    assert is_schema_or_dict_with_field(pydantic_model, "name")
    assert not is_schema_or_dict_with_field(msgspec_struct, "name2")
    assert is_schema_or_dict_without_field(pydantic_model, "name2")
    assert not is_schema_or_dict_without_field(msgspec_struct, "name")


# Tests for new methods added in id-attribute-update branch


def test_async_type_must_use_in_empty_values(mock_repo: SQLAlchemyAsyncRepository[Any]) -> None:
    """Test that empty values return False."""
    assert mock_repo._type_must_use_in_instead_of_any([]) is False


def test_sync_type_must_use_in_empty_values(sync_mock_repo: SQLAlchemySyncRepository[Any]) -> None:
    """Test that empty values return False."""
    assert sync_mock_repo._type_must_use_in_instead_of_any([]) is False


def test_async_safe_types_with_field_type(mock_repo: SQLAlchemyAsyncRepository[Any]) -> None:
    """Test safe types with valid field type."""
    # Mock field type with python_type
    mock_field_type = MagicMock()
    mock_field_type.python_type = str

    values = ["test", "another_string"]
    result = mock_repo._type_must_use_in_instead_of_any(values, mock_field_type)
    assert result is False


def test_sync_type_mismatch_with_field_type(sync_mock_repo: SQLAlchemySyncRepository[Any]) -> None:
    """Test type mismatch triggers IN() usage."""
    # Mock field type expecting strings
    mock_field_type = MagicMock()
    mock_field_type.python_type = str

    # Pass integers when expecting strings
    values = [1, 2, 3]
    result = sync_mock_repo._type_must_use_in_instead_of_any(values, mock_field_type)
    assert result is True


def test_async_field_type_none_python_type(mock_repo: SQLAlchemyAsyncRepository[Any]) -> None:
    """Test behavior when field_type.python_type is None."""
    mock_field_type = MagicMock()
    mock_field_type.python_type = None

    values = [{"complex": "object"}]  # Non-safe type
    result = mock_repo._type_must_use_in_instead_of_any(values, mock_field_type)
    assert result is True  # Should use fallback logic


def test_sync_field_type_no_python_type_attr(sync_mock_repo: SQLAlchemySyncRepository[Any]) -> None:
    """Test behavior when field_type has no python_type attribute."""
    # Create object without python_type attribute
    mock_field_type = object()

    values = [{"complex": "object"}]  # Non-safe type
    result = sync_mock_repo._type_must_use_in_instead_of_any(values, mock_field_type)
    assert result is True  # Should use fallback logic for non-safe types


def test_async_no_field_type_safe_values(mock_repo: SQLAlchemyAsyncRepository[Any]) -> None:
    """Test safe values without field type information."""
    # Test all safe types
    safe_values = [
        42,
        3.14,
        "string",
        True,
        b"bytes",
        decimal.Decimal("10.5"),
        datetime.date.today(),
        datetime.datetime.now(),
        datetime.time(12, 30),
        datetime.timedelta(days=1),
    ]

    result = mock_repo._type_must_use_in_instead_of_any(safe_values)
    assert result is False


def test_sync_no_field_type_unsafe_values(sync_mock_repo: SQLAlchemySyncRepository[Any]) -> None:
    """Test unsafe values without field type information."""
    # Test unsafe types (complex objects)
    unsafe_values = [{"key": "value"}, [1, 2, 3], {"nested": {"data": True}}]

    result = sync_mock_repo._type_must_use_in_instead_of_any(unsafe_values)
    assert result is True


def test_async_mixed_safe_unsafe_values(mock_repo: SQLAlchemyAsyncRepository[Any]) -> None:
    """Test mixed safe and unsafe values."""
    # Mix safe and unsafe types
    mixed_values = ["string", 42, {"unsafe": "dict"}]

    result = mock_repo._type_must_use_in_instead_of_any(mixed_values)
    assert result is True


def test_sync_none_values_handling(sync_mock_repo: SQLAlchemySyncRepository[Any]) -> None:
    """Test handling of None values."""
    # None values should be ignored in type checking
    values_with_none = [None, "string", None, 42]

    result = sync_mock_repo._type_must_use_in_instead_of_any(values_with_none)
    assert result is False


def test_async_empty_values(mock_repo: SQLAlchemyAsyncRepository[Any]) -> None:
    """Test empty list returns empty list."""
    result = mock_repo._get_unique_values([])
    assert result == []


def test_sync_hashable_values(sync_mock_repo: SQLAlchemySyncRepository[Any]) -> None:
    """Test hashable values deduplication."""
    values = [1, 2, 1, 3, 2, 4]
    result = sync_mock_repo._get_unique_values(values)
    assert result == [1, 2, 3, 4]


def test_async_string_values(mock_repo: SQLAlchemyAsyncRepository[Any]) -> None:
    """Test string deduplication."""
    values = ["a", "b", "a", "c", "b"]
    result = mock_repo._get_unique_values(values)
    assert result == ["a", "b", "c"]


def test_sync_unhashable_values(sync_mock_repo: SQLAlchemySyncRepository[Any]) -> None:
    """Test unhashable values (dicts) deduplication."""
    values = [
        {"key": "value1"},
        {"key": "value2"},
        {"key": "value1"},  # duplicate
        {"key": "value3"},
    ]
    result = sync_mock_repo._get_unique_values(values)
    expected = [{"key": "value1"}, {"key": "value2"}, {"key": "value3"}]
    assert result == expected


def test_async_mixed_types(mock_repo: SQLAlchemyAsyncRepository[Any]) -> None:
    """Test mixed hashable and unhashable types."""
    # Mix strings and dicts to trigger TypeError in set operations
    values = ["string", {"dict": "value"}, "string", {"other": "dict"}]
    result = mock_repo._get_unique_values(values)
    expected = ["string", {"dict": "value"}, {"other": "dict"}]
    assert result == expected


def test_sync_preserves_order(sync_mock_repo: SQLAlchemySyncRepository[Any]) -> None:
    """Test that order is preserved in deduplication."""
    values = [3, 1, 4, 1, 5, 9, 2, 6, 5, 3]
    result = sync_mock_repo._get_unique_values(values)
    assert result == [3, 1, 4, 5, 9, 2, 6]


def test_column_with_python_default() -> None:
    """Test column with Python-side default."""
    mock_column = MagicMock()
    mock_column.default = "default_value"
    mock_column.server_default = None
    mock_column.onupdate = None
    mock_column.server_onupdate = None

    assert column_has_defaults(mock_column) is True


def test_column_with_server_default() -> None:
    """Test column with server-side default."""
    mock_column = MagicMock()
    mock_column.default = None
    mock_column.server_default = "DEFAULT VALUE"
    mock_column.onupdate = None
    mock_column.server_onupdate = None

    assert column_has_defaults(mock_column) is True


def test_column_with_python_onupdate() -> None:
    """Test column with Python-side onupdate."""
    mock_column = MagicMock()
    mock_column.default = None
    mock_column.server_default = None
    mock_column.onupdate = "update_function"
    mock_column.server_onupdate = None

    assert column_has_defaults(mock_column) is True


def test_column_with_server_onupdate() -> None:
    """Test column with server-side onupdate."""
    mock_column = MagicMock()
    mock_column.default = None
    mock_column.server_default = None
    mock_column.onupdate = None
    mock_column.server_onupdate = "UPDATE_FUNCTION"

    assert column_has_defaults(mock_column) is True


def test_column_with_no_defaults() -> None:
    """Test column with no defaults."""
    mock_column = MagicMock()
    mock_column.default = None
    mock_column.server_default = None
    mock_column.onupdate = None
    mock_column.server_onupdate = None

    assert column_has_defaults(mock_column) is False


def test_column_with_false_default() -> None:
    """Test column where default is False (falsy but not None)."""
    mock_column = MagicMock()
    mock_column.default = False  # Falsy but not None
    mock_column.server_default = None
    mock_column.onupdate = None
    mock_column.server_onupdate = None

    assert column_has_defaults(mock_column) is True


def test_column_with_zero_default() -> None:
    """Test column where default is 0 (falsy but not None)."""
    mock_column = MagicMock()
    mock_column.default = 0  # Falsy but not None
    mock_column.server_default = None
    mock_column.onupdate = None
    mock_column.server_onupdate = None

    assert column_has_defaults(mock_column) is True


def test_column_with_empty_string_default() -> None:
    """Test column where default is empty string (falsy but not None)."""
    mock_column = MagicMock()
    mock_column.default = ""  # Falsy but not None
    mock_column.server_default = None
    mock_column.onupdate = None
    mock_column.server_onupdate = None

    assert column_has_defaults(mock_column) is True
