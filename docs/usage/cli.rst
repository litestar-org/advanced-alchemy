=================
Command Line Tool
=================

Advanced Alchemy provides a command-line interface (CLI) for common database operations and project management tasks.

Installation
-----------

The CLI is installed with Advanced Alchemy with the extra ``cli``:

.. tab-set::

    .. tab-item:: pip
        :sync: key1

        .. code-block:: bash
            :caption: Using pip

            python3 -m pip install advanced-alchemy[cli]

    .. tab-item:: uv

        .. code-block:: bash
            :caption: Using `UV <https://docs.astral.sh/uv/>`_

            uv add advanced-alchemy[cli]

    .. tab-item:: pipx
        :sync: key2

        .. code-block:: bash
            :caption: Using `pipx <https://pypa.github.io/pipx/>`_

            pipx install advanced-alchemy[cli]


    .. tab-item:: pdm

        .. code-block:: bash
            :caption: Using `PDM <https://pdm.fming.dev/>`_

            pdm add advanced-alchemy[cli]

    .. tab-item:: Poetry

        .. code-block:: bash
            :caption: Using `Poetry <https://python-poetry.org/>`_

            poetry add advanced-alchemy[cli]


Basic Usage
-----------

The CLI can be invoked using Python's module syntax:

.. code-block:: bash

    python -m advanced_alchemy --help
    # or with uv
    uv run -m advanced_alchemy --help

Global Options
--------------

The following options are available for all commands:

--config TEXT        Required. Dotted path to SQLAlchemy config(s)
--bind-key TEXT     Optional. Specify which SQLAlchemy config to use
--no-prompt         Optional. Skip confirmation prompts
--verbose          Optional. Enable verbose output

Available Commands
------------------

show-current-revision
~~~~~~~~~~~~~~~~~~~~~

Show the current revision of the database:

.. code-block:: bash

    python -m advanced_alchemy show-current-revision --config path.to.config

downgrade
~~~~~~~~~

Downgrade database to a specific revision:

.. code-block:: bash

    python -m advanced_alchemy downgrade --config path.to.config [REVISION]

Options:
  --sql              Generate SQL output for offline migrations
  --tag TEXT         Arbitrary tag for custom env.py scripts
  REVISION           Target revision (default: "-1")

upgrade
~~~~~~~

Upgrade database to a specific revision:

.. code-block:: bash

    python -m advanced_alchemy upgrade --config path.to.config [REVISION]

Options:
  --sql              Generate SQL output for offline migrations
  --tag TEXT         Arbitrary tag for custom env.py scripts
  REVISION           Target revision (default: "head")

init
~~~~

Initialize migrations for the project:

.. code-block:: bash

    python -m advanced_alchemy init --config path.to.config [DIRECTORY]

Options:
  --multidb          Support multiple databases
  --package          Create __init__.py for created folder (default: True)
  DIRECTORY          Directory for migration files (optional)

make-migrations
~~~~~~~~~~~~~~~

Create a new migration revision:

.. code-block:: bash

    python -m advanced_alchemy make-migrations --config path.to.config

Options:
  -m, --message TEXT       Revision message
  --autogenerate/--no-autogenerate  Automatically detect changes (default: True)
  --sql                    Export to .sql instead of writing to database
  --head TEXT              Base revision for new revision (default: "head")
  --splice                 Allow non-head revision as the "head"
  --branch-label TEXT      Branch label for new revision
  --version-path TEXT      Specific path for version file
  --rev-id TEXT           Specific revision ID

drop-all
~~~~~~~~

Drop all tables from the database:

.. code-block:: bash

    python -m advanced_alchemy drop-all --config path.to.config

dump-data
~~~~~~~~~

Dump specified tables from the database to JSON files:

.. code-block:: bash

    python -m advanced_alchemy dump-data --config path.to.config --table TABLE_NAME

Options:
  --table TEXT       Name of table to dump (use '*' for all tables)
  --dir PATH         Directory to save JSON files (default: ./fixtures)

Configuration
-------------

The CLI looks for configuration in the following locations (in order of precedence):

1. Command line arguments
2. Environment variables (prefixed with ``AA_``)
3. ``pyproject.toml`` configuration
4. ``.env`` file

