"""Unit tests for Sphinx docs/conf.py configuration and Shibuya CSS contracts."""

from __future__ import annotations

import ast
import io
import runpy
import tokenize
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
CONF_PATH = REPO_ROOT / "docs" / "conf.py"
CUSTOM_CSS_PATH = REPO_ROOT / "docs" / "_static" / "custom.css"
BUILD_DOCS_PATH = REPO_ROOT / "tools" / "build_docs.py"
CONVERT_DOCS_PATH = REPO_ROOT / "tools" / "convert_docs.sh"


@pytest.fixture(scope="module")
def conf_globals() -> dict[str, object]:
    """Execute docs/conf.py in an isolated namespace."""
    return runpy.run_path(str(CONF_PATH))


def test_sphinx_conf_clears_blanket_suppressions_and_mocks(conf_globals: dict[str, object]) -> None:
    """Verify blanket warning and mock suppressions and sphinx_autodoc_typehints are removed."""
    assert conf_globals["suppress_warnings"] == []
    assert conf_globals["autodoc_mock_imports"] == []
    extensions = conf_globals["extensions"]
    assert isinstance(extensions, list)
    assert "sphinx_autodoc_typehints" not in extensions
    assert "sphinxcontrib.mermaid" in extensions
    assert "update_html_context" not in conf_globals


@pytest.mark.parametrize(
    ("setting_name", "expected_value"),
    [
        ("autosectionlabel_maxdepth", 2),
        ("viewcode_follow_imported_members", False),
        ("autodoc_default_options", {"members": True, "show-inheritance": True, "special-members": False}),
        ("autodoc_typehints", "description"),
        ("python_maximum_signature_line_length", 68),
        ("python_use_unqualified_type_names", True),
        ("python_display_short_literal_types", True),
        ("napoleon_numpy_docstring", False),
        ("napoleon_use_ivar", True),
        ("napoleon_use_param", True),
        ("napoleon_use_rtype", True),
        ("napoleon_preprocess_types", True),
        ("nitpick_ignore", [("py:class", "alembic.ddl.impl.DefaultImpl")]),
    ],
)
def test_sphinx_conf_autodoc_and_napoleon_settings(
    conf_globals: dict[str, object],
    setting_name: str,
    expected_value: object,
) -> None:
    """Verify Autodoc, Napoleon, viewcode, and autosectionlabel settings match litestar-docs."""
    assert conf_globals[setting_name] == expected_value


def test_sphinx_conf_nav_links_and_version_env(
    monkeypatch: pytest.MonkeyPatch,
    conf_globals: dict[str, object],
) -> None:
    """Verify Shibuya task-oriented nav_links and _ADVANCED_ALCHEMY_DOCS_BUILD_VERSION env var."""
    theme_options = conf_globals["html_theme_options"]
    assert isinstance(theme_options, dict)
    nav_links = theme_options["nav_links"]
    assert isinstance(nav_links, list)
    assert [item["title"] for item in nav_links] == ["Learn", "Frameworks", "Reference", "About", "Help"]

    aliases = conf_globals["autodoc_type_aliases"]
    assert isinstance(aliases, dict)
    assert aliases["SlugMixin"] == "advanced_alchemy.mixins.SlugKey"

    monkeypatch.setenv("_ADVANCED_ALCHEMY_DOCS_BUILD_VERSION", "9.9")
    reloaded = runpy.run_path(str(CONF_PATH))
    assert reloaded["release"] == "9.9"


def test_sphinx_conf_has_no_inline_comments() -> None:
    """Verify docs/conf.py contains zero inline # comments."""
    source = CONF_PATH.read_text(encoding="utf-8")
    comments = [
        tok.string for tok in tokenize.generate_tokens(io.StringIO(source).readline) if tok.type == tokenize.COMMENT
    ]
    assert comments == []


def test_shibuya_custom_css_layout_and_link_contracts() -> None:
    """Verify docs/_static/custom.css enforces Shibuya layout, sapphire links, and scoped code pills."""
    css = CUSTOM_CSS_PATH.read_text(encoding="utf-8")
    assert ".sy-rside" in css
    assert "display: block !important;" in css
    assert "visibility: visible !important;" in css
    assert ".sy-content" in css
    assert "max-width: 46rem !important;" in css
    assert "margin-inline: auto;" in css
    assert "#1d4ed8" in css
    assert "#60a5fa" in css
    assert "text-underline-offset: 0.18em;" in css
    assert "border: none;" in css
    assert "a > code.literal" in css


def test_build_docs_cleanup_and_convert_docs_removed() -> None:
    """Verify tools/convert_docs.sh is deleted and tools/build_docs.py has no dead checkout or comments."""
    assert not CONVERT_DOCS_PATH.exists()

    source = BUILD_DOCS_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    func_names = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
    assert "checkout" not in func_names
    assert "_ADVANCED_ALCHEMY_DOCS_BUILD_VERSION" in source
    comments = [
        tok.string for tok in tokenize.generate_tokens(io.StringIO(source).readline) if tok.type == tokenize.COMMENT
    ]
    assert comments == []


def test_pyproject_includes_tools_and_docs_in_mypy_and_pyright() -> None:
    """pyproject.toml includes tools and docs in mypy packages and pyright include."""
    pyproject_text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert '"tools"' in pyproject_text
    assert '"docs"' in pyproject_text
    assert '"docs/conftest.py"' not in pyproject_text
    assert 'include = ["advanced_alchemy", "tools", "docs"]' in pyproject_text
