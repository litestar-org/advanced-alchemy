# Configuration file for the Sphinx documentation builder.
from __future__ import annotations

import os
import warnings
from datetime import datetime
from functools import partial
from typing import TYPE_CHECKING, Any

from sqlalchemy.exc import SAWarning

from advanced_alchemy.__metadata__ import __project__, __version__

if TYPE_CHECKING:
    from sphinx.addnodes import document
    from sphinx.application import Sphinx

# -- Environmental Data ------------------------------------------------------
warnings.filterwarnings("ignore", category=SAWarning)

# -- Project information -----------------------------------------------------
current_year = datetime.now().year  # noqa: DTZ005
project = __project__
copyright = f"{current_year}, Litestar Organization"
release = os.getenv("_ADVANCED-ALCHEMY_DOCS_BUILD_VERSION", __version__.rsplit(".")[0])

# -- General configuration ---------------------------------------------------
extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.autosectionlabel",
    "sphinx.ext.githubpages",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
    "docs.fix_missing_references",
    "sphinx_copybutton",
    "sphinx.ext.todo",
    "sphinx.ext.viewcode",
    "sphinx_click",
    "sphinx_toolbox.collapse",
    "sphinx_design",
    "sphinx_togglebutton",
    "sphinx_paramlinks",
]

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "msgspec": ("https://jcristharif.com/msgspec/", None),
    "sqlalchemy": ("https://docs.sqlalchemy.org/en/20/", None),
    "alembic": ("https://alembic.sqlalchemy.org/en/latest/", None),
    "litestar": ("https://docs.litestar.dev/latest/", None),
    "click": ("https://click.palletsprojects.com/en/8.1.x/", None),
}
PY_CLASS = "py:class"
PY_RE = r"py:.*"
PY_METH = "py:meth"
PY_ATTR = "py:attr"
PY_OBJ = "py:obj"

nitpicky = True
nitpick_ignore = [
    # external library / undocumented external
    (PY_CLASS, "ExternalType"),
    (PY_CLASS, "TypeEngine"),
    (PY_CLASS, "UserDefinedType"),
    (PY_CLASS, "_RegistryType"),
    (PY_CLASS, "_orm.Mapper"),
    (PY_CLASS, "_orm.registry"),
    (PY_CLASS, "_schema.MetaData"),
    (PY_CLASS, "_schema.Table"),
    (PY_CLASS, "_types.TypeDecorator"),
    (PY_CLASS, "sqlalchemy.dialects.postgresql.named_types.ENUM"),
    (PY_CLASS, "sqlalchemy.orm.decl_api.DeclarativeMeta"),
    (PY_CLASS, "sqlalchemy.sql.sqltypes.TupleType"),
    (PY_METH, "_types.TypeDecorator.process_bind_param"),
    (PY_METH, "_types.TypeDecorator.process_result_value"),
    (PY_METH, "type_engine"),
    # type vars and aliases / intentionally undocumented
    (PY_CLASS, "CollectionT"),
    (PY_CLASS, "EmptyType"),
    (PY_CLASS, "ModelT"),
    (PY_CLASS, "T"),
    (PY_CLASS, "advanced_alchemy.repository.typing.ModelT"),
    (PY_CLASS, "AsyncSession"),
    (PY_CLASS, "Select"),
    (PY_CLASS, "StatementLambdaElement"),
    (PY_CLASS, "SyncMockRepoT"),
    (PY_CLASS, "AsyncMockRepoT"),
    (PY_ATTR, "AsyncGenericMockRepository.id_attribute"),
]
nitpick_ignore_regex = [
    (PY_RE, r"advanced_alchemy.*\.T"),
    (PY_RE, r"advanced_alchemy.*CollectionT"),
    (PY_RE, r"advanced_alchemy\..*ModelT"),
]

napoleon_google_docstring = True
napoleon_include_special_with_doc = True
napoleon_use_admonition_for_examples = True
napoleon_use_admonition_for_notes = True
napoleon_use_admonition_for_references = False
napoleon_attr_annotations = True

