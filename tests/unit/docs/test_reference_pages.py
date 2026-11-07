"""Unit tests for curated Sphinx API reference pages, HTML byte budgets, and TOC limits."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urljoin

import pytest
from sphinx.util.inventory import InventoryFile

from tools.docs.update_inventories import _ByteStream

REPO_ROOT = Path(__file__).resolve().parents[3]
REFERENCE_DIR = REPO_ROOT / "docs" / "reference"
BUILD_HTML_DIR = REPO_ROOT / "docs" / "_build" / "html"
BUILD_REFERENCE_DIR = BUILD_HTML_DIR / "reference"
MAX_REFERENCE_HTML_BYTES = 120_000
MAX_TOC_ITEMS = 14


def _extract_h2_headings(rst_text: str) -> list[str]:
    """Return H2 section titles underlined with ``---`` in a reStructuredText document."""
    lines = rst_text.splitlines()
    headings: list[str] = []
    for idx in range(1, len(lines)):
        underline = lines[idx].strip()
        title = lines[idx - 1].strip()
        if title and len(underline) >= len(title) and set(underline) == {"-"}:
            headings.append(title)
    return headings


def _count_rside_toc_items(html_text: str) -> int:
    """Return the number of ``<li>`` items rendered inside the Shibuya ``.sy-rside`` local TOC."""
    match = re.search(r'<aside[^>]*class="[^"]*sy-rside[^"]*"[^>]*>(.*?)</aside>', html_text, re.DOTALL)
    if match is None:
        return 0
    return len(re.findall(r"<li\b", match.group(1)))


@pytest.mark.parametrize(
    "page",
    [
        "repository.rst",
        "repository_memory.rst",
        "service.rst",
        "filters.rst",
        "operations.rst",
        "exceptions.rst",
        "base.rst",
        "types.rst",
        "cache.rst",
    ],
)
def test_repository_and_service_reference_directive_hygiene(page: str) -> None:
    """Verify curated reference pages use H2 categories and explicit directives."""
    content = (REFERENCE_DIR / page).read_text(encoding="utf-8")
    h2_headings = _extract_h2_headings(content)
    assert 2 <= len(h2_headings) <= 5
    assert ":no-inherited-members:" in content
    assert ":imported-members:" not in content
    assert ":undoc-members:" not in content
    assert ":no-index:" not in content


def test_exceptions_reference_contains_qualified_sqlalchemy_xrefs() -> None:
    """Verify docs/reference/exceptions.rst includes qualified SQLAlchemy exception cross-references."""
    content = (REFERENCE_DIR / "exceptions.rst").read_text(encoding="utf-8")
    assert ":exc:`sqlalchemy.exc.IntegrityError`" in content
    assert ":exc:`sqlalchemy.exc.OperationalError`" in content


def test_base_module_and_classes_present_in_objects_inv() -> None:
    """Verify removing :no-index: from base.rst restores advanced_alchemy.base and UUIDBase in objects.inv."""
    inv_path = BUILD_HTML_DIR / "objects.inv"
    assert inv_path.is_file()
    inventory = InventoryFile.load(_ByteStream(inv_path.read_bytes()), "https://example.com/", urljoin)
    assert "advanced_alchemy.base" in inventory.get("py:module", {})
    assert "advanced_alchemy.base.UUIDBase" in inventory.get("py:class", {})


@pytest.mark.parametrize(
    "html_page",
    [
        "repository.html",
        "repository_memory.html",
        "service.html",
        "filters.html",
        "operations.html",
        "exceptions.html",
        "base.html",
        "types.html",
        "cache.html",
    ],
)
def test_repository_and_service_built_html_and_toc_budgets(html_page: str) -> None:
    """Verify built HTML pages stay within the 120 KB byte budget and 14-item right-rail TOC cap."""
    html_path = BUILD_REFERENCE_DIR / html_page
    assert html_path.is_file(), f"Missing built HTML file: {html_path}"
    size_bytes = html_path.stat().st_size
    assert size_bytes <= MAX_REFERENCE_HTML_BYTES, f"{html_page} is {size_bytes} B (> {MAX_REFERENCE_HTML_BYTES} B)"

    html_text = html_path.read_text(encoding="utf-8")
    toc_items = _count_rside_toc_items(html_text)
    assert 1 <= toc_items <= MAX_TOC_ITEMS, f"{html_page} has {toc_items} TOC items (expected 1..{MAX_TOC_ITEMS})"
