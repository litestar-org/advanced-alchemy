"""Sphinx documentation configuration for Advanced Alchemy."""

from __future__ import annotations

import datetime
import os
import warnings
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy.exc import SAWarning

from advanced_alchemy.__metadata__ import __project__, __version__
from tools.docs.update_inventories import InventoryUpdater

if TYPE_CHECKING:
    from sphinx.application import Sphinx

warnings.filterwarnings("ignore", category=SAWarning)

DOCS_DIR = Path(__file__).resolve().parent
current_year = datetime.datetime.now(tz=datetime.timezone.utc).year
project = __project__
copyright = f"{current_year}, Litestar Organization"
release = os.getenv("_ADVANCED_ALCHEMY_DOCS_BUILD_VERSION", __version__.rsplit(".")[0])
suppress_warnings: list[str] = []

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.autosectionlabel",
    "sphinx.ext.githubpages",
    "sphinx.ext.intersphinx",
    "sphinx.ext.napoleon",
    "sphinx.ext.todo",
    "sphinx.ext.viewcode",
    "tools.sphinx_ext.missing_references",
    "tools.sphinx_ext.changelog",
    "tools.sphinx_ext.llms_txt",
    "myst_parser",
    "auto_pytabs.sphinx_ext",
    "sphinx_copybutton",
    "sphinx_click",
    "sphinx_design",
    "sphinxcontrib.mermaid",
    "sphinx_togglebutton",
]

intersphinx_mapping = InventoryUpdater.build_intersphinx_mapping(DOCS_DIR)
nitpicky = True
nitpick_ignore: list[tuple[str, str]] = [
    ("py:class", "alembic.ddl.impl.DefaultImpl"),
]
nitpick_ignore_regex: list[tuple[str, str]] = []

auto_pytabs_min_version = (3, 9)
auto_pytabs_max_version = (3, 13)

napoleon_google_docstring = True
napoleon_numpy_docstring = False
napoleon_include_special_with_doc = False
napoleon_use_admonition_for_examples = True
napoleon_use_admonition_for_notes = True
napoleon_use_admonition_for_references = False
napoleon_attr_annotations = True
napoleon_use_ivar = True
napoleon_use_param = True
napoleon_use_rtype = True
napoleon_preprocess_types = True

autoclass_content = "class"
autodoc_class_signature = "mixed"
autodoc_default_options = {
    "members": True,
    "show-inheritance": True,
    "special-members": False,
}
autodoc_member_order = "bysource"
autodoc_typehints_format = "short"
autodoc_typehints = "description"
autodoc_typehints_description_target = "documented_params"
autodoc_preserve_defaults = True
python_maximum_signature_line_length = 68
python_use_unqualified_type_names = True
python_display_short_literal_types = True
toc_object_entries = False

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
    "DateTimeUTC": "advanced_alchemy.types.DateTimeUTC",
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
    "EngineConfig": "advanced_alchemy.config.EngineConfig",
    "AsyncSessionConfig": "advanced_alchemy.config.AsyncSessionConfig",
    "SyncSessionConfig": "advanced_alchemy.config.SyncSessionConfig",
    "EmptyType": "advanced_alchemy.utils.dataclass.EmptyType",
    "async_sessionmaker": "sqlalchemy.ext.asyncio.async_sessionmaker",
    "sessionmaker": "sqlalchemy.orm.sessionmaker",
    "SlugMixin": "advanced_alchemy.mixins.SlugKey",
    "UniqueMixin": "advanced_alchemy.mixins.UniqueMixin",
    "AsyncEngine": "sqlalchemy.ext.asyncio.AsyncEngine",
    "Engine": "sqlalchemy.engine.Engine",
    "sqlalchemy": "sqlalchemy",
    "RenameStrategy": "litestar.dto.types.RenameStrategy",
    "Union": "typing.Union",
    "Callable": "typing.Callable",
    "Any": "typing.Any",
    "Optional": "typing.Optional",
    "_EchoFlagType": "advanced_alchemy.config._EchoFlagType",
    "advanced_alchemy.types.encrypted_string.PGCryptoBackend": "advanced_alchemy.types.encrypted_string.PGCryptoBackend",
    "advanced_alchemy.types.password_hash.pwdlib.PwdlibHasher": "advanced_alchemy.types.password_hash.pwdlib.PwdlibHasher",
    "advanced_alchemy.types.password_hash.argon2.Argon2Hasher": "advanced_alchemy.types.password_hash.argon2.Argon2Hasher",
    "advanced_alchemy.types.password_hash.bcrypt.BcryptHasher": "advanced_alchemy.types.password_hash.bcrypt.BcryptHasher",
    "advanced_alchemy.types.password_hash.passlib.PasslibHasher": "advanced_alchemy.types.password_hash.passlib.PasslibHasher",
    "ForUpdateArg": "sqlalchemy.sql.selectable.ForUpdateArg",
    "LoadSpec": "advanced_alchemy.repository.LoadSpec",
    "OrderingPair": "advanced_alchemy.repository.OrderingPair",
}
autodoc_mock_imports: list[str] = []

