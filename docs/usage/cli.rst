=================
Command Line Tool
=================

Advanced Alchemy provides a command-line interface (CLI) for common database operations and project management tasks.

Installation
------------

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

The CLI can be invoked using the ``alchemy`` command:

.. code-block:: bash

    alchemy --help

Global Options
--------------

The following options are available for all commands:

.. list-table:: Global options
   :header-rows: 1
   :widths: 20 80

   * - Option
     - Explanation
   * - ``--config`` TEXT
     - **Required**. Dotted path to SQLAlchemy config(s), it's an instance of ``SQLAlchemyConfig`` (sync or async). Example: ``--config path.to.alchemy-config.config``
   * - ``--bind-key`` TEXT
     - Optional. Specify which SQLAlchemy config to use
   * - ``--no-prompt``
     - Optional. Skip confirmation prompts
   * - ``--verbose``
     - Optional. Enable verbose output


Config
------

Here is an example of what **config** looks like.

If the file is named ``alchemy-config.py``, you would need to use it like this ``--config path.to.alchemy-config.config``

.. code-block:: python
    :caption: alchemy-config.py

    from sqlalchemy import create_engine
    from advanced_alchemy.config import SQLAlchemyConfig

    # Create a test config using SQLite
    config = SQLAlchemyConfig(
        connection_url="sqlite:///test.db"
    )


Available Commands
------------------

show-current-revision
~~~~~~~~~~~~~~~~~~~~~

Show the current revision of the database:

.. code-block:: bash

    alchemy show-current-revision --config path.to.alchemy-config.config

downgrade
~~~~~~~~~

Downgrade database to a specific revision:

.. code-block:: bash

    alchemy downgrade --config path.to.alchemy-config.config [REVISION]

.. list-table:: Options
   :header-rows: 1
   :widths: 20 80

   * - Option
     - Explanation
   * - ``--sql``
     - Generate SQL output for offline migrations
   * - ``--tag`` TEXT
     - Arbitrary tag for custom env.py scripts
   * - ``REVISION``
     - Target revision (default: "-1")


upgrade
~~~~~~~

Upgrade database to a specific revision:

.. code-block:: bash

    alchemy upgrade --config path.to.alchemy-config.config [REVISION]

.. list-table:: Options
   :header-rows: 1
   :widths: 20 80

   * - Option
     - Explanation
   * - ``--sql``
     - Generate SQL output for offline migrations
   * - ``--tag`` TEXT
     - Arbitrary tag for custom env.py scripts
   * - ``REVISION``
     - Target revision (default: "head")


init
~~~~

Initialize migrations for the project:

.. code-block:: bash

    alchemy init --config path.to.alchemy-config.config [DIRECTORY]

.. list-table:: Options
   :header-rows: 1
   :widths: 20 80

   * - Option
     - Explanation
   * - ``--multidb``
     - Support multiple databases
   * - ``--package``
     - Create __init__.py for created folder (default: True)
   * - ``DIRECTORY``
     - Directory for migration files (optional)


make-migrations
~~~~~~~~~~~~~~~

Create a new migration revision:

.. code-block:: bash

    alchemy make-migrations --config path.to.alchemy-config.config

.. list-table:: Options
   :header-rows: 1
   :widths: 30 70

   * - Option
     - Explanation
   * - ``-m``, ``--message`` TEXT
     - Revision message
   * - ``--autogenerate``/ ``--no-autogenerate``
     - Automatically detect changes (default: True)
   * - ``--sql``
     - Export to .sql instead of writing to database
   * - ``--head`` TEXT
     - Base revision for new revision (default: "head")
   * - ``--splice``
     - Allow non-head revision as the "head"
   * - ``--branch-label`` TEXT
     - Branch label for new revision
   * - ``--version-path`` TEXT
     - Specific path for version file
   * - ``--rev-id`` TEXT
     - Specific revision ID


drop-all
~~~~~~~~

Drop all tables from the database:

.. code-block:: bash

    alchemy drop-all --config path.to.alchemy-config.config

dump-data
~~~~~~~~~

Dump specified tables from the database to JSON files:

.. code-block:: bash

    alchemy dump-data --config path.to.alchemy-config.config --table TABLE_NAME

.. list-table:: Options
   :header-rows: 1
   :widths: 20 80

   * - Option
     - Explanation
   * - ``--table`` TEXT
     - Name of table to dump (use '*' for all tables)
   * - ``--dir`` PATH
     - Directory to save JSON files (default: ./fixtures)


Extending the CLI
-----------------

If you're using Click in your project, you can extend Advanced Alchemy's CLI with your own commands. The CLI provides two main functions for integration:

- ``get_alchemy_group()``: Get the base CLI group
- ``add_migration_commands()``: Add migration-related commands to a group

Basic Extension
~~~~~~~~~~~~~~~

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

Typer integration
-----------------

You can integrate Advanced Alchemy's CLI commands into your existing ``Typer`` application. Here's how:


.. code-block:: python
    :caption: cli.py

    import typer
    from advanced_alchemy.cli import get_alchemy_group, add_migration_commands

    app = typer.Typer()

    @app.command()
    def hello(name: str) -> None:
        """Says hello to the world."""
        typer.echo(f"Hello {name}")

    @app.callback()
    def callback():
        """
        Typer app, including Click subapp
        """
        pass

    def create_cli() -> typer.Typer:
        """Create the CLI application with both Typer and Click commands."""
        # Get the Click group from advanced_alchemy
        alchemy_group = get_alchemy_group()

        # Convert our Typer app to a Click command object
        typer_click_object = typer.main.get_command(app)

        # Add all migration commands from the alchemy group to our CLI
        typer_click_object.add_command(add_migration_commands(alchemy_group))

        return typer_click_object

    if __name__ == "__main__":
        cli = create_cli()
        cli()


After setting up the integration, you can use both your ``Typer`` commands and Advanced Alchemy commands:

.. code-block:: bash

    # Use your Typer commands
    python cli.py hello Cody

    # Use Advanced Alchemy commands
    python cli.py alchemy upgrade --config path.to.config
    python cli.py alchemy make-migrations --config path.to.config
