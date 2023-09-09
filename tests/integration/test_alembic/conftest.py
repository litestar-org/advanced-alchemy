from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest
from pytest import FixtureRequest

from litestar.app import Litestar
from advanced_alchemy.alembic import commands

if TYPE_CHECKING:
    from pytest import MonkeyPatch


@pytest.fixture()
async def sync_alembic_commands(sync_app: Litestar) -> commands.AlembicCommands:
    return commands.AlembicCommands(app=sync_app)


@pytest.fixture()
async def async_alembic_commands(async_app: Litestar) -> commands.AlembicCommands:
    return commands.AlembicCommands(app=async_app)


@pytest.fixture(params=[pytest.param("sync_alembic_commands"), pytest.param("async_alembic_commands")])
async def alembic_commands(request: FixtureRequest) -> commands.AlembicCommands:
    return cast(commands.AlembicCommands, request.getfixturevalue(request.param))
