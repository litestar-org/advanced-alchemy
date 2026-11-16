=================
CLI & Migrations
=================

Advanced Alchemy provides the ``alchemy`` CLI (along with ``litestar database`` and ``flask database`` in framework integrations) for generating and applying Alembic migrations, checking schema drift, and exporting or loading fixture data.

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

Configure the target database configuration path in ``pyproject.toml`` (recommended), via ``ALCHEMY_CONFIG``, or with ``--config``:

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
     - Description
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

Attach Advanced Alchemy's migration commands to an existing Click command group with ``add_migration_commands``:

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

* :doc:`cli_commands`: Commands for generating migrations, checking schema drift, and exporting fixtures.
* :doc:`/reference/cli`: Full ``alchemy`` CLI command and option reference.

.. toctree::
    :titlesonly:
    :hidden:

    Command Workflows <cli_commands>
