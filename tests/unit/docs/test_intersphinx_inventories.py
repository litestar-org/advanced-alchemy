"""Unit tests for upstream intersphinx inventory caching and mapping generation."""

from __future__ import annotations

import zlib
from pathlib import Path

import pytest

from tools.docs.update_inventories import (
    UPSTREAM_INVENTORIES,
    InventoryTarget,
    InventoryUpdater,
)

REPO_ROOT = Path(__file__).resolve().parents[3]

EXPECTED_INVENTORY_NAMES = frozenset(
    {
        "python",
        "sqlalchemy",
        "alembic",
        "litestar",
        "fastapi",
        "msgspec",
        "pydantic",
        "attrs",
        "click",
        "anyio",
        "multidict",
        "cryptography",
        "sanic",
        "flask",
        "typing_extensions",
        "pytest",
        "fsspec",
        "obstore",
        "dogpile_cache",
        "dishka",
        "opentelemetry",
    }
)


def _make_valid_inventory_bytes() -> bytes:
    header = (
        b"# Sphinx inventory version 2\n"
        b"# Project: Python\n"
        b"# Version: 3.13\n"
        b"# The remainder of this file is compressed using zlib.\n"
    )
    body = zlib.compress(b"builtins.str py:class 1 library/stdtypes.html#$ -\n")
    return header + body


def test_upstream_inventories_catalog_completeness() -> None:
    """Verify all 21 upstream ecosystems are registered as frozen msgspec Structs."""
    assert len(UPSTREAM_INVENTORIES) == 21
    names = {target.name for target in UPSTREAM_INVENTORIES}
    assert names == EXPECTED_INVENTORY_NAMES
    by_name = {target.name: target for target in UPSTREAM_INVENTORIES}
    assert isinstance(by_name["msgspec"], InventoryTarget)
    assert by_name["msgspec"].base_url == "https://msgspec.dev/"
    assert by_name["python"].base_url == "https://docs.python.org/3"


def test_build_intersphinx_mapping_cached_and_offline_modes(tmp_path: Path) -> None:
    """Verify cached local .inv files take priority and uncached remotes are skipped offline."""
    inv_dir = tmp_path / "_inv"
    inv_dir.mkdir(parents=True)
    (inv_dir / "python.inv").write_bytes(_make_valid_inventory_bytes())

    online_mapping = InventoryUpdater.build_intersphinx_mapping(tmp_path, offline=False)
    assert online_mapping["python"] == ("https://docs.python.org/3", ("_inv/python.inv", None))
    assert online_mapping["obstore"][1] == (None,)

    offline_mapping = InventoryUpdater.build_intersphinx_mapping(tmp_path, offline=True)
    assert offline_mapping["python"] == ("https://docs.python.org/3", ("_inv/python.inv",))
    assert "obstore" not in offline_mapping


@pytest.mark.parametrize(
    "invalid_payload",
    [
        b"",
        b"<html>403 Forbidden</html>",
        b"# Sphinx inventory version 1\n",
    ],
)
def test_validate_inventory_bytes_rejects_invalid_header(invalid_payload: bytes) -> None:
    """Verify invalid or HTML error payloads raise ValueError."""
    with pytest.raises(ValueError, match="Invalid Sphinx inventory v2 header"):
        InventoryUpdater.validate_inventory_bytes("python", invalid_payload)


def test_validate_inventory_bytes_accepts_valid_v2_payload() -> None:
    """Verify valid zlib-compressed Sphinx v2 inventory bytes parse cleanly."""
    payload = _make_valid_inventory_bytes()
    symbol_count = InventoryUpdater.validate_inventory_bytes("python", payload)
    assert symbol_count >= 1


def test_gitignore_ignores_cached_inventories() -> None:
    """Verify .gitignore excludes cached docs/_inv/*.inv files."""
    gitignore_text = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "docs/_inv/*.inv" in gitignore_text
