"""Unit tests for Sphinx missing-reference resolution and objects.inv alias registration."""

from __future__ import annotations

import ast
import inspect
import re
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

import pytest
from docutils import nodes
from sphinx.domains.python import ObjectEntry, PythonDomain

from tools.sphinx_ext import changelog, missing_references
from tools.sphinx_ext.missing_references import (
    _resolve_advanced_alchemy_reference,
    get_module_global_imports,
    on_warn_missing_reference,
)

if TYPE_CHECKING:
    from sphinx.application import Sphinx
    from sphinx.environment import BuildEnvironment


class _FakeNode(nodes.Element):
    """Minimal Docutils Element simulating a Sphinx pending_xref node."""

    def __init__(
        self,
        tagname: str = "pending_xref",
        reftarget: str = "",
        reftype: str = "class",
        py_module: str = "",
        py_class: str = "",
        source: str = "advanced_alchemy/base.py:docstring of advanced_alchemy.base.UUIDBase",
    ) -> None:
        super().__init__()
        self.tagname = tagname
        self.source = source
        self.line = 1
        self.attributes["reftarget"] = reftarget
        self.attributes["reftype"] = reftype
        if py_module:
            self.attributes["py:module"] = py_module
        if py_class:
            self.attributes["py:class"] = py_class


def _make_fake_app(ignore_missing_refs: dict[Any, Any] | None = None) -> Sphinx:
    """Construct a lightweight Sphinx application stub for unit testing."""
    config = SimpleNamespace(ignore_missing_refs=ignore_missing_refs or {})
    return cast("Sphinx", SimpleNamespace(config=config))


@pytest.mark.parametrize(
    ("target", "module"),
    [
        ("sqlalchemy.get_engine", "advanced_alchemy.config.common"),
        ("advanced_alchemy.base.NonExistentSymbol", "advanced_alchemy.base"),
        ("NonExistentClass", "advanced_alchemy.repository._async"),
        ("advanced_alchemy.extensions.NonExistent", "advanced_alchemy.operations"),
    ],
)
def test_broken_internal_advanced_alchemy_target_is_not_suppressed(target: str, module: str) -> None:
    """Ensure broken xrefs inside advanced_alchemy modules are never blanket-suppressed."""
    assert _resolve_advanced_alchemy_reference(target, module) is False

    app = _make_fake_app()
    node = _FakeNode(reftarget=target, reftype="class", py_module=module, py_class="UUIDBase")
    assert on_warn_missing_reference(app, "py", node) is None


def test_valid_type_checking_symbol_in_advanced_alchemy_resolves() -> None:
    """Ensure symbols imported under if TYPE_CHECKING: are discovered via AST inspection."""
    imports = get_module_global_imports("advanced_alchemy.repository._async", "SQLAlchemyAsyncRepository")
    assert "ModelT" in imports

    direct_imports = get_module_global_imports("advanced_alchemy.repository._async", "ModelT")
    assert "ModelT" in direct_imports


@pytest.mark.parametrize(
    ("ignore_map", "source_target", "reftarget", "expected"),
    [
        (
            {"advanced_alchemy.base.UUIDBase": {"CustomTarget"}},
            "advanced_alchemy/base.py:docstring of advanced_alchemy.base.UUIDBase",
            "CustomTarget",
            True,
        ),
        (
            {re.compile(r"advanced_alchemy\.repository\..*"): re.compile(r".*ModelT.*")},
            "advanced_alchemy/repository/_async.py:docstring of advanced_alchemy.repository._async.SQLAlchemyAsyncRepository",
            "ModelT",
            True,
        ),
        (
            {re.compile(r"advanced_alchemy\.repository\..*"): {"SpecificTarget"}},
            "advanced_alchemy/repository/_async.py:docstring of advanced_alchemy.repository._async.SQLAlchemyAsyncRepository",
            "UnmatchedTarget",
            None,
        ),
    ],
)
def test_ignore_missing_refs_exact_and_regex_matching(
    ignore_map: dict[Any, Any],
    source_target: str,
    reftarget: str,
    expected: bool | None,
) -> None:
    """Verify exact and compiled regex matching against app.config.ignore_missing_refs."""
    app = _make_fake_app(ignore_missing_refs=ignore_map)
    node = _FakeNode(
        reftarget=reftarget,
        reftype="class",
        py_module="advanced_alchemy.base",
        source=source_target,
    )
    assert on_warn_missing_reference(app, "py", node) is expected


