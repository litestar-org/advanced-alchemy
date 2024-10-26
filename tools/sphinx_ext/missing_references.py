"""Sphinx extension for changelog and change directives."""

from __future__ import annotations

import ast
import importlib
import inspect
import re
from functools import cache  # pyright: ignore[reportAttributeAccessIssue]
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List

from docutils.utils import get_source_line
from typing_extensions import TypeVar

if TYPE_CHECKING:
    from collections.abc import Generator

    from docutils.nodes import Element, Node
    from sphinx.addnodes import pending_xref
    from sphinx.application import Sphinx
    from sphinx.environment import BuildEnvironment


@cache
def _get_module_ast(source_file: str) -> ast.AST | ast.Module:
    return ast.parse(Path(source_file).read_text(encoding="utf-8"))


def _get_import_nodes(nodes: List[ast.stmt]) -> Generator[ast.Import | ast.ImportFrom, None, None]:
    for node in nodes:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            yield node
        elif isinstance(node, ast.If) and getattr(node.test, "id", None) == "TYPE_CHECKING":
            yield from _get_import_nodes(node.body)


@cache
def get_module_global_imports(module_import_path: str, reference_target_source_obj: str) -> set[str]:
    """Return a set of names that are imported globally within the containing module of ``reference_target_source_obj``,
    including imports in ``if TYPE_CHECKING`` blocks.
    """
    module = importlib.import_module(module_import_path)
    obj = getattr(module, reference_target_source_obj)
    tree = _get_module_ast(inspect.getsourcefile(obj))  # pyright: ignore[reportArgumentType]

    import_nodes = _get_import_nodes(tree.body)  # type: ignore[attr-defined]
    return {path.asname or path.name for import_node in import_nodes for path in import_node.names}


def on_warn_missing_reference(app: Sphinx, domain: str, node: Node) -> bool | None:  # noqa: ARG001, PLR0911
    """Handle warning for missing references by checking if they are valid type imports.

    Args:
        app: The Sphinx application instance
        domain: The domain of the reference
        node: The node containing the reference

    Returns:
        bool | None: True if the warning should be suppressed, None otherwise
    """
    ignore_refs: Dict[str | re.Pattern, set[str] | re.Pattern] = app.config["ignore_missing_refs"]
    if node.tagname != "pending_xref":  # type: ignore[attr-defined]
        return None

    if not hasattr(node, "attributes"):
        return None

    attributes = node.attributes  # type: ignore[attr-defined]
    target = attributes.get("reftarget")

    # Ensure target is a string
    if not isinstance(target, str):
        return None

    # Common SQLAlchemy and Litestar types that should be ignored
    common_types = {
        # SQLAlchemy types
        "AsyncEngine",
        "Engine",
        "AsyncConnection",
        "Connection",
        "Session",
        "AsyncSession",
        "sessionmaker",
        "async_sessionmaker",
        "scoped_session",
        # Litestar types
        "BeforeMessageSendHookHandler",
        "State",
        "Scope",
        "Message",
        "Litestar",
        # Repository types
        "SQLAlchemyAsyncRepository",
        # Error types
        "NotFoundError",
        # Config types
        "SQLAlchemySyncConfig",
        "EngineConfig",
    }

    if target in common_types:
        return True

    if reference_target_source_obj := attributes.get(
        "py:class",
        attributes.get("py:meth", attributes.get("py:func")),
    ):
        global_names = get_module_global_imports(attributes["py:module"], reference_target_source_obj)

        if target in global_names:
            # autodoc has issues with if TYPE_CHECKING imports, and randomly with type aliases in annotations,
            # so we ignore those errors if we can validate that such a name exists in the containing modules global
            # scope or an if TYPE_CHECKING block. see: https://github.com/sphinx-doc/sphinx/issues/11225 and
            # https://github.com/sphinx-doc/sphinx/issues/9813 for reference
            return True

    # for various other autodoc issues that can't be resolved automatically, we check the exact path to be able
    # to suppress specific warnings
    source_line = get_source_line(node)[0]
    source = source_line.split(" ")[-1]
    if target in ignore_refs.get(source, []):  # pyright: ignore[reportOperatorIssue]
        return True

    ignore_ref_rgs = {rg: targets for rg, targets in ignore_refs.items() if isinstance(rg, re.Pattern)}
    for pattern, targets in ignore_ref_rgs.items():
        if not pattern.match(source):
            continue
        if isinstance(targets, set) and target in targets:
            return True
        if targets.match(target):  # pyright: ignore[reportAttributeAccessIssue]
            return True

    return None


def on_missing_reference(app: Sphinx, env: BuildEnvironment, node: pending_xref, contnode: Element) -> Element | None:
    """Handle missing references by attempting to resolve them through different methods.

    Args:
        app: The Sphinx application instance
        env: The Sphinx build environment
        node: The pending cross-reference node
        contnode: The content node

    Returns:
        Element | None: The resolved reference node if found, None otherwise
    """
    if not hasattr(node, "attributes"):
        return None

    attributes = node.attributes  # type: ignore[attr-defined]
    target = attributes["reftarget"]

    # Ensure target is a string and not a TypeVar
    if not isinstance(target, str) or isinstance(target, TypeVar):
        return None

    py_domain = env.domains["py"]

    # autodoc sometimes incorrectly resolves these types, so we try to resolve them as py:data first and fall back to any
    new_node = py_domain.resolve_xref(env, node["refdoc"], app.builder, "data", target, node, contnode)
    if new_node is None:
        resolved_xrefs = py_domain.resolve_any_xref(env, node["refdoc"], app.builder, target, node, contnode)
        for ref in resolved_xrefs:
            if ref:
                return ref[1]
    return new_node


def on_env_before_read_docs(app: Sphinx, env: BuildEnvironment, docnames: set[str]) -> None:  # noqa: ARG001
    tmp_examples_path = Path.cwd() / "docs/_build/_tmp_examples"
    tmp_examples_path.mkdir(exist_ok=True, parents=True)
    env.tmp_examples_path = tmp_examples_path  # pyright: ignore[reportAttributeAccessIssue]


def setup(app: Sphinx) -> Dict[str, bool]:
    app.connect("env-before-read-docs", on_env_before_read_docs)
    app.connect("missing-reference", on_missing_reference)
    app.add_config_value("ignore_missing_refs", default={}, rebuild=False)

    return {"parallel_read_safe": True, "parallel_write_safe": True}
