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


def test_config_common_broken_sqlalchemy_xrefs_replaced() -> None:
    """config/common.py replaces broken sqlalchemy.get_engine and Connection.in_transaction xrefs."""
    repo_root = Path(__file__).resolve().parents[3]
    text = (repo_root / "advanced_alchemy" / "config" / "common.py").read_text(encoding="utf-8")

    assert "sqlalchemy.get_engine" not in text
    assert "sqlalchemy.Connection.in_transaction" not in text
    assert "sqlalchemy.Session" not in text
    assert ":func:`sqlalchemy.create_engine`" in text
    assert ":meth:`sqlalchemy.engine.Connection.in_transaction`" in text


def test_config_engine_broken_serialization_xrefs_replaced() -> None:
    """config/engine.py replaces broken .serialization.* and sqlalchemy.get_engine.params.* xrefs."""
    repo_root = Path(__file__).resolve().parents[3]
    text = (repo_root / "advanced_alchemy" / "config" / "engine.py").read_text(encoding="utf-8")

    assert "<.serialization.decode_json>" not in text
    assert "<.serialization.encode_json>" not in text
    assert ":attr:`serialization.decode_json`" not in text
    assert ":attr:`serialization.encode_json`" not in text
    assert "sqlalchemy.get_engine" not in text
    assert ":func:`advanced_alchemy.utils.serialization.decode_json`" in text
    assert ":func:`advanced_alchemy.utils.serialization.encode_json`" in text


def test_flask_extension_ambiguous_config_xrefs_qualified() -> None:
    """extensions/flask/extension.py qualifies SQLAlchemyAsyncConfig and SQLAlchemySyncConfig xrefs."""
    repo_root = Path(__file__).resolve().parents[3]
    text = (repo_root / "advanced_alchemy" / "extensions" / "flask" / "extension.py").read_text(encoding="utf-8")

    assert ":class:`advanced_alchemy.extensions.flask.SQLAlchemyAsyncConfig`" in text
    assert ":class:`advanced_alchemy.extensions.flask.SQLAlchemySyncConfig`" in text

