from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from docutils.nodes import Element
    from sphinx.addnodes import pending_xref
    from sphinx.application import Sphinx
    from sphinx.environment import BuildEnvironment


def on_missing_reference(app: Sphinx, env: BuildEnvironment, node: pending_xref, contnode: Element) -> Any:
    if not hasattr(node, "attributes"):
        return None

    attributes = node.attributes  # type: ignore[attr-defined]
    target = attributes["reftarget"]
    py_domain = env.domains["py"]

    # autodoc sometimes incorrectly resolves these types, so we try to resolve them as py:data fist and fall back to any
    new_node = py_domain.resolve_xref(env, node["refdoc"], app.builder, "data", target, node, contnode)
    if new_node is None:
        resolved_xrefs = py_domain.resolve_any_xref(env, node["refdoc"], app.builder, target, node, contnode)
        for ref in resolved_xrefs:
            if ref:
                return ref[1]
    return new_node


def setup(app: Sphinx) -> dict[str, bool]:
    app.connect("missing-reference", on_missing_reference)
    app.add_config_value("ignore_missing_refs", default={}, rebuild=False)

    return {"parallel_read_safe": True, "parallel_write_safe": True}
