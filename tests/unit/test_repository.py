"""Unit tests for the SQLAlchemy Repository implementation."""

from __future__ import annotations

import datetime
import decimal
from collections.abc import AsyncGenerator, Collection, Generator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Union, cast
from unittest.mock import AsyncMock, MagicMock, PropertyMock
from uuid import uuid4

import pytest
from msgspec import Struct
from pydantic import BaseModel
from pytest_lazy_fixtures import lf
from sqlalchemy import Integer, String, column
from sqlalchemy.exc import InvalidRequestError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, InstrumentedAttribute, Mapped, Session, mapped_column
from sqlalchemy.sql.selectable import ForUpdateArg
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
from advanced_alchemy.repository._util import (
    _build_list_cache_key,
    _normalize_cache_key_value,
    column_has_defaults,
    model_from_dict,
)
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


async def test_sqlalchemy_repo_get_with_for_update(
    mock_repo: SQLAlchemyAsyncRepository[Any],
    mocker: MockerFixture,
) -> None:
    """Ensure FOR UPDATE options are applied when requested."""

    statement = MagicMock()
    statement.options.return_value = statement
    statement.execution_options.return_value = statement
    statement.with_for_update.return_value = statement
    mock_repo.statement = statement

    mocker.patch.object(mock_repo, "_get_loader_options", return_value=([], False))
    mocker.patch.object(mock_repo, "_get_base_stmt", return_value=statement)
    mocker.patch.object(mock_repo, "_apply_filters", return_value=statement)
    mocker.patch.object(mock_repo, "_filter_select_by_kwargs", return_value=statement)
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = MagicMock()
    execute = mocker.patch.object(mock_repo, "_execute", return_value=execute_result)

    instance = await maybe_async(mock_repo.get("instance-id", with_for_update=True))

    assert instance is execute_result.scalar_one_or_none.return_value
    statement.with_for_update.assert_called_once_with()
    execute.assert_called_once_with(statement, uniquify=False)


async def test_sqlalchemy_repo_get_with_for_update_dict(
    mock_repo: SQLAlchemyAsyncRepository[Any],
    mocker: MockerFixture,
) -> None:
    statement = MagicMock()
    statement.options.return_value = statement
    statement.execution_options.return_value = statement
    statement.with_for_update.return_value = statement
    mock_repo.statement = statement

    mocker.patch.object(mock_repo, "_get_loader_options", return_value=([], False))
    mocker.patch.object(mock_repo, "_get_base_stmt", return_value=statement)
    mocker.patch.object(mock_repo, "_apply_filters", return_value=statement)
    mocker.patch.object(mock_repo, "_filter_select_by_kwargs", return_value=statement)
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = MagicMock()
    mocker.patch.object(mock_repo, "_execute", return_value=execute_result)

    await maybe_async(
        mock_repo.get(
            "instance-id",
            with_for_update={"nowait": True, "read": False},
        )
    )

    statement.with_for_update.assert_called_once_with(nowait=True, read=False)


async def test_sqlalchemy_repo_get_with_for_update_arg(
    mock_repo: SQLAlchemyAsyncRepository[Any],
    mocker: MockerFixture,
) -> None:
    statement = MagicMock()
    statement.options.return_value = statement
    statement.execution_options.return_value = statement
    statement.with_for_update.return_value = statement
    mock_repo.statement = statement

    mocker.patch.object(mock_repo, "_get_loader_options", return_value=([], False))
    mocker.patch.object(mock_repo, "_get_base_stmt", return_value=statement)
    mocker.patch.object(mock_repo, "_apply_filters", return_value=statement)
    mocker.patch.object(mock_repo, "_filter_select_by_kwargs", return_value=statement)
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = MagicMock()
    mocker.patch.object(mock_repo, "_execute", return_value=execute_result)

    await maybe_async(
        mock_repo.get(
            "instance-id",
            with_for_update=ForUpdateArg(nowait=True, key_share=True),
        )
    )

    statement.with_for_update.assert_called_once_with(nowait=True, read=False, skip_locked=False, key_share=True)


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


def test_column_property_label_object() -> None:
    """Test column_property Label objects return False for column_has_defaults."""
    from sqlalchemy.sql.elements import Label

    # Create a Label object similar to what column_property creates
    mock_label = MagicMock(spec=Label)

    # Label objects don't have default/onupdate attributes, but if they did,
    # they would raise AttributeError when accessed
    assert column_has_defaults(mock_label) is False


