"""Tests verifying Sybil documentation doctest coverage configuration."""

from __future__ import annotations

import re
import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS_ROOT = ROOT / "docs"
USAGE_DOCS_ROOT = DOCS_ROOT / "usage"
PYTHON_SNIPPET_PATTERN = re.compile(r"^\.\.\s+(?:code-block::\s+python|testcode::)\s*$", re.MULTILINE)


def test_usage_docs_with_python_examples_are_tracked() -> None:
    """Ensure Sybil executes all usage guides and NON_EXECUTABLE_DOCS is removed."""
    sybil_config = runpy.run_path(str(DOCS_ROOT / "conftest.py"))
    assert "NON_EXECUTABLE_DOCS" not in sybil_config
    executable_patterns = tuple(sybil_config["EXECUTABLE_DOCS"])
    assert "usage/**/*.rst" in executable_patterns
    assert "getting-started.rst" in executable_patterns

    discovered_docs = {
        path.relative_to(DOCS_ROOT).as_posix()
        for path in USAGE_DOCS_ROOT.rglob("*.rst")
        if PYTHON_SNIPPET_PATTERN.search(path.read_text(encoding="utf-8"))
    }
    matched_docs = {
        path.relative_to(DOCS_ROOT).as_posix() for pattern in executable_patterns for path in DOCS_ROOT.glob(pattern)
    }
    assert discovered_docs.issubset(matched_docs)
