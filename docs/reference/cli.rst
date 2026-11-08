:tocdepth: 2

===
cli
===

.. py:module:: advanced_alchemy.cli

Command-line interface and migration commands for Advanced Alchemy.

CLI Commands
------------

.. click:: advanced_alchemy.cli:get_alchemy_group
    :prog: alchemy
    :nested: full

Configuration & Discovery Helpers
---------------------------------

.. autofunction:: advanced_alchemy.cli.add_migration_commands

.. autofunction:: advanced_alchemy.cli.get_alchemy_group

.. autofunction:: advanced_alchemy.cli.discover_config_from_pyproject

.. autofunction:: advanced_alchemy.cli.find_pyproject_toml

.. autofunction:: advanced_alchemy.cli.parse_pyproject_config

.. autofunction:: advanced_alchemy.cli.resolve_config_async

.. autofunction:: advanced_alchemy.cli.resolve_config_sync