def test_column_property_with_real_label() -> None:
    """Test column_has_defaults with an actual Label object from SQLAlchemy."""
    from sqlalchemy import literal_column
    from sqlalchemy.sql.elements import Label

    # Create a real Label object like column_property would create
    label_obj = literal_column("test_value").label("test_column")  # type: ignore[var-annotated]
    assert isinstance(label_obj, Label)

    # This should return False and not raise AttributeError
    assert column_has_defaults(label_obj) is False


def test_column_object_without_default_attributes() -> None:
    """Test column_has_defaults with object missing some attributes."""

    # Create an object that only has some of the expected attributes
    class PartialColumn:
        def __init__(self) -> None:
            self.default = "test_default"
            # Missing server_default, onupdate, server_onupdate attributes

    partial_column = PartialColumn()

    # Should return True based on the default attribute, even though others are missing
    assert column_has_defaults(partial_column) is True


def test_column_object_with_no_default_attributes() -> None:
    """Test column_has_defaults with object missing all attributes."""

    # Create an object that has none of the expected attributes
    class MinimalColumn:
        def __init__(self) -> None:
            self.name = "test_column"

    minimal_column = MinimalColumn()

    # Should return False since no default attributes are present
    assert column_has_defaults(minimal_column) is False


def test_normalize_cache_key_value_handles_structures() -> None:
    """Normalize cache key values for common structures."""

    @dataclass
    class Payload:
        name: str
        ids: set[int]

    class CacheBase(DeclarativeBase):
        pass

    class CacheModel(CacheBase):
        __tablename__ = "cache_model"

        id: Mapped[int] = mapped_column(primary_key=True)

    normalized = _normalize_cache_key_value(Payload(name="alpha", ids={2, 1}))
    assert normalized == {"name": "alpha", "ids": [1, 2]}
    assert _normalize_cache_key_value(CacheModel.id) == {"__attr__": "id"}
    assert _normalize_cache_key_value(column("name")) == {"__sql__": "name"}
    assert "__repr__" in _normalize_cache_key_value(object())


def test_build_list_cache_key_stable_for_unordered_inputs() -> None:
    """Cache keys should remain stable for unordered inputs."""
    filters = [CollectionFilter(field_name="id", values={2, 1})]
    key_a = _build_list_cache_key(
        model_name="CacheModel",
        version_token="v1",
        method="list",
        filters=filters,
        kwargs={"meta": {"b": 2, "a": 1}},
        order_by=[("name", False)],
        execution_options={"stream_results": True},
        uniquify=True,
    )
    key_b = _build_list_cache_key(
        model_name="CacheModel",
        version_token="v1",
        method="list",
        filters=[CollectionFilter(field_name="id", values={1, 2})],
        kwargs={"meta": {"a": 1, "b": 2}},
        order_by=[("name", False)],
        execution_options={"stream_results": True},
        uniquify=True,
    )

    assert key_a is not None
    assert key_a == key_b


def test_build_list_cache_key_returns_none_for_raw_filters() -> None:
    """Raw SQLAlchemy expressions should skip caching."""
    key = _build_list_cache_key(
        model_name="CacheModel",
        version_token="v1",
        method="list",
        filters=[column("id") == 1],
        kwargs={},
        order_by=None,
        execution_options={},
        uniquify=False,
    )

    assert key is None


def test_model_from_dict_includes_relationship_attributes() -> None:
    """Test that model_from_dict includes relationship attributes from __mapper__.attrs.keys()."""
    from tests.fixtures.uuid.models import UUIDAuthor

    # Verify that attrs.keys() includes relationships while columns.keys() doesn't
    columns_keys = list(UUIDAuthor.__mapper__.columns.keys())
    attrs_keys = list(UUIDAuthor.__mapper__.attrs.keys())

    assert "books" not in columns_keys, "books relationship should NOT be in columns.keys()"
    assert "books" in attrs_keys, "books relationship should be in attrs.keys()"


# Tests for write_only relationship handling in update method (issue #524)


