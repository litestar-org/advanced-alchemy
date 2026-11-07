"""Sphinx extension for resolving cross-references and registering objects.inv aliases."""

from __future__ import annotations

import ast
import builtins
import importlib
import inspect
import os
import re
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from docutils.utils import get_source_line
from sphinx.domains.python import ObjectEntry, PythonDomain
from sphinx.ext.autodoc import ClassDocumenter, Documenter, FunctionDocumenter, MethodDocumenter
from sphinx.ext.autodoc import directive as autodoc_directive
from sphinx.ext.autodoc import typehints as autodoc_typehints

if TYPE_CHECKING:
    from collections.abc import Generator, Iterator

    from docutils.nodes import Element, Node
    from sphinx.addnodes import pending_xref
    from sphinx.application import Sphinx
    from sphinx.environment import BuildEnvironment

__all__ = (
    "CLASS_ROLE_DATA_SUFFIXES",
    "LITESTAR_OBJECT_ALIAS_GROUPS",
    "PACKAGE_REEXPORT_MODULES",
    "get_module_global_imports",
    "on_missing_reference",
    "on_warn_missing_reference",
    "register_inventory_aliases",
    "setup",
)

_TYPEVAR_CLASS_NAMES: frozenset[str] = frozenset({
    "TypeVar",
    "ParamSpec",
    "TypeVarTuple",
    "TypeAliasType",
    "_TypeAliasForm",
})

CLASS_ROLE_DATA_SUFFIXES: frozenset[str] = frozenset({
    "BigIntIdentity",
    "JsonB",
    "EngineT",
    "SessionT",
    "SessionMakerT",
    "ConnectionT",
    "FilterTypes",
    "EmptyType",
    "ModelT",
    "ModelDTOT",
    "SelectT",
    "RowT",
    "StorageBackendT",
    "CommitStrategy",
    "RoutingStrategy",
    "TypeEncodersMap",
    "TypeDecodersSequence",
    "ErrorMessages",
    "FilterMap",
    "LogicalOperatorMap",
})

