=================
Command Line Tool
=================

Advanced Alchemy provides a standalone command-line interface (``alchemy``) for database migrations, schema initialization, table dumps, and configuration inspection. Full option tables for every command are generated automatically in :doc:`/reference/cli`.

Installation
------------

Install Advanced Alchemy with the ``cli`` extra using your preferred package manager:

.. tab-set::
    :sync-group: pkg

    .. tab-item:: uv
        :sync: uv

        .. code-block:: bash

            uv add "advanced-alchemy[cli]"

    .. tab-item:: pip
        :sync: pip

        .. code-block:: bash

            pip install "advanced-alchemy[cli]"

    .. tab-item:: pdm
        :sync: pdm

        .. code-block:: bash

            pdm add "advanced-alchemy[cli]"

    .. tab-item:: poetry
        :sync: poetry

        .. code-block:: bash

            poetry add "advanced-alchemy[cli]"

Global Options
--------------

Global options can be passed either before or after the subcommand name:

.. list-table:: Global CLI options
   :header-rows: 1
   :widths: 25 75

   * - Option
     - Description
   * - ``-c``, ``--config`` TEXT
     - Dotted (``module.attr``) or colon (``module:attr``) path to SQLAlchemy config(s), framework extensions, or a sync/async factory callable.
   * - ``--validate-config``
     - Validate discovered configurations and print a summary table before executing the command.
   * - ``--bind-key`` TEXT
     - Filter execution to a specific SQLAlchemy ``bind_key``.
   * - ``--no-prompt``
     - Skip interactive confirmation prompts for destructive operations.
   * - ``--verbose``
     - Enable verbose output.

Configuration Discovery
-----------------------

The CLI resolves SQLAlchemy configurations in the following order of precedence:

1. **CLI flag** (``--config`` / ``-c``, accepted on the root group or on any subcommand):

   .. code-block:: bash

       alchemy --config myapp.db:alchemy_config upgrade
       alchemy upgrade --config myapp.db:alchemy_config

2. **Environment variable** (``ALCHEMY_CONFIG``):

   .. code-block:: bash

       export ALCHEMY_CONFIG="myapp.db:alchemy_config"
       alchemy upgrade

3. **Project configuration** (``pyproject.toml``):

   The CLI walks upward from the current working directory (stopping at the ``.git`` repository root) to locate ``pyproject.toml`` and reads ``[tool.advanced-alchemy]`` (or ``[tool.alchemy]``):

   .. code-block:: toml

       [tool.advanced-alchemy]
       config = ["myapp.db:primary_config", "myapp.db:analytics_config"]

A configuration target can be a :class:`~advanced_alchemy.config.SQLAlchemyAsyncConfig` or :class:`~advanced_alchemy.config.SQLAlchemySyncConfig` instance, a sequence of configs, a framework plugin/extension instance, or a zero-argument sync/async factory function:

.. code-block:: python

    from advanced_alchemy.config import SQLAlchemySyncConfig

    alchemy_config = SQLAlchemySyncConfig(
        connection_string="sqlite:///:memory:",
    )

Extending the Click Group
-------------------------

Use :func:`~advanced_alchemy.cli.get_alchemy_group` and :func:`~advanced_alchemy.cli.add_migration_commands` to embed Advanced Alchemy's CLI commands inside an existing Click or Typer application:

.. code-block:: python

    import click
    from advanced_alchemy.cli import add_migration_commands, get_alchemy_group

    alchemy_group = get_alchemy_group()


    @alchemy_group.command(name="seed-reference")
    @click.option("--env", default="dev", help="Target environment name.")
    def seed_reference(env: str) -> None:
        """Custom project command registered alongside migration commands."""
        click.echo(f"Seeding reference data for {env}")


    add_migration_commands(alchemy_group)
    assert "upgrade" in alchemy_group.commands
    assert "seed-reference" in alchemy_group.commands

You can also attach the migration subcommands directly onto your own root ``@click.group()`` via ``add_migration_commands(custom_group)``.

Related Documentation
---------------------

- :doc:`cli_commands` — Migration, inspection, branching, and data dump command workflows.
- :doc:`/reference/cli` — Standalone ``alchemy`` CLI command and flag reference.
- :doc:`/reference/extensions/litestar/cli` — Litestar ``database`` CLI command reference.