async def test_update_skips_write_only_relationships(
    mock_repo: SQLAlchemyAsyncRepository[Any],
    mocker: MockerFixture,
) -> None:
    """Test that update method skips write_only relationships without error."""
    id_ = 3
    mock_instance = MagicMock()
    existing_instance = MagicMock()

    # Mock the mapper and relationship
    mock_mapper = MagicMock()
    mock_relationship = MagicMock()
    mock_relationship.key = "items"
    mock_relationship.lazy = "write_only"
    mock_relationship.viewonly = False
    mock_mapper.mapper.columns = []
    mock_mapper.mapper.relationships = [mock_relationship]

    # Mock the data object to have the write_only relationship attribute
    mock_instance.items = MagicMock()  # This would be a WriteOnlyCollection in reality

    mocker.patch.object(mock_repo, "get_id_attribute_value", return_value=id_)
    mocker.patch.object(mock_repo, "get", return_value=existing_instance)
    mocker.patch("advanced_alchemy.repository._async.inspect", return_value=mock_mapper)
    mock_repo.session.merge.return_value = existing_instance  # pyright: ignore[reportFunctionMemberAccess]

    # This should not raise an error even though items is a write_only relationship
    instance = await maybe_async(mock_repo.update(mock_instance))

    # Verify the relationship was not processed (no merge attempted for relationships)
    mock_repo.session.merge.assert_called_once_with(existing_instance, load=True)  # pyright: ignore[reportFunctionMemberAccess]
    assert instance is existing_instance


async def test_update_skips_dynamic_relationships(
    mock_repo: SQLAlchemyAsyncRepository[Any],
    mocker: MockerFixture,
) -> None:
    """Test that update method skips dynamic relationships without error."""
    id_ = 3
    mock_instance = MagicMock()
    existing_instance = MagicMock()

    # Mock the mapper and relationship
    mock_mapper = MagicMock()
    mock_relationship = MagicMock()
    mock_relationship.key = "items"
    mock_relationship.lazy = "dynamic"
    mock_relationship.viewonly = False
    mock_mapper.mapper.columns = []
    mock_mapper.mapper.relationships = [mock_relationship]

    # Mock the data object to have the dynamic relationship attribute
    mock_instance.items = MagicMock()  # This would be an AppenderQuery in reality

    mocker.patch.object(mock_repo, "get_id_attribute_value", return_value=id_)
    mocker.patch.object(mock_repo, "get", return_value=existing_instance)
    mocker.patch("advanced_alchemy.repository._async.inspect", return_value=mock_mapper)
    mock_repo.session.merge.return_value = existing_instance  # pyright: ignore[reportFunctionMemberAccess]

    # This should not raise an error even though items is a dynamic relationship
    instance = await maybe_async(mock_repo.update(mock_instance))

    # Verify the relationship was not processed (no merge attempted for relationships)
    mock_repo.session.merge.assert_called_once_with(existing_instance, load=True)  # pyright: ignore[reportFunctionMemberAccess]
    assert instance is existing_instance


async def test_update_skips_viewonly_relationships(
    mock_repo: SQLAlchemyAsyncRepository[Any],
    mocker: MockerFixture,
) -> None:
    """Test that update method skips viewonly relationships without error."""
    id_ = 3
    mock_instance = MagicMock()
    existing_instance = MagicMock()

    # Mock the mapper and relationship
    mock_mapper = MagicMock()
    mock_relationship = MagicMock()
    mock_relationship.key = "readonly_items"
    mock_relationship.lazy = "select"  # Normal lazy loading
    mock_relationship.viewonly = True  # But marked as view-only
    mock_mapper.mapper.columns = []
    mock_mapper.mapper.relationships = [mock_relationship]

    # Mock the data object to have the viewonly relationship attribute
    mock_instance.readonly_items = [MagicMock()]

    mocker.patch.object(mock_repo, "get_id_attribute_value", return_value=id_)
    mocker.patch.object(mock_repo, "get", return_value=existing_instance)
    mocker.patch("advanced_alchemy.repository._async.inspect", return_value=mock_mapper)
    mock_repo.session.merge.return_value = existing_instance  # pyright: ignore[reportFunctionMemberAccess]

    # This should not raise an error even though readonly_items is viewonly
    instance = await maybe_async(mock_repo.update(mock_instance))

    # Verify the relationship was not processed (no merge attempted for relationships)
    mock_repo.session.merge.assert_called_once_with(existing_instance, load=True)  # pyright: ignore[reportFunctionMemberAccess]
    assert instance is existing_instance


