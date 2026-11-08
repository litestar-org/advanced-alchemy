"""Unit tests for tools.docs.verify_docs_artifacts, Makefile docs targets, and CI workflow gates."""

from __future__ import annotations

import ast
from pathlib import Path
import zlib

import pytest

from tools.docs.verify_docs_artifacts import (
    LITESTAR_REQUIRED_XREFS,
    ArtifactViolation,
    DocsArtifactVerifier,
    DocsBudgetConfig,
    VerificationFinding,
    main,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
BUILD_HTML_DIR = REPO_ROOT / "docs" / "_build" / "html"
DOCS_DIR = REPO_ROOT / "docs"


def _write_synthetic_objects_inv(path: Path, entries: list[tuple[str, str, str, str]]) -> None:
    """Write a valid Sphinx v2 objects.inv file containing the supplied entries."""
    header = (
        "# Sphinx inventory version 2\n"
        "# Project: Advanced Alchemy\n"
        "# Version: 1.0\n"
        "# The remainder of this file is compressed using zlib.\n"
    ).encode("utf-8")
    body_lines = [f"{name} {role} 1 {uri} -\n" for name, role, uri, _disp in entries]
    compressed = zlib.compress("".join(body_lines).encode("utf-8"))
    path.write_bytes(header + compressed)


def test_real_build_passes_docs_artifact_verifier() -> None:
    """Verify the built documentation tree in docs/_build/html passes all artifact checks."""
    verifier = DocsArtifactVerifier(build_dir=BUILD_HTML_DIR, docs_dir=DOCS_DIR)
    violations = verifier.verify_all()
    assert violations == []
    assert main(["--build-dir", str(BUILD_HTML_DIR), "--docs-dir", str(DOCS_DIR)]) == 0


def test_objects_inv_detects_missing_module_and_missing_symbol(tmp_path: Path) -> None:
    """Verify check_objects_inv reports missing public modules and missing __all__ symbols."""
    assert VerificationFinding is ArtifactViolation
    inv_path = tmp_path / "objects.inv"
    _write_synthetic_objects_inv(
        inv_path,
        [
            ("advanced_alchemy.exceptions", "py:module", "reference/exceptions.html", "-"),
            ("advanced_alchemy.exceptions.RepositoryError", "py:exception", "reference/exceptions.html", "-"),
        ],
    )
    config = DocsBudgetConfig(required_public_modules=("advanced_alchemy.exceptions", "advanced_alchemy.base"))
    verifier = DocsArtifactVerifier(build_dir=tmp_path, config=config)
    violations = verifier.check_objects_inv()
    categories = {v.category for v in violations}
    targets = {v.target for v in violations}
    assert "objects.inv" in categories
    assert "advanced_alchemy.base" in targets
    assert "advanced_alchemy.exceptions.NotFoundError" in targets


@pytest.mark.parametrize(
    ("filename", "content", "expected_substring"),
    [
        (
            "llms.txt",
            "# Advanced Alchemy\n\n## Usage Guides\n\n.. autoclass:: Foo\n",
            "Missing section heading '## API Reference'",
        ),
        (
            "llms-full.txt",
            "# Full Docs\n\nSQLAlchemyAsyncRepository\n.. automodule:: advanced_alchemy.base\n",
            "Unexpanded RST directive '.. automodule::'",
        ),
    ],
)
def test_llms_files_detects_unexpanded_directives_and_missing_sections(
    tmp_path: Path,
    filename: str,
    content: str,
    expected_substring: str,
) -> None:
    """Verify check_llms_files flags unexpanded RST directives and missing sections."""
    (tmp_path / "llms.txt").write_text(
        "# Advanced Alchemy\n\n## Usage Guides\n\n## API Reference\n",
        encoding="utf-8",
    )
    (tmp_path / "llms-full.txt").write_text(
        "SQLAlchemyAsyncRepository\nSQLAlchemyAsyncRepositoryService\nalchemy\n",
        encoding="utf-8",
    )
    (tmp_path / filename).write_text(content, encoding="utf-8")

    verifier = DocsArtifactVerifier(build_dir=tmp_path)
    violations = verifier.check_llms_files()
    assert any(expected_substring in v.detail for v in violations)


def test_llms_files_rejects_react_json_chunks(tmp_path: Path) -> None:
    """Verify check_llms_files fails if _static/docs/manifest.json or chunks/ exists."""
    (tmp_path / "llms.txt").write_text("## Usage Guides\n## API Reference\n", encoding="utf-8")
    (tmp_path / "llms-full.txt").write_text(
        "SQLAlchemyAsyncRepository SQLAlchemyAsyncRepositoryService alchemy\n",
        encoding="utf-8",
    )
    static_docs = tmp_path / "_static" / "docs"
    static_docs.mkdir(parents=True)
    (static_docs / "manifest.json").write_text("{}", encoding="utf-8")

    verifier = DocsArtifactVerifier(build_dir=tmp_path)
    violations = verifier.check_llms_files()
    assert any("Forbidden React SPA JSON chunk" in v.detail for v in violations)


def test_html_budgets_and_internal_fragment_checks(tmp_path: Path) -> None:
    """Verify check_html_and_rst_budgets catches oversized pages, TOC overflow, code in headings, and broken anchors."""
    ref_dir = tmp_path / "reference"
    usage_dir = tmp_path / "usage"
    ref_dir.mkdir(parents=True)
    usage_dir.mkdir(parents=True)

    toc_items = "".join(f"<li><a href='#s{i}'>S{i}</a></li>" for i in range(16))
    (ref_dir / "oversized.html").write_text(
        f"<html><body><div class='sy-rside'><ul>{toc_items}</ul></div>" + ("x" * 121_000) + "</body></html>",
        encoding="utf-8",
    )
    (usage_dir / "guide.html").write_text(
        '<html><body><h2 id="valid">Heading with <code>inline_code</code></h2>'
        '<a href="#nonexistent">Broken</a></body></html>',
        encoding="utf-8",
    )

    verifier = DocsArtifactVerifier(build_dir=tmp_path)
    violations = verifier.check_html_and_rst_budgets()
    categories = {v.category for v in violations}
    assert "html-budget" in categories
    assert "toc-budget" in categories
    assert "heading-hygiene" in categories
    assert "broken-fragment" in categories


def test_makefile_and_ci_workflow_gates_configured() -> None:
    """Verify Makefile and .github/workflows/ci.yml include docstring and artifact verification gates."""
    makefile_content = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    assert "DOC_TEST_FILES" not in makefile_content
    assert "docs-update-inventories:" in makefile_content
    assert "tools.docs.scan_public_docstrings" in makefile_content
    assert "tools.docs.verify_docs_artifacts" in makefile_content
    assert "pytest docs/ tests/unit/docs/" in makefile_content

    ci_content = (REPO_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "LITESTAR_DOCS_IGNORE_MISSING_EXAMPLE_OUTPUT" not in ci_content
    assert "tools.docs.scan_public_docstrings" in ci_content
    assert "tools.docs.verify_docs_artifacts" in ci_content
    assert len(LITESTAR_REQUIRED_XREFS) >= 30


@pytest.mark.parametrize(
    ("rel_path", "expected_token"),
    [
        (".agents/bundles/knowledge/workflow.md", "verify_docs_artifacts"),
        (".agents/bundles/knowledge/workflow.md", "scan_public_docstrings"),
        (".agents/bundles/product/product-guidelines.md", "objects.inv"),
        (".agents/bundles/product/product-guidelines.md", "llms-full.txt"),
        ("AGENTS.md", "make docs"),
    ],
)
def test_okf_workflow_and_guidelines_docs_sync(rel_path: str, expected_token: str) -> None:
    """Verify OKF workflow, product guidelines, and AGENTS.md document the Sphinx artifact gates."""
    target_path = REPO_ROOT / rel_path
    if not target_path.is_file():
        pytest.skip(f"Local-only OKF file not present in checkout: {rel_path}")
    content = target_path.read_text(encoding="utf-8")
    assert expected_token in content


def test_verify_docs_artifacts_has_zero_inline_comments() -> None:
    """Verify tools/docs/verify_docs_artifacts.py contains zero inline comments."""
    mod_path = REPO_ROOT / "tools" / "docs" / "verify_docs_artifacts.py"
    raw = mod_path.read_text(encoding="utf-8")
    ast.parse(raw)
    for line in raw.splitlines():
        stripped = line.strip()
        assert not stripped.startswith("#"), f"Inline comment found: {line}"
