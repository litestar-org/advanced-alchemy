"""Helpers for installing the Google ADK Alembic migration template."""

from pathlib import Path
from shutil import copyfile

_TEMPLATE_NAME = "0001_create_adk_tables.py.template"
_REVISION_NAME = "0001_adk_v1_create_adk_tables.py"


def copy_adk_template(versions_dir: Path) -> Path:
    """Copy the ADK v1 migration template into an Alembic versions directory."""
    versions_dir.mkdir(parents=True, exist_ok=True)
    existing = sorted(versions_dir.glob("0001_adk_v1*.py"))
    if existing:
        msg = f"ADK migration already exists: {existing[0]}"
        raise FileExistsError(msg)

    template_path = Path(__file__).parent / "versions" / _TEMPLATE_NAME
    destination = versions_dir / _REVISION_NAME
    copyfile(template_path, destination)
    return destination


__all__ = ("copy_adk_template",)
