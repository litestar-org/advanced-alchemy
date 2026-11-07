"""Unit tests for Sphinx docs/conf.py configuration and Shibuya CSS contracts."""

from __future__ import annotations

import io
import runpy
import tokenize
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
CONF_PATH = REPO_ROOT / "docs" / "conf.py"


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
        tok.string
        for tok in tokenize.generate_tokens(io.StringIO(source).readline)
        if tok.type == tokenize.COMMENT
    ]
    assert comments == []
