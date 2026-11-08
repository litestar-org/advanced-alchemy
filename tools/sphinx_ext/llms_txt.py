"""Sphinx extension and CLI for generating llms.txt and llms-full.txt from resolved doctrees."""

from __future__ import annotations

import argparse
import re
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urljoin

import msgspec
from docutils import nodes
from sphinx import addnodes
from sphinx.application import Sphinx

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sphinx.environment import BuildEnvironment

__all__ = (
    "DoctreeMarkdownRenderer",
    "LlmsConfig",
    "LlmsPageEntry",
    "LlmsSectionGroup",
    "SphinxLlmsGenerator",
    "build_llms_files",
    "main",
    "on_build_finished",
    "setup",
)


class LlmsSectionGroup(msgspec.Struct, frozen=True, gc=False):
    """Section grouping mapping docname prefixes to an llms.txt category."""

    key: str
    title: str
    prefixes: tuple[str, ...]
    exact_docnames: tuple[str, ...] = ()


class LlmsPageEntry(msgspec.Struct, frozen=True, gc=False):
    """Rendered page metadata and Markdown body for llms.txt and llms-full.txt."""

    docname: str
    title: str
    summary: str
    url: str
    section: str
    markdown: str

    @property
    def section_group(self) -> str:
        """Return the section group title for compatibility."""
        return self.section

    @property
    def markdown_body(self) -> str:
        """Return the rendered Markdown body for compatibility."""
        return self.markdown


class LlmsConfig(msgspec.Struct, frozen=True, gc=False):
    """Configuration for Sphinx doctree-to-Markdown llms.txt generation."""

    site_title: str = "Advanced Alchemy"
    site_tagline: str = "A carefully crafted, thoroughly tested, optimized companion library for SQLAlchemy."
    base_url: str = "https://docs.advanced-alchemy.litestar.dev/latest/"
    excluded_docs: frozenset[str] = frozenset({"genindex", "modindex", "py-modindex", "search"})

    @property
    def project_title(self) -> str:
        """Return the site title."""
        return self.site_title

    @property
    def tagline(self) -> str:
        """Return the site tagline."""
        return self.site_tagline

    @property
    def excluded_docnames(self) -> tuple[str, ...]:
        """Return the sorted tuple of excluded document names."""
        return tuple(sorted(self.excluded_docs))


DEFAULT_SECTION_GROUPS: tuple[LlmsSectionGroup, ...] = (
    LlmsSectionGroup(
        key="overview",
        title="Overview & Getting Started",
        prefixes=(),
        exact_docnames=("index", "getting-started", "usage/index"),
    ),
    LlmsSectionGroup(
        key="usage",
        title="Usage Guides",
        prefixes=("usage/",),
        exact_docnames=(),
    ),
    LlmsSectionGroup(
        key="reference",
        title="API Reference",
        prefixes=("reference/",),
        exact_docnames=("reference/index",),
    ),
    LlmsSectionGroup(
        key="project",
        title="Project & Changelog",
        prefixes=(),
        exact_docnames=("changelog", "releases", "contribution-guide"),
    ),
)

_MIN_SUMMARY_LENGTH = 12
_MAX_SUMMARY_LENGTH = 220
_SUMMARY_TRUNCATE_AT = 217
_TOCTREE_ENTRY_LEN = 2
_SKIPPED_BLOCK_NODES = (nodes.comment, nodes.substitution_definition, nodes.target, nodes.raw)