LITESTAR_OBJECT_ALIAS_GROUPS: tuple[tuple[str, ...], ...] = (
    (
        "advanced_alchemy.extensions.litestar.SQLAlchemyPlugin",
        "advanced_alchemy.extensions.litestar.plugins.SQLAlchemyPlugin",
        "advanced_alchemy.extensions.litestar.plugins.init.plugin.SQLAlchemyPlugin",
    ),
    (
        "advanced_alchemy.extensions.litestar.SQLAlchemyInitPlugin",
        "advanced_alchemy.extensions.litestar.plugins.SQLAlchemyInitPlugin",
        "advanced_alchemy.extensions.litestar.plugins.init.plugin.SQLAlchemyInitPlugin",
    ),
    (
        "advanced_alchemy.extensions.litestar.SQLAlchemySerializationPlugin",
        "advanced_alchemy.extensions.litestar.plugins.SQLAlchemySerializationPlugin",
        "advanced_alchemy.extensions.litestar.plugins.serialization.SQLAlchemySerializationPlugin",
    ),
    (
        "advanced_alchemy.extensions.litestar.SQLAlchemyAsyncConfig",
        "advanced_alchemy.extensions.litestar.plugins.SQLAlchemyAsyncConfig",
        "advanced_alchemy.extensions.litestar.plugins.init.config.SQLAlchemyAsyncConfig",
        "advanced_alchemy.extensions.litestar.plugins.init.config.asyncio.SQLAlchemyAsyncConfig",
    ),
    (
        "advanced_alchemy.extensions.litestar.SQLAlchemySyncConfig",
        "advanced_alchemy.extensions.litestar.plugins.SQLAlchemySyncConfig",
        "advanced_alchemy.extensions.litestar.plugins.init.config.SQLAlchemySyncConfig",
        "advanced_alchemy.extensions.litestar.plugins.init.config.sync.SQLAlchemySyncConfig",
    ),
    (
        "advanced_alchemy.extensions.litestar.EngineConfig",
        "advanced_alchemy.extensions.litestar.plugins.EngineConfig",
        "advanced_alchemy.extensions.litestar.plugins.init.config.EngineConfig",
        "advanced_alchemy.extensions.litestar.plugins.init.config.engine.EngineConfig",
    ),
    (
        "advanced_alchemy.extensions.litestar.AsyncSessionConfig",
        "advanced_alchemy.config.AsyncSessionConfig",
        "advanced_alchemy.config.asyncio.AsyncSessionConfig",
    ),
    (
        "advanced_alchemy.extensions.litestar.SyncSessionConfig",
        "advanced_alchemy.config.SyncSessionConfig",
        "advanced_alchemy.config.sync.SyncSessionConfig",
    ),
    (
        "advanced_alchemy.extensions.litestar.AlembicAsyncConfig",
        "advanced_alchemy.config.AlembicAsyncConfig",
        "advanced_alchemy.config.asyncio.AlembicAsyncConfig",
    ),
    (
        "advanced_alchemy.extensions.litestar.AlembicSyncConfig",
        "advanced_alchemy.config.AlembicSyncConfig",
        "advanced_alchemy.config.sync.AlembicSyncConfig",
    ),
    (
        "advanced_alchemy.extensions.litestar.AlembicCommands",
        "advanced_alchemy.alembic.commands.AlembicCommands",
    ),
    (
        "advanced_alchemy.extensions.litestar.dto.SQLAlchemyDTO",
        "advanced_alchemy.extensions.litestar.SQLAlchemyDTO",
        "advanced_alchemy.dto.SQLAlchemyDTO",
    ),
    (
        "advanced_alchemy.extensions.litestar.dto.SQLAlchemyDTOConfig",
        "advanced_alchemy.extensions.litestar.SQLAlchemyDTOConfig",
        "advanced_alchemy.dto.SQLAlchemyDTOConfig",
    ),
    (
        "advanced_alchemy.utils.dataclass.Empty",
        "advanced_alchemy.config.types.Empty",
        "advanced_alchemy.base.Empty",
        "advanced_alchemy.utils.Empty",
    ),
    (
        "advanced_alchemy.utils.dataclass.EmptyType",
        "advanced_alchemy.config.types.EmptyType",
        "advanced_alchemy.utils.EmptyType",
    ),
    (
        "advanced_alchemy._listeners.touch_updated_timestamp",
        "advanced_alchemy.base.touch_updated_timestamp",
    ),
    (
        "advanced_alchemy.utils.serialization.decode_json",
        "advanced_alchemy.decode_json",
        "advanced_alchemy._serialization.decode_json",
    ),
    (
        "advanced_alchemy.utils.serialization.encode_json",
        "advanced_alchemy.encode_json",
        "advanced_alchemy._serialization.encode_json",
    ),
    (
        "advanced_alchemy.config.common.EngineT",
        "advanced_alchemy.config.EngineT",
    ),
    (
        "advanced_alchemy.config.common.SessionT",
        "advanced_alchemy.config.SessionT",
    ),
    (
        "advanced_alchemy.config.common.SessionMakerT",
        "advanced_alchemy.config.SessionMakerT",
    ),
    (
        "advanced_alchemy.config.common.ConnectionT",
        "advanced_alchemy.config.ConnectionT",
    ),
    (
        "advanced_alchemy.config.common.GenericSessionConfig",
        "advanced_alchemy.config.GenericSessionConfig",
    ),
    (
        "advanced_alchemy.config.common.GenericSQLAlchemyConfig",
        "advanced_alchemy.config.GenericSQLAlchemyConfig",
    ),
    (
        "advanced_alchemy.config.common.GenericAlembicConfig",
        "advanced_alchemy.config.GenericAlembicConfig",
    ),
    (
        "advanced_alchemy.config.engine.EngineConfig",
        "advanced_alchemy.config.EngineConfig",
    ),
    (
        "advanced_alchemy.config.asyncio.SQLAlchemyAsyncConfig",
        "advanced_alchemy.config.SQLAlchemyAsyncConfig",
    ),
    (
        "advanced_alchemy.config.sync.SQLAlchemySyncConfig",
        "advanced_alchemy.config.SQLAlchemySyncConfig",
    ),
    (
        "advanced_alchemy.config.routing.RoutingConfig",
        "advanced_alchemy.config.RoutingConfig",
        "advanced_alchemy.routing.RoutingConfig",
    ),
    (
        "advanced_alchemy.config.routing.ReplicaConfig",
        "advanced_alchemy.config.ReplicaConfig",
        "advanced_alchemy.routing.ReplicaConfig",
    ),
    (
        "advanced_alchemy.config.routing.RoutingStrategy",
        "advanced_alchemy.config.RoutingStrategy",
        "advanced_alchemy.routing.RoutingStrategy",
    ),
    (
        "advanced_alchemy.repository.SQLAlchemyAsyncRepository",
        "advanced_alchemy.repository._async.SQLAlchemyAsyncRepository",
        "advanced_alchemy.extensions.litestar.repository.SQLAlchemyAsyncRepository",
    ),
    (
        "advanced_alchemy.repository.SQLAlchemySyncRepository",
        "advanced_alchemy.repository._sync.SQLAlchemySyncRepository",
        "advanced_alchemy.extensions.litestar.repository.SQLAlchemySyncRepository",
    ),
    (
        "advanced_alchemy.repository.SQLAlchemyAsyncSlugRepository",
        "advanced_alchemy.repository._async.SQLAlchemyAsyncSlugRepository",
        "advanced_alchemy.extensions.litestar.repository.SQLAlchemyAsyncSlugRepository",
    ),
    (
        "advanced_alchemy.repository.SQLAlchemySyncSlugRepository",
        "advanced_alchemy.repository._sync.SQLAlchemySyncSlugRepository",
        "advanced_alchemy.extensions.litestar.repository.SQLAlchemySyncSlugRepository",
    ),
    (
        "advanced_alchemy.repository.SQLAlchemyAsyncQueryRepository",
        "advanced_alchemy.repository._async.SQLAlchemyAsyncQueryRepository",
        "advanced_alchemy.extensions.litestar.repository.SQLAlchemyAsyncQueryRepository",
    ),
    (
        "advanced_alchemy.repository.SQLAlchemySyncQueryRepository",
        "advanced_alchemy.repository._sync.SQLAlchemySyncQueryRepository",
        "advanced_alchemy.extensions.litestar.repository.SQLAlchemySyncQueryRepository",
    ),
    (
        "advanced_alchemy.repository.memory.SQLAlchemyAsyncMockRepository",
        "advanced_alchemy.repository.SQLAlchemyAsyncMockRepository",
        "advanced_alchemy.repository.memory._async.SQLAlchemyAsyncMockRepository",
    ),
    (
        "advanced_alchemy.repository.memory.SQLAlchemySyncMockRepository",
        "advanced_alchemy.repository.SQLAlchemySyncMockRepository",
        "advanced_alchemy.repository.memory._sync.SQLAlchemySyncMockRepository",
    ),
    (
        "advanced_alchemy.repository.memory.SQLAlchemyAsyncMockSlugRepository",
        "advanced_alchemy.repository.SQLAlchemyAsyncMockSlugRepository",
        "advanced_alchemy.repository.memory._async.SQLAlchemyAsyncMockSlugRepository",
    ),
    (
        "advanced_alchemy.repository.memory.SQLAlchemySyncMockSlugRepository",
        "advanced_alchemy.repository.SQLAlchemySyncMockSlugRepository",
        "advanced_alchemy.repository.memory._sync.SQLAlchemySyncMockSlugRepository",
    ),
    (
        "advanced_alchemy.filters.FilterTypes",
        "advanced_alchemy.service.FilterTypes",
        "advanced_alchemy.service.typing.FilterTypes",
        "advanced_alchemy.extensions.litestar.filters.FilterTypes",
    ),
    (
        "advanced_alchemy.repository.typing.ModelT",
        "advanced_alchemy.repository.ModelT",
        "advanced_alchemy.service.ModelT",
    ),
)

