"""Verify Sphinx documentation build artifacts, objects.inv completeness, llms.txt output, and HTML budgets."""

from __future__ import annotations

import argparse
import importlib
import inspect
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote

import msgspec
from sphinx.util.inventory import InventoryFile

from tools.docs.update_inventories import _ByteStream

__all__ = (
    "LITESTAR_REQUIRED_XREFS",
    "UNEXPANDED_RST_DIRECTIVES",
    "ArtifactViolation",
    "DocsArtifactVerifier",
    "DocsBudgetConfig",
    "VerificationFinding",
    "main",
)

UNEXPANDED_RST_DIRECTIVES: tuple[str, ...] = (
    ".. automodule::",
    ".. autoclass::",
    ".. autofunction::",
    ".. autodata::",
    ".. literalinclude::",
    ".. click::",
    ":toctree:",
)

LITESTAR_REQUIRED_XREFS: tuple[tuple[str, str], ...] = (
    ("py:attribute", "advanced_alchemy.extensions.litestar.SQLAlchemyAsyncConfig.before_send_handler"),
    ("py:attribute", "advanced_alchemy.extensions.litestar.SQLAlchemyAsyncConfig.engine_dependency_key"),
    ("py:attribute", "advanced_alchemy.extensions.litestar.SQLAlchemyAsyncConfig.session_dependency_key"),
    ("py:class", "advanced_alchemy.base.BigIntAuditBase"),
    ("py:class", "advanced_alchemy.base.BigIntBase"),
    ("py:class", "advanced_alchemy.base.UUIDAuditBase"),
    ("py:class", "advanced_alchemy.base.UUIDBase"),
    ("py:class", "advanced_alchemy.extensions.litestar.AsyncSessionConfig"),
    ("py:class", "advanced_alchemy.extensions.litestar.EngineConfig"),
    ("py:class", "advanced_alchemy.extensions.litestar.SQLAlchemyAsyncConfig"),
    ("py:class", "advanced_alchemy.extensions.litestar.SQLAlchemyInitPlugin"),
    ("py:class", "advanced_alchemy.extensions.litestar.SQLAlchemyPlugin"),
    ("py:class", "advanced_alchemy.extensions.litestar.SQLAlchemySerializationPlugin"),
    ("py:class", "advanced_alchemy.extensions.litestar.SQLAlchemySyncConfig"),
    ("py:class", "advanced_alchemy.extensions.litestar.SyncSessionConfig"),
    ("py:class", "advanced_alchemy.extensions.litestar.dto.SQLAlchemyDTO"),
    ("py:class", "advanced_alchemy.extensions.litestar.SQLAlchemyDTO"),
    ("py:class", "advanced_alchemy.dto.SQLAlchemyDTO"),
    ("py:class", "advanced_alchemy.extensions.litestar.plugins.SQLAlchemyInitPlugin"),
    ("py:class", "advanced_alchemy.extensions.litestar.plugins.SQLAlchemyPlugin"),
    ("py:class", "advanced_alchemy.extensions.litestar.plugins.SQLAlchemySerializationPlugin"),
    ("py:method", "advanced_alchemy.extensions.litestar.SQLAlchemySerializationPlugin.supports_type"),
    ("py:method", "advanced_alchemy.extensions.litestar.SQLAlchemySerializationPlugin.create_dto_for_type"),
    ("py:class", "advanced_alchemy.repository.SQLAlchemyAsyncRepository"),
    ("py:class", "advanced_alchemy.repository.SQLAlchemySyncRepository"),
    ("py:class", "advanced_alchemy.repository.memory.SQLAlchemyAsyncMockRepository"),
    ("py:class", "advanced_alchemy.repository.memory.SQLAlchemySyncMockRepository"),
    ("py:class", "advanced_alchemy.types.BigIntIdentity"),
    ("py:data", "advanced_alchemy.types.BigIntIdentity"),
    ("py:class", "advanced_alchemy.types.EncryptedString"),
    ("py:class", "advanced_alchemy.types.GUID"),
    ("py:class", "advanced_alchemy.types.JsonB"),
    ("py:data", "advanced_alchemy.types.JsonB"),
    ("py:class", "advanced_alchemy.utils.dataclass.Empty"),
    ("py:class", "advanced_alchemy.config.types.Empty"),
    ("py:class", "advanced_alchemy.config.common.EngineT"),
    ("py:class", "advanced_alchemy.config.common.SessionT"),
    ("py:class", "advanced_alchemy.filters.FilterTypes"),
    ("py:data", "advanced_alchemy.filters.FilterTypes"),
    ("py:function", "advanced_alchemy._listeners.touch_updated_timestamp"),
    ("py:function", "advanced_alchemy.base.touch_updated_timestamp"),
    ("std:doc", "reference/filters"),
)