autoclass_content = "class"
autodoc_class_signature = "separated"
autodoc_default_options = {"special-members": "__init__", "show-inheritance": True, "members": True}
autodoc_member_order = "bysource"
autodoc_typehints_format = "short"
autodoc_type_aliases = {"FilterTypes": "FilterTypes"}

autosectionlabel_prefix_document = True
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

# -- Style configuration -----------------------------------------------------
html_theme = "litestar_sphinx_theme"
html_title = "Advanced Alchemy"
pygments_style = "lightbulb"
todo_include_todos = True

html_static_path = ["_static"]
templates_path = ["_templates"]
html_js_files = ["versioning.js"]
html_css_files = ["style.css"]

html_show_sourcelink = True
html_copy_source = True

html_context = {
    "source_type": "github",
    "source_user": "litestar-org",
    "source_repo": "advanced-alchemy",
    "current_version": "latest",
    "versions": [
        ("latest", "/latest"),
        ("development", "/main"),
    ],
    "version": release,
}

html_theme_options = {
    "logo_target": "/",
    "github_repo_name": "advanced-alchemy",
    "github_url": "https://github.com/litestar-org/advanced-alchemy",
    "navigation_with_keys": True,
    "nav_links": [  # TODO(provinzkraut): I need a guide on extra_navbar_items and its magic :P
        {"title": "Home", "url": "index"},
        {
            "title": "Community",
            "children": [
                {
                    "title": "Contributing",
                    "summary": "Learn how to contribute to the Advanced Alchemy project",
                    "url": "contribution-guide",
                    "icon": "contributing",
                },
                {
                    "title": "Code of Conduct",
                    "summary": "Review the etiquette for interacting with the Litestar community",
                    "url": "https://github.com/litestar-org/.github?tab=coc-ov-file",
                    "icon": "coc",
                },
                {
                    "title": "Security",
                    "summary": "Overview of Litestar's security protocols",
                    "url": "https://github.com/litestar-org/.github?tab=coc-ov-file#security-ov-file",
                    "icon": "coc",
                },
            ],
        },
        {
            "title": "About",
            "children": [
                {
                    "title": "Litestar Organization",
                    "summary": "Details about the Litestar organization",
                    "url": "https://litestar.dev/about/organization",
                    "icon": "org",
                },
                {
                    "title": "Releases",
                    "summary": "Explore the release process, versioning, and deprecation policy for Litestar",
                    "url": "releases",
                    "icon": "releases",
                },
            ],
        },
        {
            "title": "Release notes",
            "children": [
                {
                    "title": "Changelog",
                    "url": "changelog",
                    "summary": "All changes for Advanced Alchemy",
                },
            ],
        },
        {
            "title": "Help",
            "children": [
                {
                    "title": "Discord Help Forum",
                    "summary": "Dedicated Discord help forum",
                    "url": "https://discord.gg/litestar",
                    "icon": "coc",
                },
                {
                    "title": "GitHub Discussions",
                    "summary": "GitHub Discussions",
                    "url": "https://github.com/litestar-org/advanced-alchemy/discussions",
                    "icon": "coc",
                },
                {
                    "title": "Stack Overflow",
                    "summary": "We monitor the <code><b>litestar</b></code> tag on Stack Overflow",
                    "url": "https://stackoverflow.com/questions/tagged/litestar",
                    "icon": "coc",
                },
            ],
        },
        {"title": "Sponsor", "url": "https://github.com/sponsors/Litestar-Org", "icon": "heart"},
    ],
}


def update_html_context(
    app: Sphinx,
    pagename: str,
    templatename: str,
    context: dict[str, Any],
    doctree: document,
) -> None:
    context["generate_toctree_html"] = partial(context["generate_toctree_html"], startdepth=0)


def delayed_setup(app: Sphinx) -> None:
    """When running linkcheck Shibuya causes a build failure, and checking
    the builder in the initial `setup` function call is not possible, so the check
    and extension setup has to be delayed until the builder is initialized.
    """
    if app.builder.name == "linkcheck":
        return

    app.setup_extension("shibuya")


def setup(app: Sphinx) -> dict[str, bool]:
    app.connect("builder-inited", delayed_setup, priority=0)
    app.setup_extension("litestar_sphinx_theme")
    return {"parallel_read_safe": True, "parallel_write_safe": True}
