"""Sphinx extension for changelog and change directives."""

# ruff: noqa: FIX002 PLR0911 ARG001
from __future__ import annotations

import ast
import importlib
import inspect
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Generator

    from docutils.nodes import Element, Node
    from sphinx.addnodes import pending_xref
    from sphinx.application import Sphinx
    from sphinx.environment import BuildEnvironment


def _get_module_ast(source_file: str) -> ast.AST | ast.Module:
    return ast.parse(Path(source_file).read_text(encoding="utf-8"))


def _get_import_nodes(nodes: list[ast.stmt]) -> Generator[ast.Import | ast.ImportFrom, None, None]:
    for node in nodes:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            yield node
        elif isinstance(node, ast.If) and getattr(node.test, "id", None) == "TYPE_CHECKING":
            yield from _get_import_nodes(node.body)


def get_module_global_imports(module_import_path: str, reference_target_source_obj: str) -> set[str]:
    """Return a set of names that are imported globally within the containing module of ``reference_target_source_obj``,
    including imports in ``if TYPE_CHECKING`` blocks.
    """
    module = importlib.import_module(module_import_path)
    obj = getattr(module, reference_target_source_obj)
    tree = _get_module_ast(inspect.getsourcefile(obj))  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]

    import_nodes = _get_import_nodes(tree.body)  # type: ignore[attr-defined]
    return {path.asname or path.name for import_node in import_nodes for path in import_node.names}


def _resolve_local_reference(module_path: str, target: str) -> bool:
    """Attempt to resolve a reference within the local codebase.

    Args:
        module_path: The module path (e.g., 'advanced_alchemy.base')
        target: The target class/attribute name

    Returns:
        bool: True if reference exists, False otherwise
    """
    try:
        module = importlib.import_module(module_path)
        if "." in target:
            # Handle fully qualified names (e.g., advanced_alchemy.base.BasicAttributes)
            parts = target.split(".")
            current = module
            for part in parts:
                current = getattr(current, part)
            return True
        return hasattr(module, target)
    except (ImportError, AttributeError):
        return False


def _resolve_sqlalchemy_reference(target: str) -> bool:
    """Attempt to resolve SQLAlchemy references.

    Args:
        target: The target class/attribute name

    Returns:
        bool: True if reference exists, False otherwise
    """
    try:
        import sqlalchemy

        if "." in target:
            # Handle nested attributes (e.g., Connection.in_transaction)
            obj_name, attr_name = target.rsplit(".", 1)
            obj = getattr(sqlalchemy, obj_name)
            return hasattr(obj, attr_name)
        return hasattr(sqlalchemy, target)
    except (ImportError, AttributeError):
        return False


def _resolve_litestar_reference(target: str) -> bool:
    """Attempt to resolve Litestar references.

    Args:
        target: The target class/attribute name

    Returns:
        bool: True if reference exists, False otherwise
    """
    try:
        import litestar
        from litestar import datastructures

        # Handle common Litestar classes
        if target in {"Litestar", "State", "Scope", "Message", "AppConfig", "BeforeMessageSendHookHandler"}:
            return True
        if target.startswith("datastructures."):
            _, attr = target.split(".")
            return hasattr(datastructures, attr)
        if target.startswith("config.app."):
            return True  # These are valid Litestar config references
        return hasattr(litestar, target)
    except ImportError:
        return False


def _resolve_sqlalchemy_type_reference(target: str) -> bool:
    """Attempt to resolve SQLAlchemy type references.

    Args:
        target: The target class/attribute name

    Returns:
        bool: True if reference exists, False otherwise
    """
    try:
        from sqlalchemy import types as sa_types

        type_classes = {
            "TypeEngine",
            "TypeDecorator",
            "UserDefinedType",
            "ExternalType",
            "Dialect",
            "_types.TypeDecorator",
        }

        if target in type_classes:
            return True
        if target.startswith("_types."):
            _, attr = target.split(".")
            return hasattr(sa_types, attr)
        return hasattr(sa_types, target)
    except ImportError:
        return False