_HEADING_CODE_PATTERN = re.compile(r"<h([234])\b[^>]*>(?:(?!</h\1>).)*?<code\b[^>]*>.*?</h\1>", re.DOTALL)


class DocsBudgetConfig(msgspec.Struct, frozen=True, gc=False):
    """Numeric and structural budgets enforced by tools.docs.verify_docs_artifacts."""

    max_reference_html_bytes: int = 120_000
    max_usage_html_bytes: int = 160_000
    max_reference_toc_items: int = 14
    max_usage_rst_lines: int = 200
    required_public_modules: tuple[str, ...] = (
        "advanced_alchemy",
        "advanced_alchemy.base",
        "advanced_alchemy.repository",
        "advanced_alchemy.repository.memory",
        "advanced_alchemy.service",
        "advanced_alchemy.filters",
        "advanced_alchemy.operations",
        "advanced_alchemy.exceptions",
        "advanced_alchemy.types",
        "advanced_alchemy.cache",
        "advanced_alchemy.routing",
        "advanced_alchemy.utils",
        "advanced_alchemy.cli",
        "advanced_alchemy.alembic.commands",
        "advanced_alchemy.extensions",
        "advanced_alchemy.extensions.litestar",
        "advanced_alchemy.extensions.fastapi",
        "advanced_alchemy.extensions.flask",
        "advanced_alchemy.extensions.sanic",
        "advanced_alchemy.extensions.starlette",
    )


class ArtifactViolation(msgspec.Struct, frozen=True, gc=False):
    """Single verification violation reported by DocsArtifactVerifier."""

    category: str
    target: str
    detail: str


VerificationFinding = ArtifactViolation


class _HtmlPageInspector(HTMLParser):
    """Extract HTML element IDs, internal href links, and top-level .sy-rside TOC items."""

    __slots__ = (
        "_in_rside",
        "_rside_div_depth",
        "_rside_ul_depth",
        "element_ids",
        "hrefs",
        "top_level_toc_count",
    )

    def __init__(self) -> None:
        super().__init__()
        self.element_ids: set[str] = set()
        self.hrefs: list[str] = []
        self.top_level_toc_count: int = 0
        self._in_rside: bool = False
        self._rside_div_depth: int = 0
        self._rside_ul_depth: int = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = dict(attrs)
        elem_id = attr_map.get("id")
        if elem_id:
            self.element_ids.add(elem_id)
        elem_name = attr_map.get("name")
        if tag == "a" and elem_name:
            self.element_ids.add(elem_name)

        href = attr_map.get("href")
        if href:
            self.hrefs.append(href)

        classes = set((attr_map.get("class") or "").split())
        if not self._in_rside and "sy-rside" in classes:
            self._in_rside = True
            self._rside_div_depth = 1
            self._rside_ul_depth = 0
            return

        if self._in_rside:
            if tag in {"div", "aside"}:
                self._rside_div_depth += 1
            elif tag == "ul":
                self._rside_ul_depth += 1
            elif tag == "li" and self._rside_ul_depth == 1:
                self.top_level_toc_count += 1

    def handle_endtag(self, tag: str) -> None:
        if not self._in_rside:
            return
        if tag in {"div", "aside"}:
            self._rside_div_depth -= 1
            if self._rside_div_depth <= 0:
                self._in_rside = False
        elif tag == "ul" and self._rside_ul_depth > 0:
            self._rside_ul_depth -= 1


