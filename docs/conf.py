# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = "advanced_alchemy"
copyright = "2023, jolt org"
author = "jolt org"

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.autosectionlabel",
    "sphinx.ext.githubpages",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
    "docs.fix_missing_references",
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
html_show_sourcelink = True


templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]


html_theme = "furo"
html_static_path = ["_static"]