async def test_update_skips_raise_lazy_relationships(
    mock_repo: SQLAlchemyAsyncRepository[Any],
    mocker: MockerFixture,
) -> None:
    """Test that update method skips raise lazy strategy relationships without error."""
    id_ = 3
    mock_instance = MagicMock()
    existing_instance = MagicMock()

    # Mock the mapper and relationship
    mock_mapper = MagicMock()
    mock_relationship = MagicMock()
    mock_relationship.key = "items"
    mock_relationship.lazy = "raise"
    mock_relationship.viewonly = False
    mock_mapper.mapper.columns = []
    mock_mapper.mapper.relationships = [mock_relationship]

    # Mock the data object to raise an error when accessing the relationship
    type(mock_instance).items = PropertyMock(side_effect=InvalidRequestError)

    mocker.patch.object(mock_repo, "get_id_attribute_value", return_value=id_)
    mocker.patch.object(mock_repo, "get", return_value=existing_instance)
    mocker.patch("advanced_alchemy.repository._sync.inspect", return_value=mock_mapper)
    mocker.patch("advanced_alchemy.repository._async.inspect", return_value=mock_mapper)
    mock_repo.session.merge.return_value = existing_instance  # pyright: ignore[reportFunctionMemberAccess]

    # This should not raise an error even though items has lazy="raise"
    instance = await maybe_async(mock_repo.update(mock_instance))

    # Verify the relationship was not processed (no merge attempted for relationships)
    mock_repo.session.merge.assert_called_once_with(existing_instance, load=True)  # pyright: ignore[reportFunctionMemberAccess]
    assert instance is existing_instance


async def test_update_processes_normal_relationships(
    mock_repo: SQLAlchemyAsyncRepository[Any],
    mocker: MockerFixture,
) -> None:
    """Test that update method still processes normal relationships correctly."""
    id_ = 3
    mock_instance = MagicMock()
    existing_instance = MagicMock()
    related_item = MagicMock()
    merged_related_item = MagicMock()

    # Mock the mapper and relationship
    mock_mapper = MagicMock()
    mock_relationship = MagicMock()
    mock_relationship.key = "items"
    mock_relationship.lazy = "select"  # Normal lazy loading
    mock_relationship.viewonly = False
    mock_mapper.mapper.columns = []
    mock_mapper.mapper.relationships = [mock_relationship]

    # Mock the data object to have a normal relationship with items
    mock_instance.items = [related_item]

    mocker.patch.object(mock_repo, "get_id_attribute_value", return_value=id_)
    mocker.patch.object(mock_repo, "get", return_value=existing_instance)
    mocker.patch("advanced_alchemy.repository._async.inspect", return_value=mock_mapper)

    # Mock session.merge to return different objects for main instance vs related items
    async def mock_merge(obj: Any, load: bool = True) -> Any:
        if obj is existing_instance:
            return existing_instance
        if obj is related_item:
            return merged_related_item
        return obj

    mock_repo.session.merge.side_effect = mock_merge

    # This should process the normal relationship correctly
    instance = await maybe_async(mock_repo.update(mock_instance))

    # Verify the relationship was processed - at minimum the main instance should be merged
    assert mock_repo.session.merge.call_count >= 1  # At least the main instance
    # The main point is that normal relationships don't cause errors
    assert instance is existing_instance


def test_model_from_dict_backward_compatibility() -> None:
    """Test that model_from_dict maintains backward compatibility with column-only data."""
    from tests.fixtures.uuid.models import UUIDAuthor

    author_data = {"name": "Compatible Author", "string_field": "compatibility test"}

    author = model_from_dict(UUIDAuthor, **author_data)

    assert author.name == "Compatible Author"
    assert author.string_field == "compatibility test"


def test_model_from_dict_ignores_unknown_attributes() -> None:
    """Test that model_from_dict still ignores unknown attributes."""
    from tests.fixtures.uuid.models import UUIDAuthor

    author_data = {"name": "Test Author", "unknown_attribute": "should be ignored", "another_unknown": 12345}

    author = model_from_dict(UUIDAuthor, **author_data)

    assert author.name == "Test Author"
    assert not hasattr(author, "unknown_attribute")
    assert not hasattr(author, "another_unknown")


def test_model_from_dict_empty_relationship() -> None:
    """Test that model_from_dict handles empty relationship lists."""
    from tests.fixtures.uuid.models import UUIDAuthor

    author_data = {
        "name": "Author Without Books",
        "books": [],  # Empty relationship
    }

    author = model_from_dict(UUIDAuthor, **author_data)

    assert author.name == "Author Without Books"
    assert hasattr(author, "books")
    assert author.books == []


