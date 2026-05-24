"""Wire-compatibility tests for shared provider utilities."""

import pytest

from advanced_alchemy.utils.dependencies import (
    DependencyCache as CoreDependencyCache,
)
from advanced_alchemy.utils.dependencies import (
    FieldNameType as CoreFieldNameType,
)
from advanced_alchemy.utils.dependencies import (
    FilterConfig as CoreFilterConfig,
)

pytestmark = pytest.mark.unit


def test_litestar_provider_reexports_core_dependency_utilities() -> None:
    from advanced_alchemy.extensions.litestar import providers

    assert providers.DependencyCache is CoreDependencyCache
    assert providers.FieldNameType is CoreFieldNameType
    assert providers.FilterConfig is CoreFilterConfig
    assert {"DependencyCache", "FieldNameType", "FilterConfig"} <= set(providers.__all__)


def test_fastapi_provider_reexports_core_dependency_utilities() -> None:
    pytest.importorskip("fastapi")

    from advanced_alchemy.extensions.fastapi import providers

    assert providers.DependencyCache is CoreDependencyCache
    assert providers.FieldNameType is CoreFieldNameType
    assert providers.FilterConfig is CoreFilterConfig
    assert {"DependencyCache", "FieldNameType", "FilterConfig"} <= set(providers.__all__)


def test_provider_cache_namespaces_are_framework_scoped() -> None:
    pytest.importorskip("fastapi")

    from advanced_alchemy.extensions.fastapi import providers as fastapi_providers
    from advanced_alchemy.extensions.litestar import providers as litestar_providers

    assert litestar_providers._CACHE_NAMESPACE != fastapi_providers._CACHE_NAMESPACE
