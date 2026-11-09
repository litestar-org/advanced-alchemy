"""Unit tests for lazy-loaded, typed Litestar extension submodule re-exports."""

from __future__ import annotations

import importlib

import pytest

import advanced_alchemy.extensions.litestar as litestar_ext

RE_EXPORTED_SUBMODULES = (
    "base",
    "exceptions",
    "filters",
    "mixins",
    "operations",
    "repository",
    "service",
    "types",
    "utils",
)

EXPECTED_UTILS_EXPORTS = {
    "cli_tools",
    "dataclass",
    "dependencies",
    "deprecation",
    "fixtures",
    "module_loader",
    "portals",
    "serialization",
    "singleton",
    "sync_tools",
    "text",
}


def test_repository_re_exports() -> None:
    """Verify legacy litestar.contrib.sqlalchemy deprecation warning."""
    with pytest.warns(DeprecationWarning):
        contrib_types = importlib.import_module("litestar.contrib.sqlalchemy.types")
        contrib_repo = importlib.import_module("litestar.contrib.sqlalchemy.repository")
        assert contrib_types is not None
        assert hasattr(contrib_repo, "SQLAlchemyAsyncRepository")
        assert hasattr(contrib_repo, "SQLAlchemySyncRepository")
        assert hasattr(contrib_repo, "wrap_sqlalchemy_exception")


@pytest.mark.parametrize("submodule_name", RE_EXPORTED_SUBMODULES)
def test_litestar_submodule_lazy_re_exports(submodule_name: str) -> None:
    """Verify each Litestar extension submodule lazily re-exports all core symbols."""
    litestar_submod = importlib.import_module(f"advanced_alchemy.extensions.litestar.{submodule_name}")
    core_mod = importlib.import_module(f"advanced_alchemy.{submodule_name}")

    assert getattr(litestar_ext, submodule_name) is litestar_submod

    core_all = getattr(core_mod, "__all__", None)
    if core_all is not None:
        assert set(litestar_submod.__all__) == set(core_all)
    else:
        assert set(litestar_submod.__all__) == EXPECTED_UTILS_EXPORTS

    submod_dir = set(dir(litestar_submod))
    assert set(litestar_submod.__all__).issubset(submod_dir)

    for symbol in litestar_submod.__all__:
        resolved = getattr(litestar_submod, symbol)
        assert resolved is getattr(core_mod, symbol)
        assert getattr(litestar_submod, symbol) is resolved

    with pytest.raises(AttributeError, match="has no attribute"):
        _ = litestar_submod.__non_existent_attribute__


def test_litestar_direct_from_imports() -> None:
    """Verify direct symbol imports from Litestar extension submodules."""
    from advanced_alchemy.extensions.litestar.base import UUIDAuditBase, UUIDBase
    from advanced_alchemy.extensions.litestar.exceptions import NotFoundError, RepositoryError
    from advanced_alchemy.extensions.litestar.filters import FilterTypes, LimitOffset
    from advanced_alchemy.extensions.litestar.mixins import AuditColumns, SlugKey
    from advanced_alchemy.extensions.litestar.operations import OnConflictUpsert
    from advanced_alchemy.extensions.litestar.repository import (
        SQLAlchemyAsyncRepository,
        SQLAlchemySyncRepository,
    )
    from advanced_alchemy.extensions.litestar.service import (
        SQLAlchemyAsyncRepositoryService,
        SQLAlchemySyncRepositoryService,
    )
    from advanced_alchemy.extensions.litestar.types import GUID, DateTimeUTC
    from advanced_alchemy.extensions.litestar.utils import dataclass, serialization

    assert UUIDBase is not None
    assert UUIDAuditBase is not None
    assert NotFoundError is not None
    assert RepositoryError is not None
    assert FilterTypes is not None
    assert LimitOffset is not None
    assert AuditColumns is not None
    assert SlugKey is not None
    assert OnConflictUpsert is not None
    assert SQLAlchemyAsyncRepository is not None
    assert SQLAlchemySyncRepository is not None
    assert SQLAlchemyAsyncRepositoryService is not None
    assert SQLAlchemySyncRepositoryService is not None
    assert GUID is not None
    assert DateTimeUTC is not None
    assert dataclass is not None
    assert serialization is not None


def test_litestar_package_dir_and_getattr() -> None:
    """Verify package-level __dir__ and __getattr__ on advanced_alchemy.extensions.litestar."""
    ext_dir = set(dir(litestar_ext))
    assert set(litestar_ext.__all__).issubset(ext_dir)
    for submod in RE_EXPORTED_SUBMODULES:
        assert submod in ext_dir

    with pytest.raises(AttributeError, match="has no attribute"):
        _ = litestar_ext.__non_existent_attribute__
