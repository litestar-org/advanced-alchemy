"""Unit tests for tools.docs.scan_public_docstrings and docstring xref hygiene."""

from __future__ import annotations

from pathlib import Path

from tools.docs.scan_public_docstrings import (
    DocstringDiagnostic,
    scan_file,
    scan_package,
)


def test_scan_file_detects_external_ref_leak(tmp_path: Path) -> None:
    """Synthetic class with :ref: docstring triggers external-ref-leak diagnostic."""
    sample = tmp_path / "sample.py"
    sample.write_text(
        'class SampleModel:\n    """See :ref:`metadata_describing` for details."""\n',
        encoding="utf-8",
    )

    diagnostics = scan_file(sample, check_leaks=True, check_overloads=False, check_typeddicts=False)

    assert len(diagnostics) == 1
    assert diagnostics[0] == DocstringDiagnostic(
        file=str(sample),
        line=1,
        symbol="SampleModel",
        category="external-ref-leak",
        message="Docstring on 'SampleModel' contains unresolved ':ref:`metadata_describing`' reference.",
    )


def test_scan_file_detects_overload_docstring(tmp_path: Path) -> None:
    """@overload function with a docstring triggers overload-docstring diagnostic."""
    sample = tmp_path / "overloads.py"
    sample.write_text(
        "from typing import overload\n\n"
        "@overload\n"
        "def get(x: int) -> int:\n"
        '    """Bad overload docstring."""\n'
        "    ...\n",
        encoding="utf-8",
    )

    diagnostics = scan_file(sample, check_leaks=False, check_overloads=True, check_typeddicts=False)

    assert len(diagnostics) == 1
    assert diagnostics[0].category == "overload-docstring"
    assert diagnostics[0].symbol == "get"


def test_scan_file_detects_missing_typeddict_field_docstrings(tmp_path: Path) -> None:
    """Public TypedDict missing inline field docstring triggers missing-typeddict-field-docstring."""
    sample = tmp_path / "td.py"
    sample.write_text(
        "from typing import TypedDict\n\n"
        "class SampleDict(TypedDict):\n"
        "    documented: str\n"
        '    """Documented field."""\n'
        "    undocumented: int\n",
        encoding="utf-8",
    )

    diagnostics = scan_file(sample, check_leaks=False, check_overloads=False, check_typeddicts=True)

    assert len(diagnostics) == 1
    assert diagnostics[0].category == "missing-typeddict-field-docstring"
    assert diagnostics[0].symbol == "SampleDict.undocumented"


def test_advanced_alchemy_public_docstrings_clean() -> None:
    """All public TypedDicts, overloads, and docstrings in advanced_alchemy pass scanner checks."""
    repo_root = Path(__file__).resolve().parents[3]
    diagnostics = scan_package(
        repo_root / "advanced_alchemy",
        check_leaks=True,
        check_overloads=True,
        check_typeddicts=True,
    )

    assert diagnostics == []