def test_register_inventory_aliases_populates_litestar_cross_references() -> None:
    """Verify litestar-org/litestar cross-reference aliases and class/data dual roles are registered."""
    register_fn = getattr(missing_references, "register_inventory_aliases", None)
    assert callable(register_fn)

    objects: dict[str, ObjectEntry] = {
        "advanced_alchemy.extensions.litestar.plugins.SQLAlchemyInitPlugin": ObjectEntry(
            "reference/extensions/litestar/plugins",
            "advanced_alchemy.extensions.litestar.plugins.SQLAlchemyInitPlugin",
            "class",
            False,
        ),
        "advanced_alchemy.extensions.litestar.plugins.SQLAlchemySerializationPlugin": ObjectEntry(
            "reference/extensions/litestar/plugins",
            "advanced_alchemy.extensions.litestar.plugins.SQLAlchemySerializationPlugin",
            "class",
            False,
        ),
        "advanced_alchemy.extensions.litestar.plugins.SQLAlchemySerializationPlugin.supports_type": ObjectEntry(
            "reference/extensions/litestar/plugins",
            "advanced_alchemy.extensions.litestar.plugins.SQLAlchemySerializationPlugin.supports_type",
            "method",
            False,
        ),
        "advanced_alchemy.extensions.litestar.plugins.SQLAlchemyAsyncConfig": ObjectEntry(
            "reference/extensions/litestar/plugins",
            "advanced_alchemy.extensions.litestar.plugins.SQLAlchemyAsyncConfig",
            "class",
            False,
        ),
        "advanced_alchemy.extensions.litestar.plugins.SQLAlchemyAsyncConfig.engine_dependency_key": ObjectEntry(
            "reference/extensions/litestar/plugins",
            "advanced_alchemy.extensions.litestar.plugins.SQLAlchemyAsyncConfig.engine_dependency_key",
            "attribute",
            False,
        ),
        "advanced_alchemy.extensions.litestar.dto.SQLAlchemyDTO": ObjectEntry(
            "reference/extensions/litestar/dto",
            "advanced_alchemy.extensions.litestar.dto.SQLAlchemyDTO",
            "class",
            False,
        ),
        "advanced_alchemy.utils.dataclass.Empty": ObjectEntry(
            "reference/utils",
            "advanced_alchemy.utils.dataclass.Empty",
            "class",
            False,
        ),
        "advanced_alchemy.repository.memory.SQLAlchemyAsyncMockRepository": ObjectEntry(
            "reference/repository_memory",
            "advanced_alchemy.repository.memory.SQLAlchemyAsyncMockRepository",
            "class",
            False,
        ),
        "advanced_alchemy.types.BigIntIdentity": ObjectEntry(
            "reference/types",
            "advanced_alchemy.types.BigIntIdentity",
            "data",
            False,
        ),
        "advanced_alchemy.types.JsonB": ObjectEntry(
            "reference/types",
            "advanced_alchemy.types.JsonB",
            "data",
            False,
        ),
    }
    py_domain = SimpleNamespace(objects=objects, modules={})
    env = cast("BuildEnvironment", SimpleNamespace(domains={"py": py_domain}))
    app = _make_fake_app()

    register_fn(app, env)

    assert "advanced_alchemy.extensions.litestar.SQLAlchemyInitPlugin" in objects
    assert "advanced_alchemy.extensions.litestar.SQLAlchemySerializationPlugin" in objects
    assert "advanced_alchemy.extensions.litestar.SQLAlchemySerializationPlugin.supports_type" in objects
    assert "advanced_alchemy.extensions.litestar.SQLAlchemyAsyncConfig" in objects
    assert "advanced_alchemy.extensions.litestar.SQLAlchemyAsyncConfig.engine_dependency_key" in objects
    assert "advanced_alchemy.extensions.litestar.SQLAlchemyDTO" in objects
    assert "advanced_alchemy.dto.SQLAlchemyDTO" in objects
    assert "advanced_alchemy.config.types.Empty" in objects
    assert "advanced_alchemy.base.Empty" in objects
    assert "advanced_alchemy.repository.SQLAlchemyAsyncMockRepository" in objects

    missing_references._install_python_domain_dual_role_patch()
    fake_domain = SimpleNamespace(objects=objects, modules={})
    yielded = list(PythonDomain.get_objects(cast("PythonDomain", fake_domain)))
    class_entries = {name for name, _disp, objtype, _doc, _anchor, _prio in yielded if objtype == "class"}
    data_entries = {name for name, _disp, objtype, _doc, _anchor, _prio in yielded if objtype == "data"}
    assert "advanced_alchemy.types.BigIntIdentity" in data_entries
    assert "advanced_alchemy.types.BigIntIdentity" in class_entries
    assert "advanced_alchemy.types.JsonB" in data_entries
    assert "advanced_alchemy.types.JsonB" in class_entries


def test_sphinx_ext_modules_have_zero_inline_comments_and_no_tmp_examples() -> None:
    """Verify tools/sphinx_ext modules have no inline comments or dead _tmp_examples hooks."""
    assert not hasattr(missing_references, "on_env_before_read_docs")
    for mod in (missing_references, changelog):
        source_path = Path(inspect.getfile(mod)) if "inspect" in globals() else Path(mod.__file__ or "")
        raw = source_path.read_text(encoding="utf-8")
        ast.parse(raw)
        for line in raw.splitlines():
            stripped = line.strip()
            assert not stripped.startswith("#"), f"Inline comment found in {source_path}: {line}"
