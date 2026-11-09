"""Multi-version documentation build script for Advanced Alchemy."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import shutil
from pathlib import Path
from typing import TypedDict, cast

from sphinx.cmd.build import build_main

__all__ = (
    "REDIRECT_TEMPLATE",
    "VersionSpec",
    "build",
    "load_version_spec",
    "main",
    "parser",
)

REDIRECT_TEMPLATE = """
<!DOCTYPE HTML>
<html lang="en-US">
    <head>
        <title>Page Redirection</title>
        <meta charset="UTF-8">
        <meta http-equiv="refresh" content="0; url={target}">
        <script type="text/javascript">window.location.href = "{target}"</script>
    </head>
    <body>
        You are being redirected. If this does not work, click <a href='{target}'>this link</a>
    </body>
</html>
"""

parser = argparse.ArgumentParser()
parser.add_argument("--version", required=False)
parser.add_argument("output")


class VersionSpec(TypedDict):
    """Schema for ``docs/_static/versions.json``."""

    versions: list[str]
    """Published documentation version slugs."""
    latest: str
    """Slug pointing to the latest stable version."""


def load_version_spec() -> VersionSpec:
    """Load the published documentation version manifest from ``docs/_static/versions.json``."""
    versions_file = Path("docs/_static/versions.json")
    if versions_file.exists():
        return cast("VersionSpec", json.loads(versions_file.read_text(encoding="utf-8")))
    return {"versions": [], "latest": ""}


def build(output_dir: str, version: str | None) -> None:
    """Build Sphinx HTML documentation and stage versioned output directories."""
    if version is None:
        version = importlib.metadata.version("advanced_alchemy").rsplit(".", 1)[0]
    else:
        os.environ["_ADVANCED_ALCHEMY_DOCS_BUILD_VERSION"] = version

    exit_code = build_main(["-b", "html", "-d", "docs/_build/doctrees", "docs", "docs/_build/html", "-E", "-a"])
    if exit_code != 0:
        msg = f"Sphinx documentation build failed with exit code {exit_code}"
        raise RuntimeError(msg)

    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True, parents=True)
    output_path.joinpath(".nojekyll").touch(exist_ok=True)

    version_spec = load_version_spec()
    is_latest = version == version_spec["latest"]

    docs_src_path = Path("docs/_build/html")

    output_path.joinpath("index.html").write_text(REDIRECT_TEMPLATE.format(target="latest"), encoding="utf-8")

    if is_latest:
        shutil.copytree(docs_src_path, output_path / "latest", dirs_exist_ok=True)
    shutil.copytree(docs_src_path, output_path / version, dirs_exist_ok=True)

    for other_version in [*version_spec["versions"], "latest"]:
        other_version_path = Path(other_version)
        other_version_target_path = output_path / other_version
        if other_version_path.exists() and not other_version_target_path.exists():
            shutil.copytree(other_version_path, other_version_target_path)


def main() -> None:
    """Parse CLI arguments and run the documentation build."""
    args = parser.parse_args()
    build(output_dir=args.output, version=args.version)


if __name__ == "__main__":
    main()
