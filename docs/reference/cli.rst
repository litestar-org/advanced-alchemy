===
cli
===

.. currentmodule:: advanced_alchemy.cli

.. automodule:: advanced_alchemy.cli
    :members:
    :show-inheritance:

Overview
--------

The CLI module provides Click-based command groups for database migrations and management.
Can be used standalone or integrated into framework CLIs (Litestar, FastAPI, Flask).

Functions
---------

.. autofunction:: get_alchemy_group
   :no-index:

.. autofunction:: add_migration_commands
   :no-index:

Usage
-----

Standalone CLI:

.. code-block:: python

   from advanced_alchemy.cli import get_alchemy_group

   cli = get_alchemy_group()

   if __name__ == "__main__":
       cli()

Framework Integration:

.. code-block:: python

   from advanced_alchemy.cli import add_migration_commands
   from click import Group

   app_cli = Group("myapp")
   add_migration_commands(app_cli)

See Also
--------

- :doc:`extensions/litestar/cli` - Litestar CLI integration
- :doc:`../usage/cli/index` - CLI usage guide