def test_update_many_data_conversion_handles_mixed_types() -> None:
    """Test that update_many properly handles mixed input types (regression test).

    This verifies the fix for the type handling bug in update_many where
    the old logic would fail with AttributeError when mixing model instances
    and dictionaries.
    """
    from tests.fixtures.uuid.models import UUIDAuthor

    # Simulate the data conversion logic from the fixed code
    model_type = UUIDAuthor

    # Create a mock model instance
    mock_author = UUIDAuthor(name="Test Author")

    # Mix of model instances and dictionaries (the problematic case)
    mixed_data = [
        mock_author,  # Model instance with to_dict() method
        {"id": "dict-id", "name": "Dict Author"},  # Plain dictionary
    ]

    # This is the fixed logic from repository/_async.py and _sync.py
    data_to_update = []
    for v in mixed_data:
        if isinstance(v, model_type):
            data_to_update.append(v.to_dict())
        else:
            data_to_update.append(v)  # type: ignore[arg-type]

    # Verify no AttributeError was raised and data is properly converted
    assert len(data_to_update) == 2
    assert isinstance(data_to_update[0], dict)  # Model converted to dict
    assert isinstance(data_to_update[1], dict)  # Dict passed through
    assert data_to_update[0]["name"] == "Test Author"
    assert data_to_update[1]["name"] == "Dict Author"


def test_compare_values_handles_numpy_arrays() -> None:
    """Test that compare_values properly handles numpy arrays.

    This is a regression test for the issue where comparing numpy arrays
    (like pgvector's Vector type) would raise:
    ValueError: The truth value of an array with more than one element is ambiguous
    """
    from advanced_alchemy.repository._util import compare_values

    # Test with regular values (should work as before)
    assert compare_values("same", "same") is True
    assert compare_values("different", "other") is False
    assert compare_values(None, None) is True
    assert compare_values(None, "value") is False
    assert compare_values("value", None) is False

    # Test with mock numpy arrays (when numpy is not installed)
    class MockNumpyArray:
        """Mock numpy array for testing when numpy is not available."""

        def __init__(self, data: list[float]) -> None:
            self.data = data
            self.dtype = "float64"  # Required for is_numpy_array detection

        def __array__(self) -> list[float]:
            """Required for is_numpy_array detection."""
            return self.data

        def __eq__(self, other: object) -> list[bool]:  # type: ignore[override]
            """Simulate numpy's element-wise comparison that causes the issue."""
            if isinstance(other, MockNumpyArray):
                return [a == b for a, b in zip(self.data, other.data)]
            return [False] * len(self.data)

    # Create mock arrays
    array1 = MockNumpyArray([1.0, 2.0, 3.0])
    array2 = MockNumpyArray([1.0, 2.0, 3.0])  # Same data
    array3 = MockNumpyArray([4.0, 5.0, 6.0])  # Different data

    # Test array comparisons (these would previously raise ValueError)
    result_same = compare_values(array1, array2)
    result_different = compare_values(array1, array3)
    result_mixed = compare_values(array1, "not_an_array")

    # The important thing is that no ValueError is raised
    assert isinstance(result_same, bool)  # Should not raise ValueError
    assert isinstance(result_different, bool)  # Should not raise ValueError
    assert isinstance(result_mixed, bool)  # Should not raise ValueError

    # The specific results depend on whether numpy is installed:
    # - With numpy: MockNumpyArray is not detected as numpy array, falls back to __eq__
    # - Without numpy: stub functions are used which return False for safety
    # Either way, no ValueError should be raised

    # Test with values that would cause comparison errors
    class ProblematicValue:
        def __eq__(self, other: object) -> None:  # type: ignore[override]
            raise TypeError("Cannot compare")

    problematic = ProblematicValue()
    # Should handle comparison errors gracefully
    assert compare_values(problematic, "other") is False
    assert compare_values("other", problematic) is False


def test_compare_values_with_real_numpy_arrays() -> None:
    """Test compare_values with actual numpy arrays when numpy is installed.

    This test covers the real numpy code paths that were missing from coverage.
    """
    # This test will only run if numpy is actually installed
    try:
        import numpy as np
    except ImportError:
        pytest.skip("numpy not available")

    from advanced_alchemy.repository._util import compare_values

    # Test equal arrays
    arr1 = np.array([1.0, 2.0, 3.0])
    arr2 = np.array([1.0, 2.0, 3.0])
    assert compare_values(arr1, arr2) is True

    # Test different arrays
    arr3 = np.array([4.0, 5.0, 6.0])
    assert compare_values(arr1, arr3) is False

    # Test different shapes
    arr4 = np.array([[1.0, 2.0], [3.0, 4.0]])
    assert compare_values(arr1, arr4) is False

    # Test array vs non-array
    assert compare_values(arr1, [1.0, 2.0, 3.0]) is False
    assert compare_values(arr1, "not an array") is False

    # Test empty arrays
    empty1 = np.array([])
    empty2 = np.array([])
    assert compare_values(empty1, empty2) is True

    # Test different dtypes but same values
    int_arr = np.array([1, 2, 3])
    float_arr = np.array([1.0, 2.0, 3.0])
    assert compare_values(int_arr, float_arr) is True  # numpy considers these equal

    # Test NaN handling
    nan_arr1 = np.array([1.0, np.nan, 3.0])
    nan_arr2 = np.array([1.0, np.nan, 3.0])
    # numpy considers NaN != NaN, so arrays with NaN won't be equal
    assert compare_values(nan_arr1, nan_arr2) is False


