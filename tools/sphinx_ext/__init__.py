from __future__ import annotations

from typing import TYPE_CHECKING, Dict

from tools.sphinx_ext import changelog, missing_references

if TYPE_CHECKING:
    from sphinx.application import Sphinx


def setup(app: Sphinx) -> Dict[str, bool]:
    ext_config = {}
    ext_config.update(missing_references.setup(app))
    ext_config.update(changelog.setup(app))  # type: ignore[arg-type]

    return ext_config
