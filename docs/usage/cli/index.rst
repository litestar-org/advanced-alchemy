===
CLI
===

Advanced Alchemy provides a command-line interface for database migrations and management.

.. toctree::
   :maxdepth: 1

   migrations
   commands

Prerequisites
=============

- Python 3.9+
- Advanced Alchemy installed with ``cli`` extra

Installation
============

Install Advanced Alchemy with CLI support:

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

Overview
========

The CLI provides:

- Database migration management
- Migration history inspection
- Branch management for migrations
- Database utilities (drop, dump)
- Extensibility for custom commands

Basic Usage
===========

The CLI can be invoked using the ``alchemy`` command:

.. code-block:: bash

    alchemy --help

Global Options
==============

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

Configuration
=============

Create a configuration file for the CLI:

.. code-block:: python
    :caption: alchemy-config.py

    from advanced_alchemy.config import SQLAlchemyAsyncConfig

    # Create config using your database
    config = SQLAlchemyAsyncConfig(
        connection_string="postgresql+asyncpg://user:pass@localhost/db"
    )

If the file is named ``alchemy-config.py``, use it like this:

.. code-block:: bash

    alchemy <command> --config path.to.alchemy-config.config

Quick Start
===========

Initialize migrations:

.. code-block:: bash

    alchemy init --config path.to.alchemy-config.config

Create a migration:

.. code-block:: bash

    alchemy make-migrations -m "initial schema" --config path.to.alchemy-config.config

Apply migrations:

.. code-block:: bash

    alchemy upgrade --config path.to.alchemy-config.config

Next Steps
==========

- :doc:`migrations` - Migration workflow and troubleshooting
- :doc:`commands` - Complete command reference

Related Topics
==============

- :doc:`../modeling/index` - Defining models for migrations
- :doc:`../frameworks/index` - Framework integration
