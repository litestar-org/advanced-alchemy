import typer
from click import Context
from fastapi import FastAPI

from advanced_alchemy.extensions.starlette import AdvancedAlchemy

cli = typer.Typer()


def get_advanced_alchemy_extension(app: FastAPI) -> AdvancedAlchemy:
    """Retrieve the Advanced Alchemy extension from a FastAPI application instance."""
    # Replace this with the actual logic to get the extension from the app
    for state_key in app.state.__dict__:
        if isinstance(app.state.__dict__[state_key], AdvancedAlchemy):
            return app.state.__dict__[state_key]
    raise RuntimeError("Advanced Alchemy extension not found in the application.")


@cli.command()
def database_migration(ctx: Context) -> None:
    """Manage SQLAlchemy database migrations."""
    app: FastAPI = ctx.obj["app"]
    extension = get_advanced_alchemy_extension(app)
    # ... (Implement migration commands using extension.configs)
    # Example:
    for config in extension.configs:
        # ... (Perform migration operations using config)
        pass


# You can add more commands as needed