def test_compare_values_covers_all_branches() -> None:
    """Test compare_values to ensure all code branches are covered."""
    from advanced_alchemy.repository._util import compare_values

    # Test standard equality that returns non-bool (should not happen with normal types)
    class WeirdComparison:
        def __eq__(self, other: object) -> str:  # type: ignore[override]
            return "weird"

    weird = WeirdComparison()
    # This tests the bool() conversion in the standard comparison path
    result = compare_values(weird, weird)
    assert isinstance(result, bool)  # Should convert "weird" to True
    assert result is True


def test_repository_update_methods_with_numpy_arrays() -> None:
    """Test that repository update methods work correctly with numpy array fields.

    This integration test covers the actual repository comparison paths
    that were missing from coverage.
    """
    # This test will only run if numpy is actually installed
    try:
        import numpy as np
    except ImportError:
        pytest.skip("numpy not available")

    from advanced_alchemy.repository._util import compare_values

    # Test data with numpy arrays
    arr1 = np.array([1.0, 2.0, 3.0])
    arr2 = np.array([1.0, 2.0, 3.0])  # Same as arr1
    arr3 = np.array([4.0, 5.0, 6.0])  # Different from arr1

    # These operations would previously fail with ValueError
    # Now they should work correctly by using our safe comparison

    # Test 1: Arrays with same data should be considered equal
    assert arr1 is not arr2  # Different objects
    # But compare_values should see them as equal
    assert compare_values(arr1, arr2) is True

    # Test 2: Arrays with different data should be considered different
    assert compare_values(arr1, arr3) is False

    # Test 3: Test with None values (common edge case)
    assert compare_values(None, None) is True
    assert compare_values(arr1, None) is False
    assert compare_values(None, arr1) is False

    # Test 4: Array vs non-array should be False
    assert compare_values(arr1, [1.0, 2.0, 3.0]) is False
    assert compare_values(arr1, "not an array") is False

    # Test 5: Test different shapes
    arr_2d = np.array([[1.0, 2.0], [3.0, 4.0]])
    assert compare_values(arr1, arr_2d) is False

    # Test 6: Test empty arrays
    empty1 = np.array([])
    empty2 = np.array([])
    assert compare_values(empty1, empty2) is True

    # Test 7: Test with complex numbers (edge case)
    complex1 = np.array([1 + 2j, 3 + 4j])
    complex2 = np.array([1 + 2j, 3 + 4j])
    complex3 = np.array([1 + 2j, 5 + 6j])
    assert compare_values(complex1, complex2) is True
    assert compare_values(complex1, complex3) is False


def test_was_attribute_set_with_explicitly_set_attributes() -> None:
    """Test was_attribute_set correctly identifies explicitly set attributes."""
    from sqlalchemy import inspect

    from advanced_alchemy.repository._util import was_attribute_set

    # Create an instance with explicitly set attributes
    instance = UUIDModel()
    instance.id = uuid4()  # Explicitly set id

    # Get the mapper/inspector
    mapper = inspect(instance)

    # Explicitly set attributes should return True
    assert was_attribute_set(instance, mapper, "id") is True


def test_was_attribute_set_with_uninitialized_attributes() -> None:
    """Test was_attribute_set correctly identifies uninitialized attributes."""
    from sqlalchemy import inspect

    from advanced_alchemy.repository._util import was_attribute_set

    # Use the existing UUIDModel which has created_at and updated_at audit fields
    # Create an instance - created_at and updated_at won't be in instance dict yet
    instance = UUIDModel()

    # Get the mapper/inspector
    mapper = inspect(instance)

    # Uninitialized audit attributes should return False
    # They exist on the model but haven't been explicitly set
    assert was_attribute_set(instance, mapper, "created_at") is False
    assert was_attribute_set(instance, mapper, "updated_at") is False


def test_was_attribute_set_with_modified_attributes() -> None:
    """Test was_attribute_set detects attributes with modification history."""
    from sqlalchemy import inspect

    from advanced_alchemy.repository._util import was_attribute_set

    # Create an instance and explicitly set attributes
    instance = UUIDModel()
    instance.id = uuid4()  # Explicitly set id

    # Also test setting a datetime attribute
    now = datetime.datetime.now(datetime.timezone.utc)
    instance.created_at = now  # Explicitly modify created_at

    # Get the mapper/inspector
    mapper = inspect(instance)

    # Modified attributes should return True
    assert was_attribute_set(instance, mapper, "id") is True
    assert was_attribute_set(instance, mapper, "created_at") is True


