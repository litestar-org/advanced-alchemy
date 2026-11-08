"""Custom Sphinx extensions for Advanced Alchemy documentation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from tools.sphinx_ext import changelog, missing_references

if TYPE_CHECKING:
    from sphinx.application import Sphinx

__all__ = ("setup",)


def setup(app: Sphinx) -> dict[str, str | bool]:
    """Initialize custom Sphinx extensions for changelog directives and xref resolution."""
    ext_config: dict[str, str | bool] = {}
    ext_config.update(missing_references.setup(app))
    ext_config.update(changelog.setup(app))
    return ext_config
