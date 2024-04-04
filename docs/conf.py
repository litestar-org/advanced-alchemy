# Configuration file for the Sphinx documentation builder.
from __future__ import annotations

import os
from functools import partial
from typing import TYPE_CHECKING, Any

from advanced_alchemy.__metadata__ import __project__, __version__

if TYPE_CHECKING:
    from sphinx.addnodes import document
    from sphinx.application import Sphinx

# -- Environmental Data ------------------------------------------------------


# -- Project information -----------------------------------------------------
project = __project__
author = "Litestar Organization"
release = __version__
release = os.getenv("_ADVANCED-ALCHEMY_DOCS_BUILD_VERSION", __version__.rsplit(".")[0])
copyright = "2023, Litestar Organization"

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
]

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "msgspec": ("https://jcristharif.com/msgspec/", None),
    "sqlalchemy": ("https://docs.sqlalchemy.org/en/20/", None),
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

todo_include_todos = True

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

# -- Style configuration -----------------------------------------------------
html_theme = "litestar_sphinx_theme"
html_static_path = ["_static"]
html_css_files = ["css/style.css"]
html_show_sourcelink = False
html_title = "Advanced Alchemy"

html_theme_options = {
    "use_page_nav": False,
    "github_repo_name": "advanced-alchemy",
    "logo": {
        "link": "https://docs.advanced-alchemy.litestar.dev",
    },
    "pygment_light_style": "xcode",
    "pygment_dark_style": "lightbulb",
    "navigation_with_keys": True,
    "extra_navbar_items": {
        "Documentation": "index",
        "Community": {
            "Contributing": {
                "description": "Learn how to contribute to the Advanced Alchemy project",
                "link": "https://docs.advanced-alchemy.litestar.dev/latest/contribution-guide.html",
                "icon": "contributing",
            },
            "Code of Conduct": {
                "description": "Review the etiquette for interacting with the Litestar community",
                "link": "https://github.com/litestar-org/.github?tab=coc-ov-file",
                "icon": "coc",
            },
            "Security": {
                "description": "Overview of the Litestar Organization's security protocols",
                "link": "https://github.com/litestar-org/.github?tab=coc-ov-file#security-ov-file",
                "icon": "coc",
            },
        },
        "About": {
            "Litestar Organization": {
                "description": "Details about the Litestar organization",
                "link": "https://litestar.dev/about/organization",
                "icon": "org",
            },
            # TODO: Kind've awkward to do for each repo in this way.
            # "Releases": {
            #     "description": "Explore the release process, versioning, and deprecation policy for Litestar",
            #     "link": "https://litestar.dev/about/litestar-releases",
            #     "icon": "releases",
            # },
        },
        "Release notes": {
            "Changelog": "https://docs.advanced-alchemy.litestar.dev/latest/changelog.html",
        },
        "Help": {
            "Discord Help Forum": {
                "description": "Dedicated Discord help forum",
                "link": "https://discord.gg/litestar-919193495116337154",
                "icon": "coc",
            },
            "GitHub Discussions": {
                "description": "GitHub Discussions ",
                "link": "https://github.com/orgs/litestar-org/discussions",
                "icon": "coc",
            },
            "Stack Overflow": {
                "description": "We monitor the <code><b>litestar</b></code> tag on Stack Overflow",
                "link": "https://stackoverflow.com/questions/tagged/litestar",
                "icon": "coc",
            },
        },
    },
}


def update_html_context(
    app: Sphinx,
    pagename: str,
    templatename: str,
    context: dict[str, Any],
    doctree: document,
) -> None:
    context["generate_toctree_html"] = partial(context["generate_toctree_html"], startdepth=0)


def setup(app: Sphinx) -> dict[str, bool]:
    app.setup_extension("litestar_sphinx_theme")
    app.setup_extension("pydata_sphinx_theme")
    app.connect("html-page-context", update_html_context)

    return {"parallel_read_safe": True, "parallel_write_safe": True}
