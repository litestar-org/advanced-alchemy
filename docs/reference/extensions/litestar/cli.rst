:tocdepth: 2

============
CLI Commands
============

.. py:module:: advanced_alchemy.extensions.litestar.cli

Litestar CLI database group and plugin discovery utilities.

Database Command Group
----------------------

.. click:: advanced_alchemy.extensions.litestar.cli:database_group
    :prog: litestar database
    :nested: full

Plugin Discovery
----------------

.. autofunction:: advanced_alchemy.extensions.litestar.cli.get_database_migration_plugin
