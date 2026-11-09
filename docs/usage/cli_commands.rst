=====================
CLI Command Workflows
=====================

Once :doc:`your config is connected </usage/cli>`, day-to-day schema changes follow the same commands whether you run ``alchemy ...``, ``litestar database ...``, or ``flask database ...``.

Everyday Migration Flow
-----------------------

1. **Set up migrations once** in a new project, generate a migration script from your models, and apply it:

   .. code-block:: bash

       alchemy init migrations
       alchemy make-migrations -m "create blog tables"
       alchemy upgrade head

2. **Undo the last migration** or **preview raw SQL** without touching the database:

   .. code-block:: bash

       alchemy downgrade -1
       alchemy upgrade head --sql

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

Checking Configs and Schema Drift in CI
---------------------------------------

Run ``show-config`` to confirm which databases were found, and run ``check`` in CI to catch model changes that are missing a migration file:

.. code-block:: bash

    alchemy show-config
    alchemy check
    alchemy history --indicate-current

Handling Parallel Git Branches
------------------------------

When two teammates create migrations on separate branches, merge both heads into one linear revision before deploying:

.. code-block:: bash

    alchemy heads --verbose
    alchemy merge heads -m "merge feature migrations"

Adopting an Existing Database or Exporting Data
-----------------------------------------------

.. tab-set::

    .. tab-item:: Mark Existing Schema Current

        .. code-block:: bash

            alchemy ensure-version
            alchemy stamp head

    .. tab-item:: Export JSON Seed Files

        .. code-block:: bash

            alchemy dump-data --table "*" --dir ./fixtures

    .. tab-item:: Reset Local Dev Tables

        .. code-block:: bash

            alchemy drop-all --no-prompt

.. warning::

    ``drop-all`` permanently deletes every mapped table in the target database. Only run it against disposable local or test databases.

See :doc:`/reference/cli` for every command flag.
