"""AST-based public docstring and TypedDict field docstring scanner."""

from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import msgspec

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

__all__ = (
    "DocstringDiagnostic",
    "PublicDocstringScanner",
    "main",
    "scan_file",
    "scan_package",
)

_REF_ROLE_PATTERN = re.compile(r":ref:`([^`]+)`")


class DocstringDiagnostic(msgspec.Struct, frozen=True, gc=False):
    """Static AST diagnostic emitted by tools.docs.scan_public_docstrings."""

    file: str
    line: int
    symbol: str
    category: str
    message: str


class PublicDocstringScanner:
    """AST analyzer checking docstring leaks, overload docstrings, and TypedDict field docs."""

    __slots__ = ("check_leaks", "check_overloads", "check_structs", "check_typeddicts")

    def __init__(
        self,
        *,
        check_leaks: bool = True,
        check_overloads: bool = True,
        check_typeddicts: bool = True,
        check_structs: bool = False,
    ) -> None:
        self.check_leaks = check_leaks
        self.check_overloads = check_overloads
        self.check_typeddicts = check_typeddicts
        self.check_structs = check_structs

    def scan_file(self, path: Path) -> list[DocstringDiagnostic]:
        """Scan a single Python source file for docstring diagnostics."""
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        diagnostics: list[DocstringDiagnostic] = []
        self._visit_node(tree, path=path, parent_name="", diagnostics=diagnostics)
        return diagnostics

    def scan_paths(self, paths: Iterable[Path]) -> list[DocstringDiagnostic]:
        """Scan a collection of files or directories for docstring diagnostics."""
        diagnostics: list[DocstringDiagnostic] = []
        for target in paths:
            if target.is_file() and target.suffix == ".py":
                diagnostics.extend(self.scan_file(target))
            elif target.is_dir():
                for py_file in sorted(target.rglob("*.py")):
                    diagnostics.extend(self.scan_file(py_file))
        return diagnostics

    def _visit_node(
        self,
        node: ast.AST,
        *,
        path: Path,
        parent_name: str,
        diagnostics: list[DocstringDiagnostic],
    ) -> None:
        if isinstance(node, ast.Module):
            if self.check_leaks:
                self._check_docstring_leaks(node, path=path, symbol="<module>", line=1, diagnostics=diagnostics)
            for child in node.body:
                self._visit_node(child, path=path, parent_name="", diagnostics=diagnostics)
            return

        if isinstance(node, ast.ClassDef):
            qualified_name = f"{parent_name}.{node.name}" if parent_name else node.name
            if self.check_leaks:
                self._check_docstring_leaks(
                    node, path=path, symbol=qualified_name, line=node.lineno, diagnostics=diagnostics
                )
            if not node.name.startswith("_"):
                if self.check_typeddicts and self._inherits_from(node, "TypedDict"):
                    self._check_annotated_fields(
                        node,
                        path=path,
                        symbol=qualified_name,
                        category="missing-typeddict-field-docstring",
                        kind_label="TypedDict",
                        diagnostics=diagnostics,
                    )
                if self.check_structs and self._inherits_from(node, "Struct"):
                    self._check_annotated_fields(
                        node,
                        path=path,
                        symbol=qualified_name,
                        category="missing-struct-field-docstring",
                        kind_label="Struct",
                        diagnostics=diagnostics,
                    )
            for child in node.body:
                self._visit_node(child, path=path, parent_name=qualified_name, diagnostics=diagnostics)
            return

        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            qualified_name = f"{parent_name}.{node.name}" if parent_name else node.name
            if self.check_overloads and self._is_overload(node) and ast.get_docstring(node, clean=False) is not None:
                diagnostics.append(
                    DocstringDiagnostic(
                        file=str(path),
                        line=node.lineno,
                        symbol=node.name,
                        category="overload-docstring",
                        message=f"@overload stub '{qualified_name}' must not define a docstring.",
                    )
                )
            if self.check_leaks:
                self._check_docstring_leaks(
                    node, path=path, symbol=qualified_name, line=node.lineno, diagnostics=diagnostics
                )

    @staticmethod
    def _check_docstring_leaks(
        node: ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef,
        *,
        path: Path,
        symbol: str,
        line: int,
        diagnostics: list[DocstringDiagnostic],
    ) -> None:
        docstring = ast.get_docstring(node, clean=False)
        if not docstring:
            return
        for match in _REF_ROLE_PATTERN.finditer(docstring):
            ref_target = match.group(1)
            diagnostics.append(
                DocstringDiagnostic(
                    file=str(path),
                    line=line,
                    symbol=symbol,
                    category="external-ref-leak",
                    message=f"Docstring on '{symbol}' contains unresolved ':ref:`{ref_target}`' reference.",
                )
            )

    @staticmethod
    def _inherits_from(node: ast.ClassDef, target_base: str) -> bool:
        for base in node.bases:
            if isinstance(base, ast.Name) and base.id == target_base:
                return True
            if isinstance(base, ast.Attribute) and base.attr == target_base:
                return True
            if isinstance(base, ast.Subscript):
                val = base.value
                if isinstance(val, ast.Name) and val.id == target_base:
                    return True
                if isinstance(val, ast.Attribute) and val.attr == target_base:
                    return True
        return False

    @staticmethod
    def _is_overload(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
        for dec in node.decorator_list:
            if isinstance(dec, ast.Name) and dec.id == "overload":
                return True
            if isinstance(dec, ast.Attribute) and dec.attr == "overload":
                return True
        return False

    @staticmethod
    def _check_annotated_fields(
        node: ast.ClassDef,
        *,
        path: Path,
        symbol: str,
        category: str,
        kind_label: str,
        diagnostics: list[DocstringDiagnostic],
    ) -> None:
        body = node.body
        for idx, stmt in enumerate(body):
            if not isinstance(stmt, ast.AnnAssign) or not isinstance(stmt.target, ast.Name):
                continue
            field_name = stmt.target.id
            if field_name.startswith("_"):
                continue
            has_inline_doc = False
            if idx + 1 < len(body):
                next_stmt = body[idx + 1]
                if (
                    isinstance(next_stmt, ast.Expr)
                    and isinstance(next_stmt.value, ast.Constant)
                    and isinstance(next_stmt.value.value, str)
                    and bool(next_stmt.value.value.strip())
                ):
                    has_inline_doc = True
            if not has_inline_doc:
                diagnostics.append(
                    DocstringDiagnostic(
                        file=str(path),
                        line=stmt.lineno,
                        symbol=f"{symbol}.{field_name}",
                        category=category,
                        message=(
                            f"Public {kind_label} field '{symbol}.{field_name}' is missing an inline PEP 257 docstring."
                        ),
                    )
                )


def scan_file(
    path: Path,
    *,
    check_leaks: bool = True,
    check_overloads: bool = True,
    check_typeddicts: bool = True,
    check_structs: bool = False,
) -> list[DocstringDiagnostic]:
    """Scan a single Python file for docstring diagnostics."""
    scanner = PublicDocstringScanner(
        check_leaks=check_leaks,
        check_overloads=check_overloads,
        check_typeddicts=check_typeddicts,
        check_structs=check_structs,
    )
    return scanner.scan_file(path)


def scan_package(
    package_dir: Path,
    *,
    check_leaks: bool = True,
    check_overloads: bool = True,
    check_typeddicts: bool = True,
    check_structs: bool = False,
) -> list[DocstringDiagnostic]:
    """Scan a package directory recursively for docstring diagnostics."""
    scanner = PublicDocstringScanner(
        check_leaks=check_leaks,
        check_overloads=check_overloads,
        check_typeddicts=check_typeddicts,
        check_structs=check_structs,
    )
    return scanner.scan_paths([package_dir])


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point for tools.docs.scan_public_docstrings."""
    parser = argparse.ArgumentParser(description="Scan public Python docstrings for Sphinx hygiene issues.")
    parser.add_argument("paths", nargs="*", default=["advanced_alchemy"], help="Files or directories to scan.")
    parser.add_argument("--check-leaks", action="store_true", help="Check for leaked :ref: roles in docstrings.")
    parser.add_argument("--check-overloads", action="store_true", help="Check for docstrings on @overload stubs.")
    parser.add_argument(
        "--check-typeddicts", action="store_true", help="Check for inline PEP 257 docstrings on TypedDict fields."
    )
    parser.add_argument(
        "--check-structs", action="store_true", help="Check for inline PEP 257 docstrings on Struct fields."
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    any_flag = args.check_leaks or args.check_overloads or args.check_typeddicts or args.check_structs
    scanner = PublicDocstringScanner(
        check_leaks=args.check_leaks or not any_flag,
        check_overloads=args.check_overloads or not any_flag,
        check_typeddicts=args.check_typeddicts or not any_flag,
        check_structs=args.check_structs,
    )
    diagnostics = scanner.scan_paths([Path(p) for p in args.paths])
    for item in diagnostics:
        sys.stderr.write(f"{item.file}:{item.line}: [{item.category}] {item.symbol}: {item.message}\n")
    return 1 if diagnostics else 0


if __name__ == "__main__":
    raise SystemExit(main())
