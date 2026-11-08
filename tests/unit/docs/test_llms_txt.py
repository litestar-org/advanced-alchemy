"""Unit tests for the resolved Sphinx doctree llms.txt and llms-full.txt generator."""

from __future__ import annotations

from pathlib import Path

from docutils import nodes
import pytest
from sphinx import addnodes

from tools.sphinx_ext.llms_txt import (
    LlmsConfig,
    LlmsPageEntry,
    LlmsSectionGroup,
    SphinxLlmsGenerator,
    main,
)


def test_llms_structs_instantiation() -> None:
    """Verify LlmsSectionGroup, LlmsPageEntry, and LlmsConfig struct fields and properties."""
    group = LlmsSectionGroup("core", "Core API", ("reference/",))
    assert group.key == "core"
    assert group.title == "Core API"
    assert group.prefixes == ("reference/",)

    entry = LlmsPageEntry(
        docname="usage/services",
        title="Services",
        summary="Service layer overview.",
        url="https://docs.advanced-alchemy.litestar.dev/latest/usage/services.html",
        section="Usage Guides",
        markdown="# Services\n\nService layer overview.",
    )
    assert entry.section_group == "Usage Guides"
    assert entry.markdown_body.startswith("# Services")

    config = LlmsConfig(
        site_title="Advanced Alchemy",
        site_tagline="SQLAlchemy companion library.",
    )
    assert config.project_title == "Advanced Alchemy"
    assert config.tagline == "SQLAlchemy companion library."
    assert "search" in config.excluded_docs


def test_doctree_table_conversion_escapes_pipes() -> None:
    """Verify Docutils tables render to GitHub-Flavored Markdown tables with escaped pipes."""
    generator = SphinxLlmsGenerator(LlmsConfig(site_title="Advanced Alchemy", site_tagline="Companion"))
    doc = nodes.document("", nodes.Element())
    table = nodes.table()
    tgroup = nodes.tgroup(cols=2)
    table += tgroup

    thead = nodes.thead()
    header_row = nodes.row()
    for text in ("Column", "Type"):
        entry = nodes.entry()
        entry += nodes.paragraph(text=text)
        header_row += entry
    thead += header_row
    tgroup += thead

    tbody = nodes.tbody()
    body_row = nodes.row()
    for text in ("id", "int | str"):
        entry = nodes.entry()
        entry += nodes.paragraph(text=text)
        body_row += entry
    tbody += body_row
    tgroup += tbody
    doc += table

    rendered = generator.render_doctree(doc)
    assert "| Column | Type |" in rendered
    assert "| --- | --- |" in rendered
    assert r"| id | int \| str |" in rendered


def test_doctree_link_and_admonition_rendering() -> None:
    """Verify relative links resolve against base_url and admonitions render as blockquotes."""
    config = LlmsConfig(
        site_title="Advanced Alchemy",
        site_tagline="Companion",
        base_url="https://docs.advanced-alchemy.litestar.dev/latest/",
    )
    generator = SphinxLlmsGenerator(config)
    doc = nodes.document("", nodes.Element())

    para = nodes.paragraph()
    ref = nodes.reference("", "Repository Guide", refuri="usage/repositories/basics.html")
    para += ref
    doc += para

    warning_node = nodes.warning()
    warning_node += nodes.paragraph(text="Detach cached instances before lazy loading.")
    doc += warning_node

    rendered = generator.render_doctree(doc)
    assert "[Repository Guide](https://docs.advanced-alchemy.litestar.dev/latest/usage/repositories/basics.html)" in rendered
    assert "> **Warning**: Detach cached instances before lazy loading." in rendered


def test_doctree_api_desc_signature_rendering() -> None:
    """Verify sphinx.addnodes.desc renders symbol heading, signature block, and content."""
    generator = SphinxLlmsGenerator(LlmsConfig(site_title="Advanced Alchemy", site_tagline="Companion"))
    doc = nodes.document("", nodes.Element())

    desc = addnodes.desc(domain="py", objtype="class")
    sig = addnodes.desc_signature("", "")
    sig += addnodes.desc_annotation("", "class ")
    sig += addnodes.desc_addname("", "advanced_alchemy.repository.")
    sig += addnodes.desc_name("", "SQLAlchemyAsyncRepository")
    desc += sig

    content = addnodes.desc_content()
    content += nodes.paragraph(text="Asynchronous SQLAlchemy repository.")
    desc += content
    doc += desc

    rendered = generator.render_doctree(doc)
    assert "### `advanced_alchemy.repository.SQLAlchemyAsyncRepository`" in rendered
    assert "```python\nclass advanced_alchemy.repository.SQLAlchemyAsyncRepository\n```" in rendered
    assert "Asynchronous SQLAlchemy repository." in rendered


def test_standalone_cli_generates_llms_files_without_json_chunks(tmp_path: Path) -> None:
    """Verify standalone CLI builds llms.txt and llms-full.txt with zero JSON UI chunk files."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    output_dir = tmp_path / "out"

    (docs_dir / "conf.py").write_text(
        'project = "Advanced Alchemy"\n'
        'extensions = ["tools.sphinx_ext.llms_txt"]\n'
        'llms_txt_base_url = "https://docs.advanced-alchemy.litestar.dev/latest/"\n',
        encoding="utf-8",
    )
    (docs_dir / "index.rst").write_text(
        "Advanced Alchemy\n================\n\nCompanion library for SQLAlchemy.\n\n"
        ".. toctree::\n   :maxdepth: 1\n\n   getting-started\n",
        encoding="utf-8",
    )
    (docs_dir / "getting-started.rst").write_text(
        "Getting Started\n===============\n\nInstall Advanced Alchemy with uv.\n\n"
        ".. code-block:: bash\n\n   uv add advanced-alchemy\n",
        encoding="utf-8",
    )

    exit_code = main(["--docs-dir", str(docs_dir), "--output-dir", str(output_dir)])
    assert exit_code == 0

    llms_txt = output_dir / "llms.txt"
    llms_full_txt = output_dir / "llms-full.txt"
    assert llms_txt.is_file()
    assert llms_full_txt.is_file()

    index_text = llms_txt.read_text(encoding="utf-8")
    full_text = llms_full_txt.read_text(encoding="utf-8")
    assert "# Advanced Alchemy" in index_text
    assert "[Getting Started](https://docs.advanced-alchemy.litestar.dev/latest/getting-started.html)" in index_text
    assert "uv add advanced-alchemy" in full_text
    assert not list(output_dir.rglob("manifest.json"))
    assert not list(output_dir.rglob("chunks"))