Example ``pyproject.toml`` configuration:

.. code-block:: toml

    [tool.advanced-alchemy]
    database_url = "postgresql://user:pass@localhost/dbname"
    migrations_dir = "migrations"
    seed_data = "seeds"
    async = false

Environment Variables
~~~~~~~~~~~~~~~~~~~~~

- ``AA_DATABASE_URL``: Database connection URL
- ``AA_MIGRATIONS_DIR``: Directory for migration files
- ``AA_SEED_DATA``: Directory containing seed data
- ``AA_ASYNC``: Enable async mode (true/false)

Error Handling
--------------

The CLI provides detailed error messages and exit codes:

- 0: Success
- 1: General error
- 2: Configuration error
- 3: Database error
- 4: Migration error

For detailed debugging, use the ``--verbose`` flag:

.. code-block:: bash

    aa --verbose db create

Extending the CLI
-----------------

If you're using Click in your project, you can extend Advanced Alchemy's CLI with your own commands. The CLI provides two main functions for integration:

- ``get_alchemy_group()``: Get the base CLI group
- ``add_migration_commands()``: Add migration-related commands to a group

Basic Extension
~~~~~~~~~~~~~~

Here's how to extend the CLI with your own commands:

.. code-block:: python

    from advanced_alchemy.cli import get_alchemy_group, add_migration_commands
    import click

    # Get the base group
    alchemy_group = get_alchemy_group()

    # Add your custom commands
    @alchemy_group.command(name="my-command")
    @click.option("--my-option", help="Custom option")
    def my_command(my_option):
        """My custom command."""
        click.echo(f"Running my command with option: {my_option}")

    # Add migration commands to your group
    add_migration_commands(alchemy_group)

Custom Group Integration
~~~~~~~~~~~~~~~~~~~~~~~~

You can also integrate Advanced Alchemy's commands into your existing Click group:

.. code-block:: python

    import click
    from advanced_alchemy.cli import add_migration_commands

    @click.group()
    def cli():
        """My application CLI."""
        pass

    # Add migration commands to your CLI group
    add_migration_commands(cli)

    @cli.command()
    def my_command():
        """Custom command in your CLI."""
        pass

    if __name__ == "__main__":
        cli()

Configuration Access
~~~~~~~~~~~~~~~~~~~~

When extending the CLI, you can access the SQLAlchemy configuration from the Click context:

.. code-block:: python

    @alchemy_group.command()
    @click.pass_context
    def my_db_command(ctx):
        """Command that needs database access."""
        # Get configs from context
        configs = ctx.obj["configs"]
        
        # Use the first config by default
        default_config = configs[0]
        
        # Or find a specific config by bind key
        specific_config = next(
            (config for config in configs if config.bind_key == "my_bind_key"),
            None
        )

This gives you access to the same configuration system used by the built-in commands.

Best Practices
~~~~~~~~~~~~~

When extending the CLI:

1. Use the ``--config`` option consistently with other commands
2. Follow the same pattern for database bind keys if working with multiple databases
3. Consider using the ``--no-prompt`` option for commands that modify data
4. Utilize Rich for consistent terminal output
5. Handle errors gracefully and provide clear error messages

Example with All Features
~~~~~~~~~~~~~~~~~~~~~~~~~

Here's a more complete example showing various features:

.. code-block:: python

    from advanced_alchemy.cli import get_alchemy_group
    import click
    from rich import print
    from rich.prompt import Confirm

    alchemy_group = get_alchemy_group()

    @alchemy_group.group()
    def custom():
        """Custom commands group."""
        pass

    @custom.command()
    @click.option(
        "--bind-key",
        help="Specify which SQLAlchemy config to use",
        type=str,
        default=None,
    )
    @click.option(
        "--no-prompt",
        is_flag=True,
        help="Skip confirmation prompts",
    )
    @click.pass_context
    def my_command(ctx, bind_key, no_prompt):
        """Custom database operation."""
        if not no_prompt and not Confirm.ask("Are you sure?"):
            return
        
        configs = ctx.obj["configs"]
        config = next(
            (c for c in configs if c.bind_key == bind_key),
            configs[0]
        )
        
        print(f"[green]Using database: {config.connection_string}[/]")
        # Your command logic here