class SphinxLlmsGenerator:
    """Resolved Sphinx Docutils doctree-to-Markdown renderer and llms.txt builder."""

    __slots__ = ("config", "section_groups")

    def __init__(
        self,
        config: LlmsConfig | None = None,
        section_groups: Sequence[LlmsSectionGroup] = DEFAULT_SECTION_GROUPS,
    ) -> None:
        self.config = config or LlmsConfig()
        self.section_groups = tuple(section_groups)

    def resolve_doc_url(self, docname: str) -> str:
        """Resolve a Sphinx document name to its canonical published HTML URL."""
        normalized_base = self.config.base_url.rstrip("/") + "/"
        if docname == "index":
            return normalized_base
        return urljoin(normalized_base, f"{docname}.html")

    def resolve_href(self, refuri: str, current_docname: str = "") -> str:
        """Resolve an internal or external reference URI against the configured base URL."""
        if not refuri:
            return ""
        if refuri.startswith(("http://", "https://", "mailto:")):
            return refuri
        normalized_base = self.config.base_url.rstrip("/") + "/"
        if refuri.startswith("#"):
            base_doc_url = self.resolve_doc_url(current_docname or "index")
            return f"{base_doc_url}{refuri}"
        if current_docname and "/" in current_docname and not refuri.startswith("/"):
            parent_prefix = current_docname.rsplit("/", 1)[0] + "/"
            page_base = urljoin(normalized_base, parent_prefix)
            return urljoin(page_base, refuri)
        return urljoin(normalized_base, refuri.lstrip("/"))

    def resolve_section_group(self, docname: str) -> str:
        """Map a Sphinx docname to its human-readable section group title."""
        for group in self.section_groups:
            if docname in group.exact_docnames:
                return group.title
        for group in self.section_groups:
            if any(docname.startswith(prefix) for prefix in group.prefixes):
                return group.title
        return "Project & Changelog"

    def extract_title_and_summary(
        self,
        doctree: nodes.document,
        fallback_title: str,
    ) -> tuple[str, str]:
        """Extract the primary heading and first descriptive paragraph from a doctree."""
        title = fallback_title
        for title_node in doctree.findall(nodes.title):
            if isinstance(title_node.parent, (nodes.section, nodes.document)):
                candidate = self._clean_whitespace(title_node.astext())
                if candidate:
                    title = candidate
                    break

        summary = ""
        for para in doctree.findall(nodes.paragraph):
            if self._is_inside_admonition_or_table(para):
                continue
            text = self._clean_whitespace(para.astext())
            if text and len(text) >= _MIN_SUMMARY_LENGTH:
                summary = text
                break
        if not summary:
            summary = f"Documentation for {title}."
        if len(summary) > _MAX_SUMMARY_LENGTH:
            summary = summary[:_SUMMARY_TRUNCATE_AT].rstrip() + "..."
        return title, summary

    def render_doctree(self, doctree: nodes.document, docname: str = "") -> str:
        """Render a resolved Sphinx Docutils document tree into clean Markdown."""
        blocks = self._render_block_children(doctree.children, depth=1, docname=docname)
        rendered = "\n\n".join(block for block in blocks if block.strip())
        return re.sub(r"\n{3,}", "\n\n", rendered).strip()

    def collect_ordered_docnames(self, env: BuildEnvironment) -> list[str]:
        """Collect all non-excluded docnames in deterministic toctree order."""
        ordered: list[str] = []
        seen: set[str] = set()
        root_doc = env.config.root_doc or "index"

        def visit(docname: str) -> None:
            if docname in seen or docname in self.config.excluded_docs:
                return
            if docname not in env.found_docs:
                return
            seen.add(docname)
            ordered.append(docname)
            for child in env.toctree_includes.get(docname, []):
                visit(child)

        visit(root_doc)
        for remaining in sorted(env.found_docs):
            if remaining not in seen and remaining not in self.config.excluded_docs:
                seen.add(remaining)
                ordered.append(remaining)
        return ordered

    def build_page_entries(self, app: Sphinx) -> list[LlmsPageEntry]:
        """Build rendered LlmsPageEntry objects for all documents in the Sphinx environment."""
        env: BuildEnvironment | None = getattr(app, "env", None)
        if env is None:
            return []

        entries: list[LlmsPageEntry] = []
        for docname in self.collect_ordered_docnames(env):
            try:
                doctree = env.get_and_resolve_doctree(docname, app.builder)
            except (AttributeError, KeyError, OSError, RuntimeError, TypeError, ValueError):
                doctree = env.get_doctree(docname)
            fallback_title = docname.rsplit("/", 1)[-1].replace("-", " ").replace("_", " ").title()
            if docname == "index":
                fallback_title = self.config.site_title
            title, summary = self.extract_title_and_summary(doctree, fallback_title)
            markdown = self.render_doctree(doctree, docname=docname)
            if not markdown.startswith("# "):
                markdown = f"# {title}\n\n{markdown}".strip()
            entries.append(
                LlmsPageEntry(
                    docname=docname,
                    title=title,
                    summary=summary,
                    url=self.resolve_doc_url(docname),
                    section=self.resolve_section_group(docname),
                    markdown=markdown,
                )
            )
        return entries

    def format_llms_index(self, entries: Sequence[LlmsPageEntry]) -> str:
        """Format the concise llms.txt navigation index following the llms.txt specification."""
        lines: list[str] = [
            f"# {self.config.site_title}",
            "",
            f"> {self.config.site_tagline}",
            "",
            f"Full documentation corpus: {self.resolve_href('llms-full.txt')}",
            "",
        ]
        grouped: dict[str, list[LlmsPageEntry]] = {}
        for entry in entries:
            grouped.setdefault(entry.section, []).append(entry)

        ordered_titles = [group.title for group in self.section_groups]
        for extra_title in grouped:
            if extra_title not in ordered_titles:
                ordered_titles.append(extra_title)

        for section_title in ordered_titles:
            section_entries = grouped.get(section_title, [])
            if not section_entries:
                continue
            lines.append(f"## {section_title}")
            lines.append("")
            lines.extend(f"- [{entry.title}]({entry.url}): {entry.summary}" for entry in section_entries)
            lines.append("")
        return "\n".join(lines).strip() + "\n"

    def format_llms_full(self, entries: Sequence[LlmsPageEntry]) -> str:
        """Format the complete expanded llms-full.txt Markdown corpus."""
        chunks: list[str] = [
            f"# {self.config.site_title} — Complete Documentation",
            "",
            f"> {self.config.site_tagline}",
        ]
        chunks.extend(f"Source: {entry.url}\n\n{entry.markdown}" for entry in entries)
        return "\n\n".join(chunks).strip() + "\n"

    def write_llms_files(
        self,
        app: Sphinx,
        output_dir: Path | None = None,
    ) -> tuple[Path, Path]:
        """Generate and write llms.txt and llms-full.txt to the target output directory."""
        target_dir = output_dir or Path(app.outdir)
        target_dir.mkdir(parents=True, exist_ok=True)
        entries = self.build_page_entries(app)
        llms_txt_path = target_dir / "llms.txt"
        llms_full_path = target_dir / "llms-full.txt"
        llms_txt_path.write_text(self.format_llms_index(entries), encoding="utf-8")
        llms_full_path.write_text(self.format_llms_full(entries), encoding="utf-8")
        return llms_txt_path, llms_full_path

    @classmethod
    def from_sphinx_app(cls, app: Sphinx) -> SphinxLlmsGenerator:
        """Construct a SphinxLlmsGenerator configured from a Sphinx application instance."""
        site_title = getattr(app.config, "html_title", None) or getattr(app.config, "project", "Advanced Alchemy")
        base_url = getattr(
            app.config,
            "llms_txt_base_url",
            "https://docs.advanced-alchemy.litestar.dev/latest/",
        )
        html_meta = getattr(app.config, "html_meta", {}) or {}
        tagline = html_meta.get(
            "description",
            "A carefully crafted, thoroughly tested, optimized companion library for SQLAlchemy.",
        )
        return cls(
            LlmsConfig(
                site_title=str(site_title),
                site_tagline=str(tagline),
                base_url=str(base_url),
            )
        )

    @classmethod
    def on_build_finished(cls, app: Sphinx, exception: Exception | None) -> None:
        """Sphinx build-finished event callback that writes llms.txt and llms-full.txt."""
        if exception is not None:
            return
        builder_name = getattr(app.builder, "name", "")
        if builder_name not in {"html", "dirhtml", "singlehtml", "dummy"}:
            return
        generator = cls.from_sphinx_app(app)
        generator.write_llms_files(app, Path(app.outdir))

    @classmethod
    def build_standalone(
        cls,
        docs_dir: Path,
        output_dir: Path,
        base_url: str | None = None,
    ) -> tuple[Path, Path]:
        """Run a standalone Sphinx dummy build and emit llms.txt and llms-full.txt."""
        docs_path = docs_dir.resolve()
        out_path = output_dir.resolve()
        out_path.mkdir(parents=True, exist_ok=True)
        confoverrides: dict[str, object] = {}
        if base_url is not None:
            confoverrides["llms_txt_base_url"] = base_url
        with tempfile.TemporaryDirectory() as tmp_doctrees:
            app = Sphinx(
                srcdir=str(docs_path),
                confdir=str(docs_path),
                outdir=str(out_path),
                doctreedir=tmp_doctrees,
                buildername="dummy",
                confoverrides=confoverrides,
                status=None,
                warning=None,
            )
            app.build(force_all=True)
            generator = cls.from_sphinx_app(app)
            return generator.write_llms_files(app, out_path)

    def _render_block_children(
        self,
        children: Sequence[nodes.Node],
        *,
        depth: int,
        docname: str,
    ) -> list[str]:
        blocks: list[str] = []
        for child in children:
            rendered = self._render_block_node(child, depth=depth, docname=docname)
            if rendered and rendered.strip():
                blocks.append(rendered.strip())
        return blocks

    def _render_block_node(self, node: nodes.Node, *, depth: int, docname: str) -> str:
        if isinstance(node, _SKIPPED_BLOCK_NODES):
            return ""
        if isinstance(node, nodes.section):
            return self._render_section(node, depth=depth, docname=docname)
        if isinstance(node, (nodes.title, nodes.paragraph)):
            return self._render_title_or_paragraph(node, depth=depth, docname=docname)
        if isinstance(node, nodes.literal_block) or type(node).__name__ == "mermaid":
            return self._render_literal_block(node)
        if isinstance(
            node,
            (nodes.bullet_list, nodes.enumerated_list, nodes.definition_list, nodes.field_list, nodes.table),
        ):
            return self._render_collection_node(node, docname=docname)
        return self._render_structural_node(node, depth=depth, docname=docname)

    def _render_title_or_paragraph(self, node: nodes.Node, *, depth: int, docname: str) -> str:
        text = self._render_inline_children(node.children, docname=docname).strip()
        if isinstance(node, nodes.title):
            heading_prefix = "#" * min(max(depth, 1), 6)
            return f"{heading_prefix} {text}" if text else ""
        return text

    def _render_collection_node(self, node: nodes.Node, *, docname: str) -> str:
        if isinstance(node, nodes.bullet_list):
            return self._render_list(node, ordered=False, docname=docname)
        if isinstance(node, nodes.enumerated_list):
            return self._render_list(node, ordered=True, docname=docname)
        if isinstance(node, nodes.definition_list):
            return self._render_definition_list(node, docname=docname)
        if isinstance(node, nodes.field_list):
            return self._render_field_list(node, docname=docname)
        if isinstance(node, nodes.table):
            return self._render_table(node, docname=docname)
        return ""

    def _render_structural_node(self, node: nodes.Node, *, depth: int, docname: str) -> str:
        if isinstance(node, addnodes.desc):
            return self._render_desc(node, depth=depth, docname=docname)
        if isinstance(node, addnodes.toctree):
            return self._render_toctree_node(node, docname=docname)
        if isinstance(node, nodes.Admonition):
            return self._render_admonition(node, depth=depth, docname=docname)
        if isinstance(node, nodes.block_quote):
            inner = "\n\n".join(self._render_block_children(node.children, depth=depth, docname=docname))
            return self._prefix_blockquote(inner) if inner else ""
        if isinstance(node, (nodes.container, nodes.compound, nodes.Element)):
            return self._render_container(node, depth=depth, docname=docname)
        return ""

    def _render_section(self, section: nodes.section, *, depth: int, docname: str) -> str:
        parts: list[str] = []
        for child in section.children:
            if isinstance(child, nodes.title):
                heading_prefix = "#" * min(max(depth, 1), 6)
                heading_text = self._render_inline_children(child.children, docname=docname).strip()
                if heading_text:
                    parts.append(f"{heading_prefix} {heading_text}")
            else:
                rendered = self._render_block_node(child, depth=depth + 1, docname=docname)
                if rendered and rendered.strip():
                    parts.append(rendered.strip())
        return "\n\n".join(parts)

    def _render_literal_block(self, node: nodes.Node) -> str:
        language = "text"
        if isinstance(node, nodes.Element):
            if type(node).__name__ == "mermaid" or "mermaid" in node.get("classes", []):
                language = "mermaid"
            else:
                lang_attr = node.get("language")
                if isinstance(lang_attr, str) and lang_attr.strip():
                    language = lang_attr.strip()
        code_text = node.astext().rstrip("\n")
        return f"```{language}\n{code_text}\n```"

    def _render_list(
        self,
        list_node: nodes.bullet_list | nodes.enumerated_list,
        *,
        ordered: bool,
        docname: str,
        indent: int = 0,
    ) -> str:
        lines: list[str] = []
        indent_prefix = "  " * indent
        for idx, item in enumerate(list_node.children, start=1):
            if not isinstance(item, nodes.list_item):
                continue
            marker = f"{idx}. " if ordered else "- "
            item_blocks: list[str] = []
            nested_lists: list[str] = []
            for child in item.children:
                if isinstance(child, nodes.bullet_list):
                    nested_lists.append(self._render_list(child, ordered=False, docname=docname, indent=indent + 1))
                elif isinstance(child, nodes.enumerated_list):
                    nested_lists.append(self._render_list(child, ordered=True, docname=docname, indent=indent + 1))
                else:
                    rendered = self._render_block_node(child, depth=4, docname=docname)
                    if rendered:
                        item_blocks.append(rendered)
            first_block = " ".join(block.strip() for block in item_blocks if block.strip())
            if first_block:
                lines.append(f"{indent_prefix}{marker}{first_block}")
            lines.extend(nested for nested in nested_lists if nested)
        return "\n".join(lines)

    def _render_definition_list(self, node: nodes.definition_list, *, docname: str) -> str:
        lines: list[str] = []
        for item in node.findall(nodes.definition_list_item):
            terms = [
                self._render_inline_children(term.children, docname=docname).strip()
                for term in item.children
                if isinstance(term, nodes.term)
            ]
            defs: list[str] = []
            for child in item.children:
                if isinstance(child, nodes.definition):
                    defs.extend(self._render_block_children(child.children, depth=4, docname=docname))
            term_label = ", ".join(t for t in terms if t)
            def_text = " ".join(d for d in defs if d)
            if term_label and def_text:
                lines.append(f"- **{term_label}**: {def_text}")
            elif term_label:
                lines.append(f"- **{term_label}**")
        return "\n".join(lines)

    def _render_field_list(self, node: nodes.field_list, *, docname: str) -> str:
        lines: list[str] = []
        for field in node.children:
            if not isinstance(field, nodes.field):
                continue
            name_node = next((c for c in field.children if isinstance(c, nodes.field_name)), None)
            body_node = next((c for c in field.children if isinstance(c, nodes.field_body)), None)
            if name_node is None or body_node is None:
                continue
            field_name = self._clean_whitespace(name_node.astext())
            body_parts = self._render_block_children(body_node.children, depth=4, docname=docname)
            body_text = "\n  ".join(body_parts)
            if field_name and body_text:
                lines.append(f"- **{field_name}**: {body_text}")
        return "\n".join(lines)

    def _render_table(self, table: nodes.table, *, docname: str) -> str:
        header_rows: list[list[str]] = []
        body_rows: list[list[str]] = []

        for thead in table.findall(nodes.thead):
            header_rows.extend(self._extract_table_row(row, docname=docname) for row in thead.findall(nodes.row))
        for tbody in table.findall(nodes.tbody):
            body_rows.extend(self._extract_table_row(row, docname=docname) for row in tbody.findall(nodes.row))

        if not header_rows and body_rows:
            header_rows = [body_rows.pop(0)]
        if not header_rows:
            return ""

        col_count = max(len(r) for r in [*header_rows, *body_rows])
        if col_count == 0:
            return ""

        def pad_row(cells: list[str]) -> list[str]:
            return cells + [""] * (col_count - len(cells))

        header = pad_row(header_rows[0])
        separator = ["---"] * col_count
        lines = [
            "| " + " | ".join(header) + " |",
            "| " + " | ".join(separator) + " |",
        ]
        for row_cells in header_rows[1:] + body_rows:
            padded = pad_row(row_cells)
            lines.append("| " + " | ".join(padded) + " |")
        return "\n".join(lines)

    def _extract_table_row(self, row: nodes.row, *, docname: str) -> list[str]:
        cells: list[str] = []
        for entry in row.children:
            if not isinstance(entry, nodes.entry):
                continue
            rendered = " ".join(self._render_block_children(entry.children, depth=4, docname=docname))
            cleaned = self._clean_whitespace(rendered).replace("|", r"\|")
            cells.append(cleaned)
        return cells

    def _render_admonition(
        self,
        node: nodes.Admonition,
        *,
        depth: int,
        docname: str,
    ) -> str:
        admonition_title = type(node).__name__.capitalize()
        if admonition_title == "Admonition":
            admonition_title = "Note"
        elif admonition_title == "Seealso":
            admonition_title = "See Also"

        body_children: list[nodes.Node] = []
        admonition_children: Sequence[nodes.Node] = getattr(node, "children", ())
        for child in admonition_children:
            if isinstance(child, nodes.title):
                extracted = self._clean_whitespace(child.astext())
                if extracted:
                    admonition_title = extracted
            else:
                body_children.append(child)

        rendered_blocks = self._render_block_children(
            body_children,
            depth=depth + 1,
            docname=docname,
        )
        if not rendered_blocks:
            return ""
        first_block = f"**{admonition_title}**: {rendered_blocks[0]}"
        combined = "\n\n".join([first_block, *rendered_blocks[1:]])
        return self._prefix_blockquote(combined)

    def _render_desc(self, node: addnodes.desc, *, depth: int, docname: str) -> str:
        domain = str(node.get("domain", "py"))
        objtype = str(node.get("objtype", "object"))
        heading_level = min(max(depth, 3), 5)
        if objtype in {"method", "attribute", "property", "option"}:
            heading_level = min(max(depth + 1, 4), 6)
        heading_prefix = "#" * heading_level

        signatures: list[str] = []
        primary_name = ""
        content_blocks: list[str] = []

        for child in node.children:
            if isinstance(child, addnodes.desc_signature):
                sig_text = self._clean_whitespace(child.astext())
                if sig_text:
                    signatures.append(sig_text)
                if not primary_name:
                    primary_name = self._extract_desc_name(child, fallback=sig_text)
            elif isinstance(child, addnodes.desc_content):
                content_blocks.extend(
                    self._render_block_children(
                        child.children,
                        depth=heading_level + 1,
                        docname=docname,
                    )
                )

        parts: list[str] = []
        if primary_name:
            parts.append(f"{heading_prefix} `{primary_name}`")
        if signatures:
            fence_lang = "python" if domain == "py" else "text"
            sig_body = "\n".join(signatures)
            parts.append(f"```{fence_lang}\n{sig_body}\n```")
        parts.extend(content_blocks)
        return "\n\n".join(parts)

    def _extract_desc_name(self, sig_node: addnodes.desc_signature, *, fallback: str) -> str:
        addname_parts = [n.astext().strip() for n in sig_node.findall(addnodes.desc_addname)]
        name_parts = [n.astext().strip() for n in sig_node.findall(addnodes.desc_name)]
        combined = "".join(addname_parts + name_parts).strip()
        if combined:
            return combined
        raw_ids: object = sig_node.get("ids")
        if isinstance(raw_ids, list) and raw_ids:
            return str(raw_ids[0])
        return fallback

    def _render_toctree_node(self, node: addnodes.toctree, *, docname: str) -> str:
        raw_entries: object = node.get("entries")
        if not isinstance(raw_entries, list):
            return ""
        lines: list[str] = []
        for item in raw_entries:
            if not isinstance(item, tuple) or len(item) != _TOCTREE_ENTRY_LEN:
                continue
            title, target = item
            target_str = str(target)
            if target_str.startswith(("http://", "https://")):
                label = str(title) if title else target_str
                lines.append(f"- [{label}]({target_str})")
            else:
                resolved = self.resolve_href(f"{target_str}.html", current_docname=docname)
                label = (
                    str(title) if title else target_str.rsplit("/", 1)[-1].replace("-", " ").replace("_", " ").title()
                )
                lines.append(f"- [{label}]({resolved})")
        return "\n".join(lines)

    def _render_container(self, node: nodes.Element, *, depth: int, docname: str) -> str:
        raw_classes: Sequence[str] = node.get("classes", [])
        classes: set[str] = {str(c) for c in raw_classes}
        if "sd-tab-item" in classes:
            label = ""
            body_children: list[nodes.Node] = []
            for child in node.children:
                child_classes: set[str] = set()
                if isinstance(child, nodes.Element):
                    child_raw_classes: Sequence[str] = child.get("classes", [])
                    child_classes = {str(c) for c in child_raw_classes}
                if "sd-tab-label" in child_classes:
                    label = self._clean_whitespace(child.astext())
                elif "sd-tab-content" in child_classes and isinstance(child, nodes.Element):
                    body_children.extend(child.children)
                else:
                    body_children.append(child)
            rendered_body = "\n\n".join(self._render_block_children(body_children, depth=depth, docname=docname))
            if label and rendered_body:
                return f"**{label}**\n\n{rendered_body}"
            return rendered_body

        if "sd-card" in classes:
            card_parts = self._render_block_children(node.children, depth=depth, docname=docname)
            return "\n\n".join(card_parts)

        return "\n\n".join(self._render_block_children(node.children, depth=depth, docname=docname))

    def _render_inline_children(self, children: Sequence[nodes.Node], *, docname: str) -> str:
        parts = [self._render_inline_node(child, docname=docname) for child in children]
        joined = "".join(parts)
        return re.sub(r"[ \t]+", " ", joined)

    def _render_inline_node(self, node: nodes.Node, *, docname: str) -> str:
        if isinstance(node, nodes.Text):
            return str(node).replace("¶", "")
        if isinstance(node, (nodes.literal, nodes.title_reference)):
            text = self._clean_whitespace(node.astext())
            return f"`{text}`" if text else ""
        if isinstance(node, (nodes.strong, nodes.emphasis)):
            text = self._render_inline_children(node.children, docname=docname).strip()
            wrapper = "**" if isinstance(node, nodes.strong) else "*"
            return f"{wrapper}{text}{wrapper}" if text else ""
        if isinstance(node, nodes.reference):
            return self._render_reference_node(node, docname=docname)
        if isinstance(node, nodes.Element):
            return self._render_inline_children(node.children, docname=docname)
        return self._clean_whitespace(node.astext())

    def _render_reference_node(self, node: nodes.reference, *, docname: str) -> str:
        raw_ref_classes: Sequence[str] = node.get("classes", [])
        classes: set[str] = {str(c) for c in raw_ref_classes}
        if "headerlink" in classes:
            return ""
        label = self._render_inline_children(node.children, docname=docname).strip() or self._clean_whitespace(
            node.astext()
        )
        refuri = str(node.get("refuri", ""))
        refid = str(node.get("refid", ""))
        target = refuri or (f"#{refid}" if refid else "")
        if not target:
            return label
        resolved = self.resolve_href(target, current_docname=docname)
        return f"[{label}]({resolved})" if label else resolved

    @staticmethod
    def _prefix_blockquote(text: str) -> str:
        lines = text.splitlines()
        return "\n".join(f"> {line}" if line.strip() else ">" for line in lines)

    @staticmethod
    def _clean_whitespace(text: str) -> str:
        return re.sub(r"\s+", " ", text.replace("¶", "")).strip()

    @staticmethod
    def _is_inside_admonition_or_table(node: nodes.Node) -> bool:
        current = node.parent
        while current is not None:
            if isinstance(current, (nodes.Admonition, nodes.table, addnodes.desc)):
                return True
            current = current.parent
        return False