PACKAGE_REEXPORT_MODULES: tuple[str, ...] = (
    "advanced_alchemy",
    "advanced_alchemy.base",
    "advanced_alchemy.cache",
    "advanced_alchemy.config",
    "advanced_alchemy.exceptions",
    "advanced_alchemy.filters",
    "advanced_alchemy.mixins",
    "advanced_alchemy.operations",
    "advanced_alchemy.repository",
    "advanced_alchemy.repository.memory",
    "advanced_alchemy.routing",
    "advanced_alchemy.service",
    "advanced_alchemy.types",
    "advanced_alchemy.utils",
    "advanced_alchemy.extensions.litestar",
    "advanced_alchemy.extensions.litestar.dto",
    "advanced_alchemy.extensions.litestar.plugins",
    "advanced_alchemy.extensions.litestar.session",
    "advanced_alchemy.extensions.litestar.store",
    "advanced_alchemy.extensions.fastapi",
    "advanced_alchemy.extensions.flask",
    "advanced_alchemy.extensions.sanic",
    "advanced_alchemy.extensions.starlette",
)


@cache
def _get_module_ast(source_file: str) -> ast.Module:
    """Parse and cache the AST for a Python source file."""
    return ast.parse(Path(source_file).read_text(encoding="utf-8"))


def _get_import_nodes(nodes: list[ast.stmt]) -> Generator[ast.Import | ast.ImportFrom, None, None]:
    """Yield import statements from top-level and ``if TYPE_CHECKING:`` blocks."""
    for node in nodes:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            yield node
        elif isinstance(node, ast.If) and getattr(node.test, "id", None) == "TYPE_CHECKING":
            yield from _get_import_nodes(node.body)


