from __future__ import annotations

from click.testing import CliRunner
from litestar.cli.main import litestar_group as cli_command
from litestar.testing import TestClient


def test_drop_all() -> None:
  from examples.litestar.litestar_repo_only import app
  with TestClient(app):
    #  let the lifespan events occur so tables are created
     ...
  runner = CliRunner(env={"LITESTAR_APP": "examples.litestar.litestar_repo_only:app"})
  result = runner.invoke(cli_command, "database drop-all --no-prompt")
  assert result.exit_code == 0
  assert "Successfully dropped all objects" in result.output
