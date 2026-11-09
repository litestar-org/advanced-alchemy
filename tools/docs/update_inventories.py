"""Upstream Sphinx objects.inv inventory manager and intersphinx mapping builder."""

from __future__ import annotations

import argparse
import http.client
import io
import os
import sys
from http import HTTPStatus
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urljoin, urlsplit

import msgspec
from sphinx.util.inventory import InventoryFile

if TYPE_CHECKING:
    from collections.abc import Sequence
    from types import TracebackType
    from typing import Self

__all__ = (
    "UPSTREAM_INVENTORIES",
    "InventoryTarget",
    "InventoryUpdater",
)


class InventoryTarget(msgspec.Struct, frozen=True, gc=False):
    """Upstream intersphinx inventory target descriptor."""

    name: str
    base_url: str
    inv_url: str | None = None


UPSTREAM_INVENTORIES: tuple[InventoryTarget, ...] = (
    InventoryTarget("python", "https://docs.python.org/3"),
    InventoryTarget("sqlalchemy", "https://docs.sqlalchemy.org/en/20/"),
    InventoryTarget("alembic", "https://alembic.sqlalchemy.org/en/latest/"),
    InventoryTarget("litestar", "https://docs.litestar.dev/latest/"),
    InventoryTarget("fastapi", "https://fastapi.tiangolo.com/"),
    InventoryTarget("msgspec", "https://msgspec.dev/"),
    InventoryTarget("pydantic", "https://docs.pydantic.dev/latest/"),
    InventoryTarget("attrs", "https://www.attrs.org/en/stable/"),
    InventoryTarget("click", "https://click.palletsprojects.com/en/stable/"),
    InventoryTarget("anyio", "https://anyio.readthedocs.io/en/stable/"),
    InventoryTarget("multidict", "https://multidict.aio-libs.org/en/stable/"),
    InventoryTarget("cryptography", "https://cryptography.io/en/latest/"),
    InventoryTarget("sanic", "https://sanic.readthedocs.io/en/latest/"),
    InventoryTarget("flask", "https://flask.palletsprojects.com/en/stable/"),
    InventoryTarget("typing_extensions", "https://typing-extensions.readthedocs.io/en/stable/"),
    InventoryTarget("pytest", "https://docs.pytest.org/en/stable/"),
    InventoryTarget("fsspec", "https://filesystem-spec.readthedocs.io/en/latest/"),
    InventoryTarget("obstore", "https://developmentseed.org/obstore/latest/"),
    InventoryTarget("dogpile_cache", "https://dogpilecache.sqlalchemy.org/en/latest/"),
    InventoryTarget("dishka", "https://dishka.readthedocs.io/en/stable/"),
    InventoryTarget("opentelemetry", "https://opentelemetry-python.readthedocs.io/en/latest/"),
)


