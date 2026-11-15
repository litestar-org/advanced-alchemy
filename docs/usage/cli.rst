=================
CLI & Migrations
=================

Whenever you add a column or create a new table in Python, your SQL database needs a migration script to apply that change safely.

Advanced Alchemy includes a terminal tool called ``alchemy`` (plus ``litestar database`` and ``flask database`` when using web frameworks) that wraps Alembic so you can create migrations, upgrade databases, and export seed data with one command.

Installation
------------

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

Pointing the CLI at Your Database Config
----------------------------------------

Tell ``alchemy`` where your database config lives once in ``pyproject.toml`` (recommended), with an environment variable, or with ``--config`` on the command line:

.. tab-set::

    .. tab-item:: pyproject.toml (Recommended)

        .. code-block:: toml

            [tool.advanced-alchemy]
            config = "myapp.db:alchemy_config"

    .. tab-item:: Environment Variable

        .. code-block:: bash

            export ALCHEMY_CONFIG="myapp.db:alchemy_config"
            alchemy upgrade head

    .. tab-item:: Command Flag

        .. code-block:: bash

            alchemy --config myapp.db:alchemy_config upgrade head

Your config target can be a ``SQLAlchemyAsyncConfig``, ``SQLAlchemySyncConfig``, a list of configs for multiple databases, a framework plugin/extension, or a zero-argument factory function:

.. code-block:: python

    from advanced_alchemy.config import SQLAlchemySyncConfig

    alchemy_config = SQLAlchemySyncConfig(
        connection_string="sqlite:///:memory:",
    )

Common Flags
------------

.. list-table::
   :header-rows: 1
   :widths: 28 72

   * - Flag
     - What It Does
   * - ``-c``, ``--config``
     - Import path (``myapp.db:alchemy_config``) to your config or app plugin.
   * - ``--validate-config``
     - Prints discovered configs and checks them before running a command.
   * - ``--bind-key``
     - Runs the command only for one named database bind key.
   * - ``--no-prompt``
     - Skips confirmation prompts in CI or automated scripts.

Adding Commands to Your Own Click App
-------------------------------------

Already have a custom project CLI built with Click? Attach Advanced Alchemy's migration commands directly to your group:

.. code-block:: python

    import click
    from advanced_alchemy.cli import add_migration_commands, get_alchemy_group

    alchemy_group = get_alchemy_group()


    @alchemy_group.command(name="seed-reference")
    @click.option("--env", default="dev", help="Target environment name.")
    def seed_reference(env: str) -> None:
        click.echo(f"Seeding reference data for {env}")


    add_migration_commands(alchemy_group)
    assert "upgrade" in alchemy_group.commands

Next Steps
----------

* :doc:`cli_commands` — Step-by-step commands for creating migrations, checking drift, and exporting fixtures.
* :doc:`/reference/cli` — Full list of ``alchemy`` commands and flags.

.. toctree::
    :titlesonly:
    :hidden:

    Command Workflows <cli_commands>
