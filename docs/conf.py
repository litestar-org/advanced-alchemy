# Configuration file for the Sphinx documentation builder.
# ruff: noqa: FIX002 PLR0911 ARG001 ERA001
from __future__ import annotations

import os
import warnings
from datetime import datetime
from functools import partial
from typing import TYPE_CHECKING, Any

from sqlalchemy.exc import SAWarning

from advanced_alchemy.__metadata__ import __project__, __version__

if TYPE_CHECKING:
    from typing import Any

    from sphinx.addnodes import document
    from sphinx.application import Sphinx

# -- Environmental Data ------------------------------------------------------
warnings.filterwarnings("ignore", category=SAWarning)

# -- Project information -----------------------------------------------------
current_year = datetime.now().year  # noqa: DTZ005
project = __project__
copyright = f"{current_year}, Litestar Organization"  # noqa: A001
release = os.getenv("_ADVANCED-ALCHEMY_DOCS_BUILD_VERSION", __version__.rsplit(".")[0])
suppress_warnings = [
    "autosectionlabel.*",
    "ref.python",  # TODO: remove when https://github.com/sphinx-doc/sphinx/issues/4961 is fixed
]
# -- General configuration ---------------------------------------------------
extensions = [
    "sphinx.ext.intersphinx",
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.autosectionlabel",
    "sphinx.ext.githubpages",
    "sphinx.ext.viewcode",
    # "sphinx_autodoc_typehints",
    "auto_pytabs.sphinx_ext",
    "tools.sphinx_ext",
    "sphinx_copybutton",
    "sphinx.ext.todo",
    "sphinx.ext.viewcode",
    "sphinx_click",
    "sphinx_toolbox.collapse",
    "sphinx_design",
    "sphinx_togglebutton",
    "sphinx_paramlinks",
]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]
intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "msgspec": ("https://jcristharif.com/msgspec/", None),
    "sqlalchemy": ("https://docs.sqlalchemy.org/en/20/", None),
    "alembic": ("https://alembic.sqlalchemy.org/en/latest/", None),
    "litestar": ("https://docs.litestar.dev/latest/", None),
    "click": ("https://click.palletsprojects.com/en/stable/", None),
    "anyio": ("https://anyio.readthedocs.io/en/stable/", None),
    "multidict": ("https://multidict.aio-libs.org/en/stable/", None),
    "cryptography": ("https://cryptography.io/en/latest/", None),
    "pydantic": ("https://docs.pydantic.dev/latest/", None),
    "sanic": ("https://sanic.readthedocs.io/en/latest/", None),
    "flask": ("https://flask.palletsprojects.com/en/stable/", None),
    "typing_extensions": ("https://typing-extensions.readthedocs.io/en/stable/", None),
}
PY_CLASS = "py:class"
PY_EXC = "py:exc"
PY_RE = r"py:.*"
PY_METH = "py:meth"
PY_ATTR = "py:attr"
PY_OBJ = "py:obj"
PY_FUNC = "py:func"
nitpicky = True
nitpick_ignore: list[str] = []
nitpick_ignore_regex: list[str] = []

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
autodoc_type_aliases = {
    "ModelT": "advanced_alchemy.repository.typing.ModelT",
    "FilterTypeT": "advanced_alchemy.filters.FilterTypeT",
    "StatementTypeT": "advanced_alchemy.filters.StatementTypeT",
    "EngineT": "sqlalchemy.engine.Engine",
    "AsyncEngineT": "sqlalchemy.ext.asyncio.AsyncEngine",
    "SessionT": "sqlalchemy.orm.Session",
    "AsyncSessionT": "sqlalchemy.ext.asyncio.AsyncSession",
    "ConnectionT": "sqlalchemy.engine.Connection",
    "AsyncConnectionT": "sqlalchemy.ext.asyncio.AsyncConnection",
    "Mapper": "sqlalchemy.orm.Mapper",
    "Registry": "sqlalchemy.orm.registry",
    "RegistryType": "sqlalchemy.orm.registry",
    "Table": "sqlalchemy.schema.Table",
    "MetaData": "sqlalchemy.schema.MetaData",
    "FilterableRepository": "advanced_alchemy.repository._util.FilterableRepository",
    "SQLAlchemyAsyncRepositoryProtocol": "advanced_alchemy.repository._async.SQLAlchemyAsyncRepositoryProtocol",
    "SQLAlchemyAsyncRepository": "advanced_alchemy.repository.SQLAlchemyAsyncRepository",
    "SQLAlchemySyncRepositoryProtocol": "advanced_alchemy.repository._sync.SQLAlchemySyncRepositoryProtocol",
    "SQLAlchemySyncRepository": "advanced_alchemy.repository.SQLAlchemySyncRepository",
    "SQLAlchemyAsyncSlugRepositoryProtocol": "advanced_alchemy.repository._async.SQLAlchemyAsyncSlugRepositoryProtocol",
    "SQLAlchemySyncSlugRepositoryProtocol": "advanced_alchemy.repository._sync.SQLAlchemySyncSlugRepositoryProtocol",
    "ModelOrRowMappingT": "advanced_alchemy.repository.ModelOrRowMappingT",
    "ModelDTOT": "advanced_alchemy.service.ModelDTOT",
    "DTOData": "litestar.dto.data_structures.DTOData",
    "InstrumentedAttribute": "sqlalchemy.orm.attributes.InstrumentedAttribute",
    "BaseModel": "pydantic.BaseModel",
    "Struct": "msgspec.Struct",
    "TableArgsType": "sqlalchemy.orm.decl_base._TableArgsType",
    "TypeEngine": "sqlalchemy.types.TypeEngine",
    "DeclarativeBase": "sqlalchemy.orm.DeclarativeBase",
    "UUIDBase": "advanced_alchemy.base.UUIDBase",
    "NanoIDBase": "advanced_alchemy.base.NanoIDBase",
    "BigIntBase": "advanced_alchemy.base.BigIntBase",
    "BigIntAuditBase": "advanced_alchemy.base.BigIntAuditBase",
    "DefaultBase": "advanced_alchemy.base.DefaultBase",
    "SQLQuery": "advanced_alchemy.base.SQLQuery",
    "UUIDv6PrimaryKey": "advanced_alchemy.base.UUIDv6PrimaryKey",
    "UUIDv7PrimaryKey": "advanced_alchemy.base.UUIDv7PrimaryKey",
    "NanoIDPrimaryKey": "advanced_alchemy.base.NanoIDPrimaryKey",
    "BigIntPrimaryKey": "advanced_alchemy.base.BigIntPrimaryKey",
    "CommonTableAttributes": "advanced_alchemy.base.CommonTableAttributes",
    "AuditColumns": "advanced_alchemy.base.AuditColumns",
    "UUIDPrimaryKey": "advanced_alchemy.base.UUIDPrimaryKey",
}
autodoc_mock_imports = [
    "alembic",
    "sanic_ext.Extend",
    "sanic",
    "sqlalchemy.ext.asyncio.engine.create_async_engine",
    "_sa.create_engine._sphinx_paramlinks_creator",
    "sqlalchemy.Dialect",
    "sqlalchemy.orm.MetaData",
    "sqlalchemy.orm.strategy_options._AbstractLoad",
    "sqlalchemy.sql.base.ExecutableOption",
    "sqlalchemy.Connection.in_transaction",
    "sqlalchemy.orm.attributes.InstrumentedAttribute",
    "sqlalchemy.orm.decl_base._TableArgsType",
    "sqlalchemy.orm.DeclarativeBase",
    "litestar.dto.data_structures.DTOData",
    "sqlalchemy.sql.schema._NamingSchemaParameter",
    "sqlalchemy.sql.FromClause",
]


autosectionlabel_prefix_document = True

todo_include_todos = True

templates_path = ["_templates"]
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
    "version": release,
}

html_theme_options = {
    "logo_target": "/",
    "github_repo_name": "Advanced Alchemy",
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
                    "summary": "Review the etiquette for interacting with the Advanced Alchemy community",
                    "url": "https://github.com/litestar-org/.github?tab=coc-ov-file",
                    "icon": "coc",
                },
                {
                    "title": "Security",
                    "summary": "Overview of Advanced Alchemy's security protocols",
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
                    "summary": "Explore the release process, versioning, and deprecation policy for Advanced Alchemy",
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
    _app: Sphinx,
    _pagename: str,
    _templatename: str,
    context: dict[str, Any],
    _doctree: document,
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
