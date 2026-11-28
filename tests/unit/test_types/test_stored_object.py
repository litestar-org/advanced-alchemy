"""Unit tests for the StoredObject column type."""

from typing import Any
from unittest.mock import Mock

import pytest
from alembic.autogenerate import render_python_code
from alembic.operations.ops import AddColumnOp, UpgradeOps
from sqlalchemy import Column, Integer, MetaData, Table

from advanced_alchemy.exceptions import ImproperConfigurationError
from advanced_alchemy.types.file_object import StoredObject, storages
from advanced_alchemy.types.file_object.base import StorageBackend

UNREGISTERED_KEY = "unregistered-stored-object-key"


@pytest.fixture(autouse=True)
def _assert_key_unregistered() -> None:
    assert not storages.is_registered(UNREGISTERED_KEY)


@pytest.mark.parametrize(
    ("multiple", "expected"),
    [
        (False, f"StoredObject(backend='{UNREGISTERED_KEY}')"),
        (True, f"StoredObject(backend='{UNREGISTERED_KEY}', multiple=True)"),
    ],
)
def test_stored_object_repr_without_registered_backend(multiple: bool, expected: str) -> None:
    assert repr(StoredObject(backend=UNREGISTERED_KEY, multiple=multiple)) == expected


def test_stored_object_storage_key_without_registered_backend() -> None:
    assert StoredObject(backend=UNREGISTERED_KEY).storage_key == UNREGISTERED_KEY


def test_stored_object_backend_still_resolves_lazily() -> None:
    with pytest.raises(ImproperConfigurationError):
        _ = StoredObject(backend=UNREGISTERED_KEY).backend


def test_stored_object_key_from_backend_instance() -> None:
    backend = Mock(spec=StorageBackend)
    backend.key = "instance_key"
    stored = StoredObject(backend=backend, multiple=True)

    assert stored.storage_key == "instance_key"
    assert repr(stored) == "StoredObject(backend='instance_key', multiple=True)"


@pytest.mark.parametrize("multiple", [False, True])
def test_stored_object_repr_round_trips(multiple: bool) -> None:
    rebuilt = eval(repr(StoredObject(backend=UNREGISTERED_KEY, multiple=multiple)), {"StoredObject": StoredObject})

    assert isinstance(rebuilt, StoredObject)
    assert rebuilt.storage_key == UNREGISTERED_KEY
    assert rebuilt.multiple is multiple


def test_stored_object_column_and_table_repr_without_registered_backend() -> None:
    column: Column[Any] = Column("attachment", StoredObject(backend=UNREGISTERED_KEY))
    table = Table("document", MetaData(), Column("id", Integer, primary_key=True), column)

    assert f"StoredObject(backend='{UNREGISTERED_KEY}')" in repr(column)
    assert f"StoredObject(backend='{UNREGISTERED_KEY}')" in repr(table)


def test_stored_object_alembic_autogenerate_without_registered_backend() -> None:
    upgrade_ops = UpgradeOps(
        ops=[AddColumnOp("document", Column("attachment", StoredObject(backend=UNREGISTERED_KEY), nullable=True))]
    )

    code = render_python_code(upgrade_ops, user_module_prefix="sa.")

    assert f"sa.StoredObject(backend='{UNREGISTERED_KEY}')" in code