autosectionlabel_prefix_document = True
autosectionlabel_maxdepth = 2
viewcode_follow_imported_members = False

copybutton_prompt_text = "$ "

html_theme = "shibuya"
html_title = "Advanced Alchemy"
html_short_title = "AA"
llms_txt_base_url = "https://docs.advanced-alchemy.litestar.dev/latest/"

pygments_style = "a11y-light"
pygments_dark_style = "a11y-high-contrast-dark"

todo_include_todos = True

html_static_path = ["_static"]
html_favicon = "_static/favicon.png"
templates_path = ["_templates"]
html_css_files = ["custom.css", "syntax-highlighting.css"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store", "PYPI_README.md", "guides/**", "examples/**"]
html_show_sourcelink = True
html_copy_source = True

html_meta = {
    "description": "Advanced Alchemy - A carefully crafted, thoroughly tested, optimized companion library for SQLAlchemy",
    "keywords": "sqlalchemy, orm, alembic, python, database, litestar, repository-pattern, fastapi, starlette",
    "author": "Litestar Organization",
    "og:title": "Advanced Alchemy Documentation",
    "og:type": "website",
    "og:description": "Advanced Alchemy - A carefully crafted, thoroughly tested, optimized companion library for SQLAlchemy",
    "og:site_name": "Advanced Alchemy",
    "twitter:card": "summary",
}

html_context = {
    "source_type": "github",
    "source_user": "litestar-org",
    "source_repo": "advanced-alchemy",
    "current_version": "latest",
    "version": release,
}

html_theme_options = {
    "logo_target": "/",
    "accent_color": "amber",
    "github_url": "https://github.com/litestar-org/advanced-alchemy",
    "discord_url": "https://discord.gg/dSDXd4mKhp",
    "navigation_with_keys": True,
    "globaltoc_expand_depth": 2,
    "light_logo": "_static/logo-default.png",
    "dark_logo": "_static/logo-default.png",
    "discussion_url": "https://discord.gg/dSDXd4mKhp",
    "nav_links": [
        {
            "title": "Learn",
            "url": "usage/index",
            "children": [
                {"title": "Getting Started", "url": "getting-started", "summary": "Install and configure Advanced Alchemy"},
                {"title": "Data Modeling", "url": "usage/modeling/index", "summary": "Declarative bases, mixins, and custom types"},
                {"title": "Repositories", "url": "usage/repositories/index", "summary": "Async and sync data access and filtering"},
                {"title": "Services", "url": "usage/services", "summary": "Business logic and schema/DTO hydration"},
                {"title": "Replica Routing", "url": "usage/routing", "summary": "Read/write replica session routing"},
                {"title": "Caching", "url": "usage/caching", "summary": "Dogpile L2 query and entity caching"},
                {"title": "CLI & Migrations", "url": "usage/cli", "summary": "Alembic CLI and database workflows"},
            ],
        },
        {
            "title": "Frameworks",
            "url": "usage/frameworks/litestar",
            "children": [
                {"title": "Litestar", "url": "usage/frameworks/litestar", "summary": "Plugin, DI providers, DTOs, and session stores"},
                {"title": "FastAPI", "url": "usage/frameworks/fastapi", "summary": "Extension, lifespan, and Annotated dependencies"},
                {"title": "Starlette", "url": "usage/frameworks/starlette", "summary": "ASGI middleware and request-scoped sessions"},
                {"title": "Sanic", "url": "usage/frameworks/sanic", "summary": "Sanic extension and dependency injection"},
                {"title": "Flask", "url": "usage/frameworks/flask", "summary": "WSGI and async Flask integration"},
            ],
        },
        {"title": "Reference", "url": "reference/index"},
        {
            "title": "About",
            "children": [
                {
                    "title": "Changelog",
                    "url": "changelog",
                    "summary": "All changes for Advanced Alchemy",
                },
                {
                    "title": "Litestar Organization",
                    "summary": "Details about the Litestar organization, the team behind Advanced Alchemy",
                    "url": "https://litestar.dev/about/organization",
                    "icon": "org",
                },
                {
                    "title": "Releases",
                    "summary": "Explore the release process, versioning, and deprecation policy for Advanced Alchemy",
                    "url": "releases",
                    "icon": "releases",
                },
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
                {"title": "Sponsor", "url": "https://github.com/sponsors/Litestar-Org", "icon": "heart"},
            ],
        },
        {
            "title": "Help",
            "children": [
                {
                    "title": "Discord Help Forum",
                    "summary": "Dedicated Discord help forum",
                    "url": "https://discord.gg/dSDXd4mKhp",
                    "icon": "coc",
                },
                {
                    "title": "GitHub Discussions",
                    "summary": "GitHub Discussions",
                    "url": "https://github.com/litestar-org/advanced-alchemy/discussions",
                    "icon": "coc",
                },
            ],
        },
    ],
}


def setup(app: Sphinx) -> dict[str, bool]:
    """Initialize Sphinx theme extension."""
    app.setup_extension("shibuya")
    return {"parallel_read_safe": True, "parallel_write_safe": True}