class DocsArtifactVerifier:
    """Verify built Sphinx HTML, objects.inv, and llms.txt documentation artifacts."""

    __slots__ = ("build_dir", "config", "docs_dir")

    def __init__(
        self,
        build_dir: Path,
        docs_dir: Path | None = None,
        config: DocsBudgetConfig | None = None,
    ) -> None:
        self.build_dir = build_dir
        self.docs_dir = docs_dir
        self.config = config or DocsBudgetConfig()

    def verify_all(self) -> list[ArtifactViolation]:
        """Run all artifact, inventory, LLM export, and HTML/RST budget checks."""
        violations: list[ArtifactViolation] = []
        violations.extend(self.check_objects_inv())
        violations.extend(self.check_llms_files())
        violations.extend(self.check_html_and_rst_budgets())
        return violations

    def check_objects_inv(self) -> list[ArtifactViolation]:
        """Verify downstream objects.inv module, __all__ symbol, and Litestar alias completeness."""
        violations: list[ArtifactViolation] = []
        inv_path = self.build_dir / "objects.inv"
        if not inv_path.is_file():
            return [ArtifactViolation("objects.inv", str(inv_path), "Missing objects.inv file in build directory.")]

        inv_data = InventoryFile.load(_ByteStream(inv_path.read_bytes()), "", lambda _base, uri: uri)

        py_modules = inv_data.get("py:module", {})
        all_py_symbols: set[str] = set()
        for role, bucket in inv_data.items():
            if role.startswith("py:"):
                all_py_symbols.update(bucket.keys())
            violations.extend(
                ArtifactViolation(
                    "objects.inv",
                    key,
                    f"Double-prefixed inventory entry in {role}: {key}",
                )
                for key in bucket
                if "advanced_alchemy." in key[len("advanced_alchemy.") :]
            )

        for mod_name in self.config.required_public_modules:
            if mod_name not in py_modules:
                violations.append(
                    ArtifactViolation(
                        "objects.inv",
                        mod_name,
                        f"Missing py:module entry for public module {mod_name}",
                    )
                )
            try:
                module = importlib.import_module(mod_name)
            except ImportError:
                continue
            for sym_name in getattr(module, "__all__", ()):
                sym_obj = getattr(module, sym_name, None)
                if inspect.ismodule(sym_obj):
                    continue
                fullname = f"{mod_name}.{sym_name}"
                if fullname not in all_py_symbols:
                    violations.append(
                        ArtifactViolation(
                            "objects.inv",
                            fullname,
                            f"Missing __all__ export {fullname} in objects.inv",
                        )
                    )

        for role, target in LITESTAR_REQUIRED_XREFS:
            if target not in inv_data.get(role, {}):
                violations.append(
                    ArtifactViolation(
                        "objects.inv",
                        f"{role}:{target}",
                        f"Missing required Litestar cross-reference target {target} under {role}",
                    )
                )

        return violations

    def check_llms_files(self) -> list[ArtifactViolation]:
        """Verify llms.txt and llms-full.txt completeness and absence of unexpanded RST or JSON chunks."""
        violations: list[ArtifactViolation] = []
        llms_path = self.build_dir / "llms.txt"
        llms_full_path = self.build_dir / "llms-full.txt"

        for file_path in (llms_path, llms_full_path):
            if not file_path.is_file():
                violations.append(
                    ArtifactViolation("llms.txt", str(file_path), f"Missing required artifact {file_path.name}")
                )
            elif file_path.stat().st_size == 0:
                violations.append(ArtifactViolation("llms.txt", str(file_path), f"Artifact {file_path.name} is empty"))

        if llms_path.is_file() and llms_path.stat().st_size > 0:
            llms_text = llms_path.read_text(encoding="utf-8")
            violations.extend(
                ArtifactViolation(
                    "llms.txt",
                    str(llms_path),
                    f"Missing section heading '{required_section}' in llms.txt",
                )
                for required_section in ("## Usage Guides", "## API Reference")
                if required_section not in llms_text
            )
            violations.extend(
                ArtifactViolation(
                    "llms.txt",
                    str(llms_path),
                    f"Unexpanded RST directive '{directive}' leaked into llms.txt",
                )
                for directive in UNEXPANDED_RST_DIRECTIVES
                if directive in llms_text
            )

        if llms_full_path.is_file() and llms_full_path.stat().st_size > 0:
            full_text = llms_full_path.read_text(encoding="utf-8")
            violations.extend(
                ArtifactViolation(
                    "llms-full.txt",
                    str(llms_full_path),
                    f"Missing expanded symbol '{required_symbol}' in llms-full.txt",
                )
                for required_symbol in ("SQLAlchemyAsyncRepository", "SQLAlchemyAsyncRepositoryService", "alchemy")
                if required_symbol not in full_text
            )
            violations.extend(
                ArtifactViolation(
                    "llms-full.txt",
                    str(llms_full_path),
                    f"Unexpanded RST directive '{directive}' leaked into llms-full.txt",
                )
                for directive in UNEXPANDED_RST_DIRECTIVES
                if directive in full_text
            )

        manifest_json = self.build_dir / "_static" / "docs" / "manifest.json"
        chunks_dir = self.build_dir / "_static" / "docs" / "chunks"
        if manifest_json.exists() or chunks_dir.exists():
            violations.append(
                ArtifactViolation(
                    "llms.txt",
                    str(self.build_dir / "_static" / "docs"),
                    "Forbidden React SPA JSON chunk artifacts detected under _static/docs/",
                )
            )

        return violations

    def check_html_and_rst_budgets(self) -> list[ArtifactViolation]:
        """Verify HTML byte budgets, .sy-rside TOC counts, RST line counts, headings, and #fragment anchors."""
        violations: list[ArtifactViolation] = []
        attr_viewcode_dir = self.build_dir / "_modules" / "attr"
        if attr_viewcode_dir.exists():
            violations.append(
                ArtifactViolation(
                    "viewcode",
                    str(attr_viewcode_dir),
                    "Third-party _modules/attr/ viewcode output must not be emitted",
                )
            )

        page_ids: dict[Path, set[str]] = {}
        page_hrefs: dict[Path, list[str]] = {}

        for html_file in sorted(self.build_dir.rglob("*.html")):
            rel_parts = html_file.relative_to(self.build_dir).parts
            if rel_parts and rel_parts[0] in {"_static", "_modules"}:
                continue

            raw_html = html_file.read_text(encoding="utf-8", errors="ignore")
            inspector = _HtmlPageInspector()
            inspector.feed(raw_html)
            resolved_html = html_file.resolve()
            page_ids[resolved_html] = inspector.element_ids
            page_hrefs[resolved_html] = inspector.hrefs

            size_bytes = html_file.stat().st_size
            if rel_parts and rel_parts[0] == "reference":
                if size_bytes > self.config.max_reference_html_bytes:
                    violations.append(
                        ArtifactViolation(
                            "html-budget",
                            str(html_file),
                            f"Reference HTML size {size_bytes} exceeds {self.config.max_reference_html_bytes} bytes",
                        )
                    )
                if inspector.top_level_toc_count > self.config.max_reference_toc_items:
                    violations.append(
                        ArtifactViolation(
                            "toc-budget",
                            str(html_file),
                            f"Reference TOC count {inspector.top_level_toc_count} exceeds {self.config.max_reference_toc_items}",
                        )
                    )
            elif rel_parts and rel_parts[0] == "usage":
                if size_bytes > self.config.max_usage_html_bytes:
                    violations.append(
                        ArtifactViolation(
                            "html-budget",
                            str(html_file),
                            f"Usage HTML size {size_bytes} exceeds {self.config.max_usage_html_bytes} bytes",
                        )
                    )
                if _HEADING_CODE_PATTERN.search(raw_html):
                    violations.append(
                        ArtifactViolation(
                            "heading-hygiene",
                            str(html_file),
                            "Usage guide h2/h3/h4 headings must not contain inline <code> tags",
                        )
                    )

        violations.extend(self._check_internal_fragments(page_ids, page_hrefs))
        violations.extend(self._check_rst_source_files())
        return violations

    def _check_rst_source_files(self) -> list[ArtifactViolation]:
        """Verify RST line budgets and forbid fragile :lines: ranges in literalinclude directives."""
        if self.docs_dir is None or not self.docs_dir.is_dir():
            return []
        violations: list[ArtifactViolation] = []
        rst_candidates = list((self.docs_dir / "usage").rglob("*.rst"))
        getting_started = self.docs_dir / "getting-started.rst"
        if getting_started.is_file():
            rst_candidates.append(getting_started)
        for rst_file in sorted(rst_candidates):
            text = rst_file.read_text(encoding="utf-8")
            line_count = len(text.splitlines())
            if line_count > self.config.max_usage_rst_lines:
                violations.append(
                    ArtifactViolation(
                        "rst-budget",
                        str(rst_file),
                        f"Usage RST line count {line_count} exceeds {self.config.max_usage_rst_lines} lines",
                    )
                )
            if ":lines:" in text:
                violations.append(
                    ArtifactViolation(
                        "literalinclude",
                        str(rst_file),
                        "Use :pyobject: or :start-at:/:end-before: instead of fragile :lines: in literalinclude",
                    )
                )
        return violations

    def _check_internal_fragments(
        self,
        page_ids: dict[Path, set[str]],
        page_hrefs: dict[Path, list[str]],
    ) -> list[ArtifactViolation]:
        """Verify that every internal HTML href with a #fragment resolves to an existing id attribute."""
        violations: list[ArtifactViolation] = []
        build_root = self.build_dir.resolve()

        for src_page, hrefs in page_hrefs.items():
            for href in hrefs:
                if href.startswith(("http://", "https://", "mailto:", "javascript:")) or "#" not in href:
                    continue
                path_part, _, fragment = href.partition("#")
                fragment = unquote(fragment)
                if not fragment:
                    continue
                if not path_part:
                    target_page = src_page
                else:
                    clean_path = path_part.split("?", 1)[0]
                    candidate = (src_page.parent / clean_path).resolve()
                    if candidate.is_dir():
                        candidate = (candidate / "index.html").resolve()
                    elif not candidate.suffix and candidate.with_suffix(".html").is_file():
                        candidate = candidate.with_suffix(".html").resolve()
                    target_page = candidate

                try:
                    target_page.relative_to(build_root)
                except ValueError:
                    continue

                rel_target = target_page.relative_to(build_root).parts
                if rel_target and rel_target[0] in {"_static", "_modules"}:
                    continue

                if target_page not in page_ids:
                    if not target_page.is_file():
                        violations.append(
                            ArtifactViolation(
                                "broken-link",
                                str(src_page),
                                f"Internal link '{href}' points to missing page {target_page}",
                            )
                        )
                    continue

                if fragment not in page_ids[target_page]:
                    violations.append(
                        ArtifactViolation(
                            "broken-fragment",
                            str(src_page),
                            f"Internal fragment '#{fragment}' in '{href}' not found in {target_page.name}",
                        )
                    )

        return violations


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for verifying built Sphinx documentation artifacts."""
    parser = argparse.ArgumentParser(description="Verify Sphinx documentation artifacts and budgets.")
    parser.add_argument("--build-dir", type=Path, default=Path("docs/_build/html"))
    parser.add_argument("--docs-dir", type=Path, default=Path("docs"))
    args = parser.parse_args(argv)

    verifier = DocsArtifactVerifier(build_dir=args.build_dir, docs_dir=args.docs_dir)
    violations = verifier.verify_all()
    if violations:
        for violation in violations:
            sys.stderr.write(f"[{violation.category}] {violation.target}: {violation.detail}\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
