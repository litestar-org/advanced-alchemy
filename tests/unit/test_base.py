# ruff: noqa: TC004, F401
# pyright: reportUnusedImport=false
from __future__ import annotations

import warnings

import pytest

from tests.helpers import purge_module


def test_deprecated_uuid_primary_keys() -> None:
    """Test that using UUIDv7PrimaryKey from base raises a deprecation warning."""
    purge_module(["advanced_alchemy.base"], __file__)
    with pytest.warns(DeprecationWarning, match="please import it from 'advanced_alchemy.mixins' instead"):
        from advanced_alchemy.base import UUIDv7PrimaryKey

    with pytest.warns(DeprecationWarning, match="please import it from 'advanced_alchemy.mixins' instead"):
        from advanced_alchemy.base import UUIDv6PrimaryKey

    with pytest.warns(DeprecationWarning, match="please import it from 'advanced_alchemy.mixins' instead"):
        from advanced_alchemy.base import UUIDPrimaryKey


def test_deprecated_slug_mixin() -> None:
    """Test that using SlugMixin from base raises a deprecation warning."""
    purge_module(["advanced_alchemy.base", "advanced_alchemy.mixins.slug", "advanced_alchemy.mixins"], __file__)
    with pytest.warns(DeprecationWarning, match="please import it from 'advanced_alchemy.mixins' instead"):
        from advanced_alchemy.base import SlugKey


def test_deprecated_bigint_primary_key() -> None:
    """Test that using BigIntPrimaryKey from base raises a deprecation warning."""
    purge_module(["advanced_alchemy.base", "advanced_alchemy.mixins.bigint", "advanced_alchemy.mixins"], __file__)
    with pytest.warns(DeprecationWarning, match="please import it from 'advanced_alchemy.mixins' instead"):
        from advanced_alchemy.base import BigIntPrimaryKey


def test_deprecated_nanoid_primary_key() -> None:
    """Test that using NanoIDPrimaryKey from base raises a deprecation warning."""
    purge_module(["advanced_alchemy.base", "advanced_alchemy.mixins.nanoid", "advanced_alchemy.mixins"], __file__)
    with pytest.warns(DeprecationWarning, match="please import it from 'advanced_alchemy.mixins' instead"):
        from advanced_alchemy.base import NanoIDPrimaryKey


def test_deprecated_audit_columns() -> None:
    """Test that using AuditColumns from base raises a deprecation warning."""
    purge_module(["advanced_alchemy.base", "advanced_alchemy.mixins.audit", "advanced_alchemy.mixins"], __file__)
    with pytest.warns(DeprecationWarning, match="please import it from 'advanced_alchemy.mixins' instead"):
        from advanced_alchemy.base import AuditColumns


def test_deprecated_classes_functionality() -> None:
    """Test that deprecated classes maintain functionality while warning."""
    purge_module(["advanced_alchemy.base", "advanced_alchemy.mixins"], __file__)

    warnings.filterwarnings("ignore", category=DeprecationWarning)
    from sqlalchemy import exc as sa_exc

    warnings.filterwarnings("ignore", category=sa_exc.SAWarning)

    # Test instantiation and basic attributes
    from advanced_alchemy.base import AuditColumns, NanoIDPrimaryKey, UUIDPrimaryKey, UUIDv6PrimaryKey, UUIDv7PrimaryKey

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
