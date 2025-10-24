========
Commands
========

Complete reference for Advanced Alchemy CLI commands.

Prerequisites
=============

See :doc:`index` for installation and configuration.

Migration Commands
==================

Commands for creating and applying database migrations.

show-current-revision
---------------------

Show the current revision of the database:

.. code-block:: bash

    alchemy show-current-revision --config path.to.alchemy-config.config

.. list-table:: Options
   :header-rows: 1
   :widths: 20 80

   * - Option
     - Explanation
   * - ``--verbose``
     - Display detailed revision information

downgrade
---------

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
-------

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

stamp
-----

Stamp the revision table with a specific revision without running migrations:

.. code-block:: bash

    alchemy stamp --config path.to.alchemy-config.config REVISION

.. list-table:: Options
   :header-rows: 1
   :widths: 20 80

   * - Option
     - Explanation
   * - ``--sql``
     - Generate SQL output for offline migrations
   * - ``--tag`` TEXT
     - Arbitrary tag for custom env.py scripts
   * - ``--purge``
     - Delete all entries in version table before stamping
   * - ``REVISION``
     - Target revision to stamp (required)

Use cases:

- Initialize version table for existing database
- Mark migrations as applied without running them
- Reset migration history (with ``--purge``)
- Generate SQL for manual database stamping (with ``--sql``)

init
----

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
---------------

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

Inspection Commands
===================

Commands for inspecting migration history and database state.

check
-----

Check if the database is up to date with the current migration revision:

.. code-block:: bash

    alchemy check --config path.to.alchemy-config.config

Returns exit code 0 if database is current, non-zero otherwise.

Use cases:

- CI/CD validation before deployment
- Pre-deployment smoke tests
- Health checks

heads
-----

Show current available heads in the migration script directory:

.. code-block:: bash

    alchemy heads --config path.to.alchemy-config.config

.. list-table:: Options
   :header-rows: 1
   :widths: 20 80

   * - Option
     - Explanation
   * - ``--verbose``
     - Display detailed head information
   * - ``--resolve-dependencies``
     - Resolve dependencies between heads

Use cases:

- Detect multiple heads (branch conflicts)
- Verify migration graph state
- Branch development coordination

history
-------

List migration changesets in chronological order:

.. code-block:: bash

    alchemy history --config path.to.alchemy-config.config

.. list-table:: Options
   :header-rows: 1
   :widths: 20 80

   * - Option
     - Explanation
   * - ``--verbose``
     - Display detailed revision information
   * - ``--rev-range`` TEXT
     - Revision range to display (e.g., 'base:head', 'abc:def')
   * - ``--indicate-current``
     - Indicate the current revision in output

Use cases:

- Audit migration history
- Generate migration documentation
- Review changes between revisions

show
----

Show details of a specific revision:

.. code-block:: bash

    alchemy show --config path.to.alchemy-config.config REVISION

Examples:

.. code-block:: bash

    # Show head revision
    alchemy show head --config path.to.alchemy-config.config

    # Show specific revision
    alchemy show abc123def --config path.to.alchemy-config.config

    # Show base revision
    alchemy show base --config path.to.alchemy-config.config

branches
--------

Show current branch points in the migration history:

.. code-block:: bash

    alchemy branches --config path.to.alchemy-config.config

.. list-table:: Options
   :header-rows: 1
   :widths: 20 80

   * - Option
     - Explanation
   * - ``--verbose``
     - Display detailed branch information

Use cases:

- Identify branch points in migration graph
- Multi-team development coordination
- Branch-based development workflows

Branch Management Commands
==========================

Commands for managing branched migration workflows.

merge
-----

Merge two revisions together, creating a new migration file:

.. code-block:: bash

    alchemy merge --config path.to.alchemy-config.config REVISIONS

.. list-table:: Options
   :header-rows: 1
   :widths: 20 80

   * - Option
     - Explanation
   * - ``-m``, ``--message`` TEXT
     - Merge message
   * - ``--branch-label`` TEXT
     - Branch label for merge revision
   * - ``--rev-id`` TEXT
     - Specify custom revision ID
   * - ``REVISIONS``
     - Revisions to merge (e.g., 'abc123+def456' or 'heads')

Examples:

.. code-block:: bash

    # Merge all heads
    alchemy merge heads -m "merge feature branches" --config path.to.alchemy-config.config

    # Merge specific revisions
    alchemy merge abc123+def456 -m "merge database changes" --config path.to.alchemy-config.config

Use cases:

- Resolve multiple heads (branch conflicts)
- Consolidate parallel development branches
- Team coordination for database changes

Utility Commands
================

Additional migration utilities.

edit
----

Edit a revision file using the system editor (set via ``$EDITOR`` environment variable):

.. code-block:: bash

    alchemy edit --config path.to.alchemy-config.config REVISION

Examples:

.. code-block:: bash

    # Edit latest revision
    alchemy edit head --config path.to.alchemy-config.config

    # Edit specific revision
    alchemy edit abc123def --config path.to.alchemy-config.config

ensure-version
--------------

Create the Alembic version table if it doesn't exist:

.. code-block:: bash

    alchemy ensure-version --config path.to.alchemy-config.config

.. list-table:: Options
   :header-rows: 1
   :widths: 20 80

   * - Option
     - Explanation
   * - ``--sql``
     - Generate SQL output instead of executing

Use cases:

- Database initialization workflows
- Manual database setup
- Generate SQL for DBA review (with ``--sql``)

list-templates
--------------

List available Alembic migration templates:

.. code-block:: bash

    alchemy list-templates --config path.to.alchemy-config.config

Use cases:

- Discover available templates for ``init`` command
- Template selection for new projects

Database Commands
=================

Commands for managing database tables and data.

drop-all
--------

Drop all tables from the database:

.. code-block:: bash

    alchemy drop-all --config path.to.alchemy-config.config

.. warning::

   This command is destructive and will delete all data. Use with caution.

dump-data
---------

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
=================

Integrate Advanced Alchemy commands into your application.

Click Integration
-----------------

Extend the CLI with custom commands:

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
-------------------------

Integrate into existing Click group:

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

Typer Integration
-----------------

Integrate with Typer applications:

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

Usage:

.. code-block:: bash

    # Use your Typer commands
    python cli.py hello Cody

    # Use Advanced Alchemy commands
    python cli.py alchemy upgrade --config path.to.config
    python cli.py alchemy make-migrations --config path.to.config

Related Topics
==============

- :doc:`migrations` - Migration workflow and troubleshooting
- :doc:`index` - CLI overview and installation