DoctreeMarkdownRenderer = SphinxLlmsGenerator


def on_build_finished(app: Sphinx, exception: Exception | None) -> None:
    """Sphinx build-finished hook delegating to SphinxLlmsGenerator."""
    SphinxLlmsGenerator.on_build_finished(app, exception)


def build_llms_files(
    docs_dir: Path,
    output_dir: Path,
    *,
    base_url: str | None = None,
) -> tuple[Path, Path]:
    """Build llms.txt and llms-full.txt via a standalone Sphinx invocation."""
    return SphinxLlmsGenerator.build_standalone(docs_dir, output_dir, base_url=base_url)


def setup(app: Sphinx) -> dict[str, str | bool]:
    """Register the llms_txt Sphinx extension and configuration values."""
    if "llms_txt_base_url" not in app.config.values:
        app.add_config_value(
            "llms_txt_base_url",
            "https://docs.advanced-alchemy.litestar.dev/latest/",
            "html",
        )
    app.connect("build-finished", on_build_finished)
    return {
        "version": "1.0.0",
        "parallel_read_safe": True,
        "parallel_write_safe": True,
    }


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint for standalone llms.txt and llms-full.txt generation."""
    parser = argparse.ArgumentParser(
        prog="python -m tools.sphinx_ext.llms_txt",
        description="Generate llms.txt and llms-full.txt from resolved Sphinx doctrees.",
    )
    parser.add_argument(
        "--docs-dir",
        type=Path,
        default=Path("docs"),
        help="Path to the Sphinx documentation source directory.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("docs/_build/html"),
        help="Directory where llms.txt and llms-full.txt will be written.",
    )
    parser.add_argument(
        "--base-url",
        type=str,
        default=None,
        help="Optional override for llms_txt_base_url.",
    )
    args = parser.parse_args(argv)
    build_llms_files(args.docs_dir, args.output_dir, base_url=args.base_url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
