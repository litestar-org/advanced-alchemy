from __future__ import annotations

from advanced_alchemy.cli import add_migration_commands as build_cli_interface


def run_cli() -> None:
    """Advanced Alchemy CLI"""
    build_cli_interface()()


if __name__ == "__main__":
    run_cli()
