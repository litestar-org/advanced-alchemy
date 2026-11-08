"""Parameterized tests for runnable documentation examples under docs/examples/."""

from __future__ import annotations

import importlib
import tokenize
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
EXAMPLES_DIR = REPO_ROOT / "docs" / "examples"


def _discover_example_files() -> list[Path]:
    """Discover all runnable example Python files under docs/examples/."""
    if not EXAMPLES_DIR.exists():
        return []
    return sorted(path for path in EXAMPLES_DIR.rglob("*.py") if path.name != "__init__.py")


def _module_name_for_path(path: Path) -> str:
    """Convert a docs/examples file path into an importable dotted module name."""
    rel = path.relative_to(REPO_ROOT).with_suffix("")
    return ".".join(rel.parts)


EXAMPLE_FILES = _discover_example_files()
EXAMPLE_IDS = [str(path.relative_to(REPO_ROOT)) for path in EXAMPLE_FILES]


def test_examples_directory_non_empty() -> None:
    """Verify at least one runnable example script is discovered in docs/examples/."""
    assert EXAMPLE_FILES


@pytest.mark.parametrize("example_path", EXAMPLE_FILES, ids=EXAMPLE_IDS)
def test_example_module_has_no_inline_comments(example_path: Path) -> None:
    """Ensure runnable example modules contain zero inline or standalone # comments."""
    with example_path.open("rb") as handle:
        tokens = list(tokenize.tokenize(handle.readline))
    comment_tokens = [tok for tok in tokens if tok.type == tokenize.COMMENT]
    assert not comment_tokens, f"Unexpected comments in {example_path}: {comment_tokens}"


@pytest.mark.parametrize("example_path", EXAMPLE_FILES, ids=EXAMPLE_IDS)
def test_example_module_executes_main(example_path: Path) -> None:
    """Import each documentation example module and execute its main() entry point."""
    module_name = _module_name_for_path(example_path)
    module = importlib.import_module(module_name)
    assert hasattr(module, "__all__")
    assert "main" in module.__all__
    main_fn = getattr(module, "main", None)
    assert callable(main_fn)
    main_fn()