def _get_typevar_assigned_names(nodes: list[ast.stmt]) -> set[str]:
    """Extract module-level TypeVar, ParamSpec, and TypeAlias names from AST statements."""
    names: set[str] = set()
    for node in nodes:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            func_name = getattr(node.value.func, "id", None) or getattr(node.value.func, "attr", None)
            if func_name in {"TypeVar", "ParamSpec", "TypeVarTuple", "TypeAliasType", "NewType"}:
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        names.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            ann_name = getattr(node.annotation, "id", None) or getattr(node.annotation, "attr", None)
            if ann_name == "TypeAlias":
                names.add(node.target.id)
        elif isinstance(node, ast.If) and getattr(node.test, "id", None) == "TYPE_CHECKING":
            names.update(_get_typevar_assigned_names(node.body))
    return names


@cache
def get_module_global_imports(module_import_path: str, reference_target_source_obj: str = "") -> set[str]:
    """Return global and ``if TYPE_CHECKING:`` imported names for ``module_import_path``."""
    try:
        module = importlib.import_module(module_import_path)
    except ImportError:
        return set()

    source_file: str | None = None
    if reference_target_source_obj:
        root_attr = reference_target_source_obj.split(".", 1)[0]
        obj = getattr(module, root_attr, None)
        if obj is not None:
            try:
                source_file = inspect.getsourcefile(obj)
            except TypeError:
                source_file = None

    if source_file is None:
        try:
            source_file = inspect.getsourcefile(module)
        except TypeError:
            return set()

    if not source_file:
        return set()

    tree = _get_module_ast(source_file)
    import_nodes = _get_import_nodes(tree.body)
    imported_names = {path.asname or path.name for import_node in import_nodes for path in import_node.names}
    imported_names.update(_get_typevar_assigned_names(tree.body))
    return imported_names


def _is_runtime_typevar_or_alias(obj: Any) -> bool:
    """Return True if ``obj`` is a runtime TypeVar, ParamSpec, or typing alias."""
    if obj is None:
        return False
    cls_name = getattr(obj, "__class__", type(obj)).__name__
    if cls_name in _TYPEVAR_CLASS_NAMES:
        return True
    return getattr(type(obj), "__module__", "") == "typing" and not isinstance(obj, type)


def _resolve_advanced_alchemy_reference(target: str, module: str) -> bool:
    """Verify whether ``target`` is a valid TYPE_CHECKING import or TypeVar in ``module``.

    Broken references to non-existent ``advanced_alchemy`` symbols or external libraries
    always return ``False`` so Sphinx surfaces the warning.
    """
    external_prefixes = ("sqlalchemy.", "alembic.", "litestar.", "click.", "msgspec.", "pydantic.")
    if not module.startswith("advanced_alchemy") or target.startswith(external_prefixes):
        return False

    resolved = False
    if "." not in target:
        try:
            mod = importlib.import_module(module)
        except ImportError:
            return False
        if hasattr(mod, target):
            runtime_obj = getattr(mod, target)
            resolved = _is_runtime_typevar_or_alias(runtime_obj) or target in CLASS_ROLE_DATA_SUFFIXES
        else:
            resolved = target in get_module_global_imports(module)
    elif target.startswith("advanced_alchemy."):
        mod_path, _, attr_name = target.rpartition(".")
        try:
            target_mod = importlib.import_module(mod_path)
        except ImportError:
            return False
        if hasattr(target_mod, attr_name):
            runtime_obj = getattr(target_mod, attr_name)
            resolved = _is_runtime_typevar_or_alias(runtime_obj) or attr_name in CLASS_ROLE_DATA_SUFFIXES
        else:
            resolved = attr_name in get_module_global_imports(mod_path) and attr_name in CLASS_ROLE_DATA_SUFFIXES

    return resolved


