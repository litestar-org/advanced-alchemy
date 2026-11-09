======================
CLI Command Workflows
======================

This guide walks through common database lifecycle workflows using the standalone ``alchemy`` CLI (or ``litestar database`` / ``flask database`` when using web framework integrations). Complete flag signatures for every subcommand are documented in :doc:`/reference/cli`.

Inspecting Loaded Configurations
--------------------------------

Before running migrations, verify which configurations were discovered and have Alembic enabled using ``show-config`` or ``--validate-config``:

.. code-block:: bash

    alchemy show-config
    alchemy --validate-config show-current-revision

Initializing and Generating Migrations
--------------------------------------

Initialize an Alembic migration directory for a single database or multi-database project, then autogenerate revision scripts from your SQLAlchemy metadata:

.. code-block:: bash

    alchemy init migrations
    alchemy make-migrations -m "create initial tables"

Apply pending migrations with ``upgrade`` or revert revisions with ``downgrade``:

.. code-block:: bash

    alchemy upgrade head
    alchemy downgrade -1

Pass ``--sql`` to ``upgrade``, ``downgrade``, ``stamp``, or ``ensure-version`` to emit offline SQL scripts for DBA review without executing statements against the live database.

.. note:: **PostgreSQL enum changes**

   Alembic's autogenerate does not detect changes to PostgreSQL native ``ENUM`` types on its own (such as adding a value to an existing ``StrEnum``). Advanced Alchemy automatically enables this detection for PostgreSQL connections when `alembic-postgresql-enum <https://pypi.org/project/alembic-postgresql-enum/>`_ is installed (included automatically with the ``asyncpg``, ``psycopg``, and ``psycopg2`` extras):

   .. tab-set::
       :sync-group: pkg

       .. tab-item:: uv
           :sync: uv

           .. code-block:: bash

               uv add "advanced-alchemy[asyncpg]"

       .. tab-item:: pip
           :sync: pip

           .. code-block:: bash

               pip install "advanced-alchemy[asyncpg]"

       .. tab-item:: pdm
           :sync: pdm

           .. code-block:: bash

               pdm add "advanced-alchemy[asyncpg]"

       .. tab-item:: poetry
           :sync: poetry

           .. code-block:: bash

               poetry add "advanced-alchemy[asyncpg]"

   Both :class:`~advanced_alchemy.alembic.commands.AlembicCommandConfig` and the generated ``env.py`` load ``alembic_postgresql_enum`` inside ``contextlib.suppress(ModuleNotFoundError)`` when the target dialect is PostgreSQL, so no manual configuration is required.

Auditing Migration History and Drift
------------------------------------

Use the inspection commands in CI/CD pipelines to verify that your migration scripts match your SQLAlchemy models and have no unmerged branch heads:

.. code-block:: bash

    alchemy check
    alchemy heads --verbose
    alchemy history --indicate-current
    alchemy show head

Branching and Merging Revisions
-------------------------------

When parallel feature branches create independent migration heads, inspect the branch points with ``branches`` and consolidate them into a single merge revision with ``merge``:

.. code-block:: bash

    alchemy branches --verbose
    alchemy merge heads -m "merge parallel feature migrations"

Stamping Existing Databases
---------------------------

When adopting Alembic on an existing database or resetting a local development version table, use ``ensure-version`` and ``stamp``:

.. code-block:: bash

    alchemy ensure-version
    alchemy stamp head

Database Maintenance and Fixture Dumps
--------------------------------------

During local development or test fixture generation, export table rows to JSON files with ``dump-data`` or reset all mapped tables with ``drop-all``:

.. code-block:: bash

    alchemy dump-data --table "*" --dir ./fixtures
    alchemy drop-all --no-prompt

.. warning::

    ``alchemy drop-all`` permanently drops all tables bound to the target metadata. Always verify the target environment before passing ``--no-prompt``.

Related Documentation
---------------------

- :doc:`/usage/cli` — CLI installation, configuration discovery, global flags, and Click extension points.
- :doc:`/usage/database_seeding` — Loading exported JSON fixtures back into your database.
- :doc:`/reference/cli` — Complete ``alchemy`` CLI command and option reference.
- :doc:`/reference/extensions/litestar/cli` — Litestar ``database`` CLI command reference.
