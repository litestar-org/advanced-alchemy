import re
import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS_ROOT = ROOT / "docs"
USAGE_DOCS_ROOT = DOCS_ROOT / "usage"
PYTHON_SNIPPET_PATTERN = re.compile(r"^\.\.\s+(?:code-block::\s+python|testcode::)\s*$", re.MULTILINE)


def test_usage_docs_with_python_examples_are_tracked() -> None:
    """Ensure docs with Python examples are either executable or explicitly classified."""
    sybil_config = runpy.run_path(str(DOCS_ROOT / "conftest.py"))
    executable_docs = set(sybil_config["EXECUTABLE_DOCS"])
    non_executable_docs = set(sybil_config["NON_EXECUTABLE_DOCS"])

    discovered_docs = {
        path.relative_to(DOCS_ROOT).as_posix()
        for path in USAGE_DOCS_ROOT.rglob("*.rst")
        if PYTHON_SNIPPET_PATTERN.search(path.read_text(encoding="utf-8"))
    }

    assert executable_docs.isdisjoint(non_executable_docs)
    assert discovered_docs == executable_docs.union(non_executable_docs)