def _propagate_member_aliases(
    objects: dict[str, ObjectEntry],
    canonical_name: str,
    alias_name: str,
) -> None:
    """Propagate documented class attribute and method entries from ``canonical_name`` to ``alias_name``."""
    prefix = f"{canonical_name}."
    member_entries = [
        (obj_name[len(prefix) :], entry)
        for obj_name, entry in list(objects.items())
        if obj_name.startswith(prefix)
    ]
    for suffix, entry in member_entries:
        alias_member = f"{alias_name}.{suffix}"
        if alias_member not in objects:
            objects[alias_member] = ObjectEntry(entry.docname, entry.node_id, entry.objtype, True)


def _register_alias_group(objects: dict[str, ObjectEntry], group: tuple[str, ...]) -> None:
    """Register aliased ObjectEntry records for all members of an equivalence ``group``."""
    canonical_name: str | None = None
    canonical_entry: ObjectEntry | None = None
    for candidate in group:
        entry = objects.get(candidate)
        if entry is not None and not entry.aliased:
            canonical_name = candidate
            canonical_entry = entry
            break
    if canonical_entry is None:
        for candidate in group:
            entry = objects.get(candidate)
            if entry is not None:
                canonical_name = candidate
                canonical_entry = entry
                break
    if canonical_name is None or canonical_entry is None:
        return

    for alias_name in group:
        if alias_name not in objects:
            objects[alias_name] = ObjectEntry(
                canonical_entry.docname,
                canonical_entry.node_id,
                canonical_entry.objtype,
                True,
            )
        if canonical_entry.objtype == "class" and alias_name != canonical_name:
            _propagate_member_aliases(objects, canonical_name, alias_name)


def _register_undocumented_class_members(objects: dict[str, ObjectEntry]) -> None:
    """Register public methods and attributes of documented classes onto their class anchor."""
    for fullname, entry in list(objects.items()):
        if entry.objtype != "class" or entry.aliased or not fullname.startswith("advanced_alchemy."):
            continue
        mod_name, _, cls_name = fullname.rpartition(".")
        try:
            mod = importlib.import_module(mod_name)
        except ImportError:
            continue
        cls = getattr(mod, cls_name, None)
        if not isinstance(cls, type):
            continue
        for attr_name in dir(cls):
            if attr_name.startswith("_"):
                continue
            member_fullname = f"{fullname}.{attr_name}"
            if member_fullname in objects:
                continue
            static_attr = inspect.getattr_static(cls, attr_name, None)
            is_callable = callable(static_attr) or isinstance(static_attr, (classmethod, staticmethod))
            member_objtype = "method" if is_callable else "attribute"
            objects[member_fullname] = ObjectEntry(entry.docname, entry.node_id, member_objtype, True)


