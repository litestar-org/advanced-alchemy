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
    "click": ("https://click.palletsprojects.com/en/8.1.x/", None),
    "anyio": ("https://anyio.readthedocs.io/en/stable/", None),
    "multidict": ("https://multidict.aio-libs.org/en/stable/", None),
    "cryptography": ("https://cryptography.io/en/latest/", None),
}
PY_CLASS = "py:class"
PY_EXC = "py:exc"
PY_RE = r"py:.*"
PY_METH = "py:meth"
PY_ATTR = "py:attr"
PY_OBJ = "py:obj"
PY_FUNC = "py:func"
nitpicky = True
nitpick_ignore = [
    # external library / undocumented external
    (PY_CLASS, "pydantic.main.BaseModel"),
    (PY_CLASS, "Starlette"),
    (PY_CLASS, "HTTPResponse"),
    (PY_CLASS, "sanic.helpers.Default"),
    (PY_CLASS, "sanic_ext.bootstrap.Extend"),
    (PY_CLASS, "sanic_ext.Extnd"),
    (PY_CLASS, "RequestResponseEndpoint"),
    (PY_CLASS, "sanic.Request"),
    (PY_CLASS, "sanic.HTTPResponse"),
    (PY_CLASS, "Default"),
    (PY_CLASS, "TypeDecodersSequence"),
    (PY_CLASS, "Litestar"),
    (PY_CLASS, "T"),
    (PY_CLASS, "ExternalType"),
    (PY_CLASS, "TypeEngine"),
    (PY_CLASS, "UserDefinedType"),
    (PY_CLASS, "_RegistryType"),
    (PY_CLASS, "_orm.Mapper"),
    (PY_CLASS, "_orm.registry"),
    (PY_CLASS, "_schema.MetaData"),
    (PY_CLASS, "MetaData"),
    (PY_CLASS, "_schema.Table"),
    (PY_CLASS, "_types.TypeDecorator"),
    (PY_CLASS, "TypeDecorator"),
    (PY_CLASS, "Dialect"),
    (PY_CLASS, "registry"),
    (PY_CLASS, "ColumnElement"),
    (PY_CLASS, "sqlalchemy.dialects.postgresql.named_types.ENUM"),
    (PY_CLASS, "sqlalchemy.orm.decl_api.DeclarativeMeta"),
    (PY_CLASS, "sqlalchemy.sql.sqltypes.TupleType"),
    (PY_METH, "_types.TypeDecorator.process_bind_param"),
    (PY_METH, "_types.TypeDecorator.process_result_value"),
    (PY_METH, "type_engine"),
    (PY_CLASS, "DeclarativeBase"),
    (PY_FUNC, "_sa.create_engine"),
    (PY_FUNC, "_asyncio.create_async_engine"),
    (PY_CLASS, "RowMapping"),
    (PY_CLASS, "Select"),
    (PY_CLASS, "StatementLambdaElement"),
    (PY_CLASS, "SyncMockRepoT"),
    (PY_CLASS, "CommitStrategy"),
    (PY_CLASS, "AsyncMockRepoT"),
    (PY_CLASS, "Request"),
    (PY_CLASS, "Response"),
    (PY_CLASS, "EmptyType"),
    (PY_CLASS, "FilterTypeT"),
    (PY_CLASS, "AppConfig"),
    (PY_CLASS, "config.app.AppConfig"),
    (PY_CLASS, "Group"),
    (PY_CLASS, "BeforeMessageSendHookHandler"),
    (PY_CLASS, "FieldDefinition"),
    (PY_CLASS, "EngineT"),
    (PY_CLASS, "Engine"),
    (PY_CLASS, "ConnectionT"),
    (PY_CLASS, "SessionT"),
    (PY_CLASS, "SessionMakerT"),
    (PY_CLASS, "AsyncEngine"),
    (PY_CLASS, "AsyncSession"),
    (PY_CLASS, "Session"),
    (PY_CLASS, "Connection"),
    (PY_CLASS, "AsyncConnection"),
    (PY_CLASS, "sessionmaker"),
    (PY_CLASS, "sessionmaker[Session]"),
    (PY_CLASS, "async_sessionmaker"),
    (PY_CLASS, "async_sessionmaker[AsyncSession]"),
    (PY_ATTR, "id_attribute"),
    (PY_CLASS, "ModelT"),
    (PY_CLASS, "NotFoundError"),
    (PY_EXC, "NotFoundError"),
    (PY_CLASS, "Scope"),
    (PY_CLASS, "State"),
    (PY_CLASS, "datastructures.State"),
    (PY_EXC, "ImproperConfigurationError"),
    (PY_CLASS, "Message"),
    (PY_CLASS, "Litestar"),
    (PY_CLASS, "DTOFieldDefinition"),
    (PY_CLASS, "advanced_alchemy.extensions.litestar.plugins._slots_base.SlotsBase"),
    (PY_CLASS, "advanced_alchemy.filters.StatementTypeT"),
    (PY_CLASS, "Default"),
    (PY_CLASS, "bytes-like"),
    (PY_CLASS, "scoped_session"),
    (PY_CLASS, "async_scoped_session"),
    (PY_CLASS, "advanced_alchemy.config.types.CommitStrategy"),
    (PY_CLASS, "advanced_alchemy.repository._util.FilterableRepositoryProtocol"),
    (PY_CLASS, "advanced_alchemy.repository._async.SQLAlchemyAsyncRepositoryProtocol"),
    (PY_CLASS, "advanced_alchemy.repository._async.SQLAlchemyAsyncRepository"),
    (PY_CLASS, "advanced_alchemy.repository._util.FilterableRepository"),
    (PY_CLASS, "advanced_alchemy.repository._sync.SQLAlchemySyncRepositoryProtocol"),
    (PY_CLASS, "advanced_alchemy.repository._sync.SQLAlchemySyncRepository"),
    (PY_CLASS, "advanced_alchemy.repository._async.SQLAlchemyAsyncSlugRepositoryProtocol"),
    (PY_CLASS, "advanced_alchemy.repository._sync.SQLAlchemySyncSlugRepositoryProtocol"),
    (PY_ATTR, "advanced_alchemy.repository.AbstractAsyncRepository.id_attribute"),
    (PY_CLASS, "advanced_alchemy.repository.typing.ModelOrRowMappingT"),
    (PY_CLASS, "advanced_alchemy.service.typing.ModelDTOT"),
    (PY_CLASS, "advanced_alchemy.service._typing.ModelDTOT"),
]
nitpick_ignore_regex = [
    (PY_RE, r"advanced_alchemy.*\.T"),
    (PY_RE, r"advanced_alchemy.*CollectionT"),
    (PY_RE, r"advanced_alchemy\..*ModelT"),
    (PY_RE, r"sanic_ext\..*"),
    (PY_RE, r"starlette\..*"),
    (PY_RE, r"sqlalchemy\..*"),
    (PY_RE, r"serialization\..*"),
    (PY_RE, r"Pool\..*"),
    (PY_RE, r"pydantic\.main*"),
    (PY_RE, r"sanic_ext*"),
    (PY_RE, r"advanced_alchemy\.exceptions\..*Error"),
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
autodoc_type_aliases: dict[str, str] = {}
autodoc_mock_imports = [
    "alembic",
    "sanic_ext.Extend",
    "sanic",
    "litestar",
    "sqlalchemy.ext.asyncio.engine.create_async_engine",
    "_sa.create_engine._sphinx_paramlinks_creator",
    "sqlalchemy.Dialect",
    "sqlalchemy.orm.MetaData",
    "sqlalchemy.orm.strategy_options._AbstractLoad",
    "pydantic.main.BaseModel",
    "sqlalchemy.sql.base.ExecutableOption",
    "sqlalchemy.Connection.in_transaction",
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
    "announcement": "This documentation is currently under development.",
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
