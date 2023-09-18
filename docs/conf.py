# Configuration file for the Sphinx documentation builder.
import os

from advanced_alchemy.__metadata__ import __project__ as project
from advanced_alchemy.__metadata__ import __version__ as version

# -- Environmental Data ------------------------------------------------------


# -- Project information -----------------------------------------------------
project = project
author = "Jolt Org"
release = version
release = os.getenv("_ADVANCED-ALCHEMY_DOCS_BUILD_VERSION", version.rsplit(".")[0])
copyright = "2023, Jolt Org"

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
html_theme = "shibuya"
html_static_path = ["_static"]
html_css_files = ["css/custom.css"]
html_show_sourcelink = True
html_title = "Docs"
html_favicon = "_static/logo.png"
html_logo = "_static/logo.png"
html_context = {
    "source_type": "github",
    "source_user": "jolt-org",
    "source_repo": project.replace("_", "-"),
}

brand_colors = {
    "--brand-primary": {"rgb": "245, 0, 87", "hex": "#f50057"},
    "--brand-secondary": {"rgb": "32, 32, 32", "hex": "#202020"},
    "--brand-tertiary": {"rgb": "161, 173, 161", "hex": "#A1ADA1"},
    "--brand-green": {"rgb": "0, 245, 151", "hex": "#00f597"},
    "--brand-alert": {"rgb": "243, 96, 96", "hex": "#f36060"},
    "--brand-dark": {"rgb": "0, 0, 0", "hex": "#000000"},
    "--brand-light": {"rgb": "235, 221, 221", "hex": "#ebdddd"},
}

html_theme_options = {
    "logo_target": "/",
    "announcement": "This documentation is currently under development.",
    "github_url": "https://github.com/jolt-org/advanced-alchemy",
    "nav_links": [
        {"title": "Home", "url": "https://advanced-alchemy.jolt.rs"},
        {"title": "Docs", "url": "https://docs.advanced-alchemy.jolt.rs"},
        {"title": "Code", "url": "https://github.com/jolt-org/advanced-alchemy"},
    ],
    "light_css_variables": {
        # RGB
        "--sy-rc-theme": brand_colors["--brand-primary"]["rgb"],
        "--sy-rc-text": brand_colors["--brand-primary"]["rgb"],
        "--sy-rc-invert": brand_colors["--brand-primary"]["rgb"],
        # "--sy-rc-bg": brand_colors["--brand-secondary"]["rgb"],
        # Hex
        "--sy-c-link": brand_colors["--brand-secondary"]["hex"],
        # "--sy-c-foot-bg": "#191919",
        "--sy-c-foot-divider": brand_colors["--brand-primary"]["hex"],
        "--sy-c-foot-text": brand_colors["--brand-dark"]["hex"],
        "--sy-c-bold": brand_colors["--brand-primary"]["hex"],
        "--sy-c-heading": brand_colors["--brand-primary"]["hex"],
        "--sy-c-text-weak": brand_colors["--brand-primary"]["hex"],
        "--sy-c-text": brand_colors["--brand-dark"]["hex"],
        "--sy-c-bg-weak": brand_colors["--brand-dark"]["rgb"],
    },
    "dark_css_variables": {
        # RGB
        "--sy-rc-theme": brand_colors["--brand-primary"]["rgb"],
        "--sy-rc-text": brand_colors["--brand-primary"]["rgb"],
        "--sy-rc-invert": brand_colors["--brand-primary"]["rgb"],
        "--sy-rc-bg": brand_colors["--brand-dark"]["rgb"],
        # Hex
        "--sy-c-link": brand_colors["--brand-primary"]["hex"],
        "--sy-c-foot-bg": brand_colors["--brand-dark"]["hex"],
        "--sy-c-foot-divider": brand_colors["--brand-primary"]["hex"],
        "--sy-c-foot-text": brand_colors["--brand-light"]["hex"],
        "--sy-c-bold": brand_colors["--brand-primary"]["hex"],
        "--sy-c-heading": brand_colors["--brand-primary"]["hex"],
        "--sy-c-text-weak": brand_colors["--brand-primary"]["hex"],
        "--sy-c-text": brand_colors["--brand-light"]["hex"],
        "--sy-c-bg-weak": brand_colors["--brand-dark"]["hex"],
        "--sy-c-bg": brand_colors["--brand-primary"]["hex"],
    },
}
