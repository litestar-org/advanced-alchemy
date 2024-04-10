from __future__ import annotations

from pathlib import Path
from typing import Any

from anyio import Path as AsyncPath

from advanced_alchemy._serialization import decode_json


def open_fixture(fixtures_path: Path | AsyncPath, fixture_name: str) -> Any:
    """Loads JSON file with the specified fixture name

    Args:
        fixtures_path (Path): The path to look for fixtures
        fixture_name (str): The fixture name to load.

    Raises:
        FileNotFoundError: Fixtures not found.

    Returns:
        Any: The parsed JSON data
    """
    fixture = Path(fixtures_path / f"{fixture_name}.json")
    if fixture.exists():
        with fixture.open(mode="r", encoding="utf-8") as f:
            f_data = f.read()
        return decode_json(f_data)
    msg = f"Could not find the {fixture_name} fixture"
    raise FileNotFoundError(msg)


async def open_fixture_async(fixtures_path: Path | AsyncPath, fixture_name: str) -> Any:
    """Loads JSON file with the specified fixture name

    Args:
        fixtures_path (Path): The path to look for fixtures
        fixture_name (str): The fixture name to load.

    Raises:
        FileNotFoundError: Fixtures not found.

    Returns:
        Any: The parsed JSON data
    """
    fixture = AsyncPath(fixtures_path / f"{fixture_name}.json")
    if await fixture.exists():
        async with await fixture.open(mode="r", encoding="utf-8") as f:
            f_data = await f.read()
        return decode_json(f_data)
    msg = f"Could not find the {fixture_name} fixture"
    raise FileNotFoundError(msg)