def _resolve_advanced_alchemy_reference(target: str, module: str) -> bool:
    """Attempt to resolve Advanced Alchemy references.

    Args:
        target: The target class/attribute name
        module: The current module context

    Returns:
        bool: True if reference exists, False otherwise
    """
    # Handle base module references
    base_classes = {
        "BasicAttributes",
        "CommonTableAttributes",
        "AuditColumns",
        "BigIntPrimaryKey",
        "UUIDPrimaryKey",
        "UUIDv6PrimaryKey",
        "UUIDv7PrimaryKey",
        "NanoIDPrimaryKey",
        "Empty",
        "TableArgsType",
        "DeclarativeBase",
    }

    # Handle config module references
    config_classes = {
        "EngineT",
        "SessionT",
        "SessionMakerT",
        "ConnectionT",
        "GenericSessionConfig",
        "GenericAlembicConfig",
    }

    # Handle type module references
    type_classes = {"DateTimeUTC", "ORA_JSONB", "GUID", "EncryptedString", "EncryptedText"}

    if target in base_classes or target in config_classes or target in type_classes:
        return True

    # Handle fully qualified references
    if target.startswith("advanced_alchemy."):
        parts = target.split(".")
        if parts[-1] in base_classes | config_classes | type_classes:
            return True

    # Handle module-relative references
    return bool(module.startswith("advanced_alchemy."))


def _resolve_serialization_reference(target: str) -> bool:
    """Attempt to resolve serialization-related references.

    Args:
        target: The target class/attribute name

    Returns:
        bool: True if reference exists, False otherwise
    """
    serialization_attrs = {"decode_json", "encode_json", "serialization.decode_json", "serialization.encode_json"}
    return target in serialization_attrs


def _resolve_click_reference(target: str) -> bool:
    """Attempt to resolve Click references.

    Args:
        target: The target class/attribute name

    Returns:
        bool: True if reference exists, False otherwise
    """
    try:
        import click

        if target == "Group":
            return True
        return hasattr(click, target)
    except ImportError:
        return False


def on_warn_missing_reference(app: Sphinx, domain: str, node: Node) -> bool | None:
    """Handle warning for missing references by checking if they are valid type imports."""
    if node.tagname != "pending_xref":  # type: ignore[attr-defined]
        return None

    if not hasattr(node, "attributes"):
        return None

    attributes = node.attributes  # type: ignore[attr-defined,unused-ignore]
    target = attributes["reftarget"]
    ref_type = attributes.get("reftype")
    module = attributes.get("py:module", "")

    # Handle TypeVar references
    if hasattr(target, "__class__") and target.__class__.__name__ == "TypeVar":
        return True

    # Handle Advanced Alchemy references
    if _resolve_advanced_alchemy_reference(target, module):
        return True

    # Handle SQLAlchemy type system references
    if ref_type in {"class", "meth", "attr"} and any(
        x in target for x in ["TypeDecorator", "TypeEngine", "Dialect", "ExternalType", "UserDefinedType"]
    ):
        return _resolve_sqlalchemy_type_reference(target)

    # Handle SQLAlchemy core references
    if target.startswith("sqlalchemy.") or (
        ref_type in ("class", "attr", "obj", "meth")
        and target
        in {
            "Engine",
            "Session",
            "Connection",
            "MetaData",
            "AsyncSession",
            "AsyncEngine",
            "AsyncConnection",
            "sessionmaker",
            "async_sessionmaker",
        }
    ):
        clean_target = target.replace("sqlalchemy.", "")
        if _resolve_sqlalchemy_reference(clean_target):
            return True

    # Handle Litestar references
    if ref_type in {"class", "obj"} and (
        target.startswith(("datastructures.", "config.app."))
        or target
        in {
            "Litestar",
            "State",
            "Scope",
            "Message",
            "AppConfig",
            "BeforeMessageSendHookHandler",
            "FieldDefinition",
            "ImproperConfigurationError",
        }
    ):
        return _resolve_litestar_reference(target)

    # Handle serialization references
    if ref_type in {"attr", "meth"} and _resolve_serialization_reference(target):
        return True

    # Handle Click references
    if ref_type == "class" and _resolve_click_reference(target):
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

    attributes = node.attributes  # type: ignore[attr-defined,unused-ignore]
    target = attributes["reftarget"]

    # Remove this check since it's causing issues
    if not isinstance(target, str):
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


def on_env_before_read_docs(app: Sphinx, env: BuildEnvironment, docnames: set[str]) -> None:
    tmp_examples_path = Path.cwd() / "docs/_build/_tmp_examples"
    tmp_examples_path.mkdir(exist_ok=True, parents=True)
    env.tmp_examples_path = tmp_examples_path  # type: ignore[attr-defined] # pyright: ignore[reportAttributeAccessIssue]


def setup(app: Sphinx) -> dict[str, bool]:
    app.connect("env-before-read-docs", on_env_before_read_docs)
    app.connect("missing-reference", on_missing_reference)
    app.connect("warn-missing-reference", on_warn_missing_reference)
    app.add_config_value("ignore_missing_refs", default={}, rebuild="")
    return {"parallel_read_safe": True, "parallel_write_safe": True}