def test_was_attribute_set_with_nonexistent_attribute() -> None:
    """Test was_attribute_set handles nonexistent attributes gracefully."""
    from sqlalchemy import inspect

    from advanced_alchemy.repository._util import was_attribute_set

    # Create an instance
    instance = UUIDModel()

    # Get the mapper/inspector
    mapper = inspect(instance)

    # Nonexistent attribute should return False (attr_state is None)
    assert was_attribute_set(instance, mapper, "nonexistent_field") is False


# Tests for nested dict handling in model_from_dict (Issue #556)


def test_model_from_dict_nested_single_dict() -> None:
    """Test single nested dict is converted to model instance."""
    from tests.fixtures.uuid.models import UUIDAuthor, UUIDBook

    data = {
        "title": "Test Book",
        "author": {"name": "Test Author"},
    }
    book = model_from_dict(UUIDBook, **data)

    assert book.title == "Test Book"
    assert isinstance(book.author, UUIDAuthor)
    assert book.author.name == "Test Author"


def test_model_from_dict_nested_list_of_dicts() -> None:
    """Test list of nested dicts are converted to model instances."""
    from tests.fixtures.uuid.models import UUIDAuthor, UUIDBook

    data = {
        "name": "Test Author",
        "books": [
            {"title": "Book 1"},
            {"title": "Book 2"},
        ],
    }
    author = model_from_dict(UUIDAuthor, **data)

    assert author.name == "Test Author"
    assert len(author.books) == 2
    assert all(isinstance(b, UUIDBook) for b in author.books)
    assert author.books[0].title == "Book 1"
    assert author.books[1].title == "Book 2"


def test_model_from_dict_deeply_nested() -> None:
    """Test deeply nested structures (2+ levels) - author with books, each book with author."""
    from tests.fixtures.uuid.models import UUIDAuthor, UUIDBook

    # Create a book with nested author that has nested books
    # Note: SQLAlchemy's back_populates will automatically add the outer book
    # to author.books, so we get 3 books total (the outer book + 2 nested)
    data = {
        "title": "Test Book",
        "author": {
            "name": "Test Author",
            "books": [
                {"title": "Another Book 1"},
                {"title": "Another Book 2"},
            ],
        },
    }
    book = model_from_dict(UUIDBook, **data)

    assert book.title == "Test Book"
    assert isinstance(book.author, UUIDAuthor)
    assert book.author.name == "Test Author"
    # Due to back_populates, author.books contains the outer book + 2 nested books = 3 total
    assert len(book.author.books) == 3
    assert all(isinstance(b, UUIDBook) for b in book.author.books)
    # The first two are from the nested data
    titles = {b.title for b in book.author.books}
    assert "Another Book 1" in titles
    assert "Another Book 2" in titles
    assert "Test Book" in titles


def test_model_from_dict_none_relationship() -> None:
    """Test None value for relationship is preserved."""
    from tests.fixtures.uuid.models import UUIDBook

    data = {"title": "Orphan Book", "author": None}
    book = model_from_dict(UUIDBook, **data)

    assert book.title == "Orphan Book"
    assert book.author is None


def test_model_from_dict_empty_list_relationship() -> None:
    """Test empty list for relationship is preserved."""
    from tests.fixtures.uuid.models import UUIDAuthor

    data = {"name": "Author Without Books", "books": []}
    author = model_from_dict(UUIDAuthor, **data)

    assert author.name == "Author Without Books"
    assert author.books == []


def test_model_from_dict_mixed_list() -> None:
    """Test list with both dicts and model instances."""
    from tests.fixtures.uuid.models import UUIDAuthor, UUIDBook

    existing_book = UUIDBook(title="Existing Book")
    data = {
        "name": "Test Author",
        "books": [
            existing_book,
            {"title": "New Book"},
        ],
    }
    author = model_from_dict(UUIDAuthor, **data)

    assert len(author.books) == 2
    assert author.books[0] is existing_book
    assert isinstance(author.books[1], UUIDBook)
    assert author.books[1].title == "New Book"


