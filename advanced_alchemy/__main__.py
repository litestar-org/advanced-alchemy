from advanced_alchemy.cli import add_migration_commands as build_cli_interface


def run_cli() -> None:  # pragma: no cover
    """Advanced Alchemy CLI"""
    build_cli_interface()()


if __name__ == "__main__":  # pragma: no cover
    run_cli()