class InventoryUpdater:
    """Fetches, validates, caches, and maps upstream Sphinx objects.inv inventories."""

    __slots__ = ()

    @staticmethod
    def resolve_inventory_url(target: InventoryTarget) -> str:
        """Return the full objects.inv URL for a target."""
        if target.inv_url is not None:
            return target.inv_url
        base = target.base_url if target.base_url.endswith("/") else f"{target.base_url}/"
        return urljoin(base, "objects.inv")

    @staticmethod
    def validate_inventory_bytes(base_url: str, payload: bytes) -> int:
        """Validate a Sphinx v2 inventory payload and return its total symbol count."""
        if not payload.startswith(b"# Sphinx inventory version 2"):
            msg = "Invalid Sphinx inventory v2 header"
            raise ValueError(msg)
        inventory = InventoryFile.load(_ByteStream(payload), base_url, urljoin)
        return sum(len(entries) for entries in inventory.values())

    @classmethod
    def fetch_inventory(cls, target: InventoryTarget, *, timeout: float = 15.0) -> bytes:
        """Download and validate an upstream objects.inv payload over HTTPS."""
        current_url = cls.resolve_inventory_url(target)
        for _ in range(5):
            parsed = urlsplit(current_url)
            if parsed.scheme != "https" or not parsed.netloc:
                msg = f"Unsupported inventory URL scheme for {target.name}: {current_url}"
                raise ValueError(msg)
            path = parsed.path or "/"
            if parsed.query:
                path = f"{path}?{parsed.query}"
            conn = http.client.HTTPSConnection(parsed.netloc, timeout=timeout)
            try:
                conn.request("GET", path, headers={"User-Agent": "advanced-alchemy-docs/1.0"})
                response = conn.getresponse()
                location = response.getheader("Location")
                if (
                    response.status
                    in {
                        HTTPStatus.MOVED_PERMANENTLY,
                        HTTPStatus.FOUND,
                        HTTPStatus.SEE_OTHER,
                        HTTPStatus.TEMPORARY_REDIRECT,
                        HTTPStatus.PERMANENT_REDIRECT,
                    }
                    and location
                ):
                    current_url = urljoin(current_url, location)
                    continue
                if response.status != HTTPStatus.OK:
                    msg = f"HTTP {response.status} fetching inventory for {target.name} from {current_url}"
                    raise OSError(msg)
                payload = response.read()
            finally:
                conn.close()
            cls.validate_inventory_bytes(target.base_url, payload)
            return payload
        msg = f"Too many redirects fetching inventory for {target.name}"
        raise OSError(msg)

    @classmethod
    def update_all(
        cls,
        docs_dir: Path,
        *,
        targets: Sequence[InventoryTarget] = UPSTREAM_INVENTORIES,
        strict: bool = False,
    ) -> dict[str, int]:
        """Download and write validated objects.inv files into docs/_inv/."""
        inv_dir = docs_dir / "_inv"
        inv_dir.mkdir(parents=True, exist_ok=True)
        counts: dict[str, int] = {}
        for target in targets:
            try:
                payload = cls.fetch_inventory(target)
                count = cls.validate_inventory_bytes(target.base_url, payload)
                (inv_dir / f"{target.name}.inv").write_bytes(payload)
                counts[target.name] = count
                sys.stdout.write(f"Updated {target.name}.inv ({count} symbols)\n")
            except (OSError, ValueError) as exc:
                sys.stderr.write(f"Warning: failed to update {target.name}: {exc}\n")
                if strict:
                    raise
        return counts

    @staticmethod
    def build_intersphinx_mapping(
        docs_dir: Path,
        *,
        offline: bool | None = None,
        targets: Sequence[InventoryTarget] = UPSTREAM_INVENTORIES,
    ) -> dict[str, tuple[str, tuple[str | None, ...]]]:
        """Construct Sphinx intersphinx_mapping with local cache preference and offline safety."""
        inv_dir = docs_dir / "_inv"
        if offline is not None:
            is_offline = offline
        else:
            env_flag = os.getenv("_ADVANCED_ALCHEMY_DOCS_OFFLINE", "").strip().lower()
            if env_flag in {"1", "true", "yes"}:
                is_offline = True
            elif env_flag in {"0", "false", "no"}:
                is_offline = False
            else:
                is_offline = not inv_dir.is_dir() or not any(inv_dir.glob("*.inv"))
        mapping: dict[str, tuple[str, tuple[str | None, ...]]] = {}
        for target in targets:
            cached_file = inv_dir / f"{target.name}.inv"
            rel_inv = f"_inv/{target.name}.inv"
            if cached_file.is_file():
                locations: tuple[str | None, ...] = (rel_inv,) if is_offline else (rel_inv, None)
                mapping[target.name] = (target.base_url, locations)
            elif not is_offline:
                mapping[target.name] = (target.base_url, (None,))
        return mapping

    @classmethod
    def main(cls, argv: Sequence[str] | None = None) -> int:
        """Run the command-line upstream inventory updater."""
        parser = argparse.ArgumentParser(description="Update cached Sphinx objects.inv files.")
        parser.add_argument(
            "--docs-dir",
            type=Path,
            default=Path(__file__).resolve().parents[2] / "docs",
            help="Path to the Sphinx docs directory.",
        )
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Fail with non-zero exit code if any upstream inventory download fails.",
        )
        args = parser.parse_args(list(argv) if argv is not None else None)
        try:
            cls.update_all(args.docs_dir, strict=args.strict)
        except (OSError, ValueError):
            return 1
        return 0


class _ByteStream:
    """Readable byte stream adapter satisfying Sphinx's _ReadableStream protocol."""

    __slots__ = ("_buffer",)

    def __init__(self, payload: bytes) -> None:
        self._buffer = io.BytesIO(payload)

    def __enter__(self) -> Self:
        """Enter the stream context manager."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Close the underlying buffer on context exit."""
        self._buffer.close()

    def read(self, size: int = -1) -> bytes:
        """Read up to size bytes from the underlying buffer."""
        return self._buffer.read(size)


if __name__ == "__main__":
    raise SystemExit(InventoryUpdater.main())