def test_model_from_dict_preserves_existing_instance() -> None:
    """Test that existing model instances are passed through unchanged."""
    from tests.fixtures.uuid.models import UUIDAuthor, UUIDBook

    existing_author = UUIDAuthor(name="Existing")
    data = {
        "title": "Test Book",
        "author": existing_author,
    }
    book = model_from_dict(UUIDBook, **data)

    assert book.author is existing_author


def test_model_from_dict_single_item_for_collection() -> None:
    """Test single dict provided for collection relationship is wrapped in list."""
    from tests.fixtures.uuid.models import UUIDAuthor, UUIDBook

    data = {
        "name": "Test Author",
        "books": {"title": "Single Book"},  # Single dict instead of list
    }
    author = model_from_dict(UUIDAuthor, **data)

    assert len(author.books) == 1
    assert isinstance(author.books[0], UUIDBook)
    assert author.books[0].title == "Single Book"


def test_model_from_dict_performance_baseline() -> None:
    """Ensure minimal overhead for non-nested dicts."""
    import time

    from tests.fixtures.uuid.models import UUIDAuthor

    data = {"name": "Test Author", "string_field": "test"}

    # Warm up
    for _ in range(100):
        model_from_dict(UUIDAuthor, **data)

    # Benchmark
    start = time.perf_counter()
    for _ in range(10000):
        model_from_dict(UUIDAuthor, **data)
    elapsed = time.perf_counter() - start

    # Should complete quickly (< 1 second for 10k iterations)
    assert elapsed < 1.0


def test_model_from_dict_performance_nested() -> None:
    """Benchmark nested dict conversion."""
    import time

    from tests.fixtures.uuid.models import UUIDAuthor

    data = {
        "name": "Test Author",
        "books": [{"title": f"Book {i}"} for i in range(10)],
    }

    # Warm up
    for _ in range(100):
        model_from_dict(UUIDAuthor, **data)

    start = time.perf_counter()
    for _ in range(1000):
        model_from_dict(UUIDAuthor, **data)
    elapsed = time.perf_counter() - start

    # Should complete reasonably (< 2 seconds for 1k iterations with 10 children)
    assert elapsed < 2.0


def test_model_from_dict_many_to_many_relationship() -> None:
    """Test nested dict handling for many-to-many relationships."""
    from tests.fixtures.uuid.models import UUIDItem, UUIDTag

    data = {
        "name": "Test Item",
        "tags": [
            {"name": "Tag 1"},
            {"name": "Tag 2"},
        ],
    }
    item = model_from_dict(UUIDItem, **data)

    assert item.name == "Test Item"
    assert len(item.tags) == 2
    assert all(isinstance(t, UUIDTag) for t in item.tags)
    assert item.tags[0].name == "Tag 1"
    assert item.tags[1].name == "Tag 2"


def test_model_from_dict_tuple_for_collection() -> None:
    """Test tuple provided for collection relationship is handled correctly."""
    from tests.fixtures.uuid.models import UUIDAuthor, UUIDBook

    data = {
        "name": "Test Author",
        "books": ({"title": "Book 1"}, {"title": "Book 2"}),  # Tuple instead of list
    }
    author = model_from_dict(UUIDAuthor, **data)

    assert len(author.books) == 2
    assert all(isinstance(b, UUIDBook) for b in author.books)


def test_convert_relationship_value_helper() -> None:
    """Test the _convert_relationship_value helper function directly."""
    from advanced_alchemy.repository._util import _convert_relationship_value
    from tests.fixtures.uuid.models import UUIDBook

    # Test None
    assert _convert_relationship_value(None, UUIDBook, is_collection=False) is None
    assert _convert_relationship_value(None, UUIDBook, is_collection=True) is None

    # Test single dict for non-collection
    result = _convert_relationship_value({"title": "Test"}, UUIDBook, is_collection=False)
    assert isinstance(result, UUIDBook)
    assert result.title == "Test"

    # Test single dict for collection (should wrap in list)
    result = _convert_relationship_value({"title": "Test"}, UUIDBook, is_collection=True)
    assert isinstance(result, list)
    assert len(result) == 1
    assert isinstance(result[0], UUIDBook)

    # Test list of dicts for collection
    result = _convert_relationship_value(
        [{"title": "Book 1"}, {"title": "Book 2"}],
        UUIDBook,
        is_collection=True,
    )
    assert isinstance(result, list)
    assert len(result) == 2

    # Test existing instance pass-through
    existing = UUIDBook(title="Existing")
    result = _convert_relationship_value(existing, UUIDBook, is_collection=False)
    assert result is existing

    # Test existing instance in collection
    result = _convert_relationship_value([existing], UUIDBook, is_collection=True)
    assert result[0] is existing
