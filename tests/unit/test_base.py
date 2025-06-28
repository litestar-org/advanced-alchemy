# pyright: reportUnusedImport=false
from __future__ import annotations

import warnings

from tests.helpers import purge_module


def test_deprecated_classes_functionality() -> None:
    """Test that mixins classes maintain have base functionality."""
    purge_module(["advanced_alchemy.base", "advanced_alchemy.mixins"], __file__)

    warnings.filterwarnings("ignore", category=DeprecationWarning)
    from sqlalchemy import exc as sa_exc

    warnings.filterwarnings("ignore", category=sa_exc.SAWarning)

    # Test instantiation and basic attributes
    from advanced_alchemy.mixins import (
        AuditColumns,
        NanoIDPrimaryKey,
        UUIDPrimaryKey,
        UUIDv6PrimaryKey,
        UUIDv7PrimaryKey,
    )

    uuidv7_pk = UUIDv7PrimaryKey()
    uuidv6_pk = UUIDv6PrimaryKey()
    uuid_pk = UUIDPrimaryKey()
    nanoid_pk = NanoIDPrimaryKey()
    audit = AuditColumns()

    # Verify the classes have the expected attributes
    assert hasattr(uuidv7_pk, "id")
    assert hasattr(uuidv7_pk, "_sentinel")
    assert hasattr(uuidv6_pk, "id")
    assert hasattr(uuidv6_pk, "_sentinel")
    assert hasattr(uuid_pk, "id")
    assert hasattr(uuid_pk, "_sentinel")
    assert hasattr(nanoid_pk, "id")
    assert hasattr(nanoid_pk, "_sentinel")
    assert hasattr(audit, "created_at")
    assert hasattr(audit, "updated_at")