def register_inventory_aliases(app: Sphinx, env: BuildEnvironment) -> list[str]:
    """Populate Python domain object aliases for package re-exports and Litestar cross-references."""
    del app
    py_domain = env.domains.get("py")
    objects = cast("dict[str, ObjectEntry] | None", getattr(py_domain, "objects", None))
    if objects is None:
        return []

    _register_undocumented_class_members(objects)

    for group in LITESTAR_OBJECT_ALIAS_GROUPS:
        _register_alias_group(objects, group)

    reexport_by_name: dict[str, list[str]] = {}
    for pkg_name in PACKAGE_REEXPORT_MODULES:
        try:
            pkg = importlib.import_module(pkg_name)
        except ImportError:
            continue
        exported_names = getattr(pkg, "__all__", ())
        for sym_name in exported_names:
            sym = getattr(pkg, sym_name, None)
            if sym is None or inspect.ismodule(sym):
                continue
            origin_module = getattr(sym, "__module__", None)
            candidates = reexport_by_name.setdefault(sym_name, [])
            pkg_full = f"{pkg_name}.{sym_name}"
            if pkg_full not in candidates:
                candidates.append(pkg_full)
            if isinstance(origin_module, str) and origin_module.startswith("advanced_alchemy"):
                origin_full = f"{origin_module}.{sym_name}"
                if origin_full not in candidates:
                    candidates.append(origin_full)
                parent_mod = origin_module.rsplit(".", 1)[0]
                parent_full = f"{parent_mod}.{sym_name}"
                if parent_full not in candidates:
                    candidates.append(parent_full)

    for candidates in reexport_by_name.values():
        if len(candidates) > 1:
            _register_alias_group(objects, tuple(candidates))

    litestar_submodules = (
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
    for submod in litestar_submodules:
        src_prefix = f"advanced_alchemy.{submod}."
        dst_prefix = f"advanced_alchemy.extensions.litestar.{submod}."
        for obj_name, entry in list(objects.items()):
            if obj_name.startswith(src_prefix):
                suffix = obj_name[len(src_prefix) :]
                alias_name = f"{dst_prefix}{suffix}"
                if alias_name not in objects:
                    objects[alias_name] = ObjectEntry(entry.docname, entry.node_id, entry.objtype, True)

    return []


def _install_python_domain_dual_role_patch() -> None:
    """Ensure PythonDomain.get_objects yields py:class aliases for data/type-alias inventory entries."""
    if getattr(PythonDomain, "_aa_dual_role_patched", False):
        return

    original_get_objects = PythonDomain.get_objects

    def _patched_get_objects(self: PythonDomain) -> Iterator[tuple[str, str, str, str, str, int]]:
        emitted_classes: set[str] = set()
        buffered: list[tuple[str, str, str, str, str, int]] = []
        for item in original_get_objects(self):
            buffered.append(item)
            if item[2] == "class":
                emitted_classes.add(item[0])
            yield item

        for fullname, dispname, objtype, docname, anchor, _prio in buffered:
            if objtype in {"data", "attribute"} and fullname not in emitted_classes:
                short_name = fullname.rsplit(".", 1)[-1]
                if short_name in CLASS_ROLE_DATA_SUFFIXES:
                    emitted_classes.add(fullname)
                    yield (fullname, dispname, "class", docname, anchor, -1)

    setattr(PythonDomain, "get_objects", _patched_get_objects)
    setattr(PythonDomain, "_aa_dual_role_patched", True)


def _install_autodoc_explicit_members_patch() -> None:
    """Preserve explicit ``:members:`` allowlists and compact description-mode overload signatures."""
    if getattr(autodoc_directive, "_aa_explicit_members_patched", False):
        return

    original_process = autodoc_directive.process_documenter_options

    def _patched_process_documenter_options(
        documenter: Any,
        config: Any,
        options: dict[str, str],
    ) -> Any:
        explicit_members = options.get("members")
        resolved = original_process(documenter, config, options)
        if isinstance(explicit_members, str) and explicit_members.strip():
            resolved["members"] = [item.strip() for item in explicit_members.split(",") if item.strip()]
        return resolved

    original_func_sig = FunctionDocumenter.format_signature
    original_meth_sig = MethodDocumenter.format_signature

    def _compact_func_signature(self: FunctionDocumenter, **kwargs: Any) -> str:
        if self.config.autodoc_typehints == "description":
            return Documenter.format_signature(self, **kwargs)
        return original_func_sig(self, **kwargs)

    def _compact_meth_signature(self: MethodDocumenter, **kwargs: Any) -> str:
        if self.config.autodoc_typehints == "description":
            return Documenter.format_signature(self, **kwargs)
        return original_meth_sig(self, **kwargs)

    original_cls_get_sig = ClassDocumenter._get_signature

    def _compact_cls_get_signature(self: ClassDocumenter) -> tuple[Any | None, str | None, Any | None]:
        if (
            not self.options.inherited_members
            and isinstance(self.object, type)
            and "__init__" not in self.object.__dict__
            and "__new__" not in self.object.__dict__
            and "__dataclass_fields__" not in self.object.__dict__
        ):
            return None, None, None
        return original_cls_get_sig(self)

    original_record_typehints = autodoc_typehints.record_typehints

    def _compact_record_typehints(
        app: Sphinx,
        objtype: str,
        name: str,
        obj: Any,
        options: Any,
        args: str,
        retann: str,
    ) -> None:
        if objtype == "class" and isinstance(obj, type):
            doc = getattr(obj, "__doc__", "") or ""
            if "Args:" not in doc and "Parameters" not in doc and ":param " not in doc:
                return
        original_record_typehints(app, objtype, name, obj, options, args, retann)
        annotations = app.env.temp_data.get("annotations", {}).get(name)
        if isinstance(annotations, dict):
            for key, val in list(annotations.items()):
                if isinstance(val, str):
                    if "_AbstractLoad" in val:
                        annotations[key] = "~advanced_alchemy.repository.LoadSpec | None"
                    elif "UnaryExpression" in val and "InstrumentedAttribute" in val:
                        annotations[key] = (
                            "list[~advanced_alchemy.repository.OrderingPair] "
                            "| ~advanced_alchemy.repository.OrderingPair | None"
                        )

    setattr(autodoc_directive, "process_documenter_options", _patched_process_documenter_options)
    setattr(FunctionDocumenter, "format_signature", _compact_func_signature)
    setattr(MethodDocumenter, "format_signature", _compact_meth_signature)
    setattr(ClassDocumenter, "_get_signature", _compact_cls_get_signature)
    setattr(autodoc_typehints, "record_typehints", _compact_record_typehints)
    setattr(autodoc_directive, "_aa_explicit_members_patched", True)


def _is_offline_mode() -> bool:
    """Return True when offline documentation build mode is active."""
    return os.getenv("_ADVANCED_ALCHEMY_DOCS_OFFLINE", "").strip().lower() in {"1", "true", "yes"}


def _resolve_external_runtime_symbol(target: str) -> bool:
    """Check if an external dotted reference resolves to a real attribute on an installed package."""
    if target.startswith("advanced_alchemy"):
        return False
    if hasattr(builtins, target):
        return True
    parts = target.split(".")
    for split_idx in range(len(parts) - 1, 0, -1):
        mod_name = ".".join(parts[:split_idx])
        try:
            current: Any = importlib.import_module(mod_name)
        except ImportError:
            continue
        found = True
        for attr in parts[split_idx:]:
            if not hasattr(current, attr):
                found = False
                break
            current = getattr(current, attr)
        if found:
            return True
    return False


def _matches_ignore_missing_refs(
    ignore_refs: dict[str | re.Pattern[str], set[str] | list[Any] | re.Pattern[str]],
    source: str,
    target: str,
) -> bool:
    """Return True if ``(source, target)`` matches ``app.config.ignore_missing_refs``."""
    direct_targets = ignore_refs.get(source)
    if direct_targets is not None and _target_matches(direct_targets, target):
        return True

    for key, targets in ignore_refs.items():
        if isinstance(key, re.Pattern) and key.search(source) and _target_matches(targets, target):
            return True
        if isinstance(key, str) and key != source:
            try:
                if re.fullmatch(key, source) and _target_matches(targets, target):
                    return True
            except re.error:
                continue
    return False


def _target_matches(targets: set[str] | list[Any] | re.Pattern[str], target: str) -> bool:
    """Return True if ``target`` matches a configured target set, list, or compiled regex."""
    if isinstance(targets, re.Pattern):
        return bool(targets.search(target))
    for item in targets:
        if isinstance(item, re.Pattern) and item.search(target):
            return True
        if item == target:
            return True
    return False


def _should_ignore_offline_reference(
    domain: str,
    ref_type: str,
    target: str,
    module: str,
    reference_target_source_obj: str,
) -> bool:
    """Return True if an external reference should be suppressed in offline mode."""
    if not _is_offline_mode():
        return False
    if domain == "std" and ref_type == "doc" and ":" in target:
        return target.split(":", 1)[0] != "advanced-alchemy"
    if target.startswith("advanced_alchemy"):
        return False
    if "." in target:
        return _resolve_external_runtime_symbol(target)
    if module:
        global_names = get_module_global_imports(module, reference_target_source_obj)
        return target in global_names or hasattr(builtins, target)
    return hasattr(builtins, target)


def _should_ignore_module_typechecking_import(
    target: str,
    module: str,
    reference_target_source_obj: str,
) -> bool:
    """Return True if ``target`` is a verified module TypeVar or TYPE_CHECKING-only import."""
    if not module or target.startswith("advanced_alchemy."):
        return False
    if _resolve_advanced_alchemy_reference(target, module):
        return True
    if reference_target_source_obj and "." not in target:
        global_names = get_module_global_imports(module, reference_target_source_obj)
        return target in global_names and not hasattr(importlib.import_module(module), target)
    return False


def on_warn_missing_reference(app: Sphinx, domain: str, node: Node) -> bool | None:
    """Evaluate unresolved pending_xref nodes against AST imports, ignore rules, and offline mode."""
    if getattr(node, "tagname", None) != "pending_xref" or not hasattr(node, "attributes"):
        return None

    attributes = cast("dict[str, Any]", getattr(node, "attributes", {}))
    target = attributes.get("reftarget")
    if hasattr(target, "__class__") and target.__class__.__name__ in _TYPEVAR_CLASS_NAMES:
        return True
    if not isinstance(target, str):
        return None

    ref_type = str(attributes.get("reftype", ""))
    module = str(attributes.get("py:module", "") or "")
    reference_target_source_obj = str(
        attributes.get("py:class") or attributes.get("py:meth") or attributes.get("py:func") or ""
    )

    if _should_ignore_module_typechecking_import(target, module, reference_target_source_obj):
        return True

    raw_source = get_source_line(node)[0] or ""
    source = raw_source.split(" ")[-1] if raw_source else ""
    raw_ignore = getattr(app.config, "ignore_missing_refs", None)
    ignore_refs = cast(
        "dict[str | re.Pattern[str], set[str] | list[Any] | re.Pattern[str]]",
        raw_ignore or {},
    )
    if _matches_ignore_missing_refs(ignore_refs, source, target) or _should_ignore_offline_reference(
        domain, ref_type, target, module, reference_target_source_obj
    ):
        return True

    return None


def on_missing_reference(app: Sphinx, env: BuildEnvironment, node: pending_xref, contnode: Element) -> Element | None:
    """Resolve missing references across Python domain object types and module-relative aliases."""
    if not hasattr(node, "attributes"):
        return None

    attributes: dict[str, Any] = node.attributes
    target = attributes.get("reftarget")
    if not isinstance(target, str):
        return None

    py_domain = env.domains["py"]
    refdoc = node.get("refdoc", env.docname)

    candidate_targets: list[str] = [target]
    module = attributes.get("py:module")
    if isinstance(module, str) and module and "." not in target:
        candidate_targets.append(f"{module}.{target}")

    for candidate in candidate_targets:
        new_node = py_domain.resolve_xref(env, refdoc, app.builder, "data", candidate, node, contnode)
        if new_node is not None:
            return new_node
        resolved_xrefs = py_domain.resolve_any_xref(env, refdoc, app.builder, candidate, node, contnode)
        for ref in resolved_xrefs:
            if ref:
                return ref[1]

    return None


def setup(app: Sphinx) -> dict[str, bool]:
    """Register Sphinx missing-reference and inventory-alias hooks."""
    _install_python_domain_dual_role_patch()
    _install_autodoc_explicit_members_patch()
    app.connect("autodoc-process-signature", _sanitize_recorded_typehints, priority=600)
    app.connect("env-updated", register_inventory_aliases)
    app.connect("missing-reference", on_missing_reference)
    app.connect("warn-missing-reference", on_warn_missing_reference)
    app.add_config_value("ignore_missing_refs", default={}, rebuild="env")
    return {"parallel_read_safe": True, "parallel_write_safe": True}


def _sanitize_recorded_typehints(
    app: Sphinx,
    objtype: str,
    name: str,
    obj: Any,
    options: Any,
    args: str,
    retann: str,
) -> None:
    """Normalize expanded runtime type aliases in recorded autodoc annotations."""
    del options, args, retann
    annotations = app.env.temp_data.get("annotations", {}).get(name)
    if not isinstance(annotations, dict):
        return
    if objtype == "class" and isinstance(obj, type):
        doc = getattr(obj, "__doc__", "") or ""
        if "Args:" not in doc and "Parameters" not in doc and ":param " not in doc:
            annotations.clear()
            return
    for key, val in list(annotations.items()):
        if isinstance(val, str):
            if "_AbstractLoad" in val:
                annotations[key] = "~advanced_alchemy.repository.LoadSpec | None"
            elif "UnaryExpression" in val and "InstrumentedAttribute" in val:
                annotations[key] = (
                    "list[~advanced_alchemy.repository.OrderingPair] "
                    "| ~advanced_alchemy.repository.OrderingPair | None"
                )
