# Guide: Database Migrations (Alembic CLI)

`advanced-alchemy` provides a powerful, integrated command-line interface (CLI) for managing database migrations with Alembic. It offers a seamless experience whether you are using it in a standalone project or with a supported web framework like Litestar or FastAPI.

## 1. Standalone Usage

For projects that don't use a framework integration, `advanced-alchemy` provides a standalone `alchemy` command. This command is a wrapper around the standard `alembic` command, but it's pre-configured to work with your `SQLAlchemyAsyncConfig` or `SQLAlchemySyncConfig`.

### Configuration

The CLI needs to know where to find your configuration object. You point to it using the `--config` option.

```bash
# Point to the config object for a project named 'my_app'
alchemy --config my_app.db.config.sqlalchemy_config <command>
```

### Common Commands

All standard Alembic commands are available.

-   **Initialize Migrations:**
    ```bash
    alchemy --config my_app.db.config init
    ```

-   **Create a New Migration:**
    ```bash
    # This will automatically detect changes to your models
    alchemy --config my_app.db.config make-migrations -m "Add user table"
    ```

-   **Upgrade the Database:**
    ```bash
    alchemy --config my_app.db.config upgrade head
    ```

-   **Downgrade the Database:**
    ```bash
    alchemy --config my_app.db.config downgrade -1
    ```

## 2. Framework Integration

When using a framework integration like the `SQLAlchemyPlugin` for Litestar, the migration commands are integrated directly into the framework's own CLI.

### Litestar Integration

The `SQLAlchemyPlugin` automatically registers a `db` command group with the `litestar` CLI.

**Configuration:**
The CLI commands are enabled by your `ApplicationCore` plugin's `on_cli_init` method. You add the `database_group` to your main CLI group.

```python
# In your src/py/app/server/core.py

from advanced_alchemy.extensions.litestar.cli import database_group

class ApplicationCore(InitPluginProtocol, CLIPluginProtocol):
    # ...
    def on_cli_init(self, cli: Group) -> None:
        # This adds the 'db' command group to the 'litestar' CLI
        cli.add_command(database_group)
```

**Usage:**
You can now run all the same migration commands, but prefixed with `litestar db`.

-   **Create a New Migration:**
    ```bash
    litestar db make-migrations -m "Add user table"
    ```

-   **Upgrade the Database:**
    ```bash
    litestar db upgrade head
    ```

### FastAPI Integration

For FastAPI, you register the database commands in your CLI entry point (e.g., `manage.py`).

**Configuration:**

```python
# In your manage.py or cli.py

from fastapi import FastAPI
from advanced_alchemy.extensions.fastapi import register_database_commands
import click

# Assume 'app' is your FastAPI instance
app = FastAPI()
# ... configure AdvancedAlchemy on your app ...

@click.group()
def cli():
    pass

# This adds the 'database' command group
cli.add_command(register_database_commands(app))
```

**Usage:**
The commands are then available under the `database` group.

-   **Create a New Migration:**
    ```bash
    python manage.py database make-migrations -m "Add user table"
    ```

-   **Upgrade the Database:**
    ```bash
    python manage.py database upgrade head
    ```

This integrated CLI approach provides a single, consistent entry point for all your application's management tasks.

## 4. Working with Multiple Databases (`--bind-key`)

The migration CLI fully supports multi-database setups. To target a command at a specific database, you use the `--bind-key` option.

### Configuration

For the `--bind-key` option to work, you must do two things:

1.  **Assign a `bind_key` to each database configuration:** When you define your `SQLAlchemyAsyncConfig` or `SQLAlchemySyncConfig` objects, give each one a unique `bind_key`.

    ```python
    # In your config.py
    
    db_one_config = SQLAlchemyAsyncConfig(
        connection_string="...",
        bind_key="db_one",
    )
    
    db_two_config = SQLAlchemyAsyncConfig(
        connection_string="...",
        bind_key="db_two",
    )
    ```

2.  **Associate your models with a bind key:** In your SQLAlchemy declarative models, use the `info` dictionary in `__table_args__` to specify which database the model belongs to.

    ```python
    # In your models.py
    
    class MyModelForDBOne(UUIDAuditBase):
        __tablename__ = "my_model"
        __table_args__ = {"info": {"bind_key": "db_one"}}
        # ... columns ...
    
    class MyModelForDBTwo(UUIDAuditBase):
        __tablename__ = "another_model"
        __table_args__ = {"info": {"bind_key": "db_two"}}
        # ... columns ...
    ```

### Usage

Once configured, you can direct any migration command to a specific database using the `--bind-key` flag.

```bash
# Create a migration for the 'db_two' database
litestar db make-migrations -m "Add another model" --bind-key db_two

# Upgrade the 'db_one' database
litestar db upgrade head --bind-key db_one
```

This allows you to manage migrations for multiple databases from a single, unified CLI.

## 5. Adding Custom CLI Commands

A powerful pattern is to add your own application-specific commands alongside the `db` group. This is also done in the `on_cli_init` method (for Litestar) or your main CLI file.

**Litestar Example:**

```python
# In your src/py/app/server/core.py

from advanced_alchemy.extensions.litestar.cli import database_group
from app.cli.commands import user_management_group # Your custom command group

class ApplicationCore(InitPluginProtocol, CLIPluginProtocol):
    # ...
    def on_cli_init(self, cli: Group) -> None:
        cli.add_command(database_group)
        cli.add_command(user_management_group)
```

This would allow you to run commands like:
-   `litestar db upgrade head`
-   `litestar user create ...`
-   `litestar user delete ...`

This integrated CLI approach provides a single, consistent entry point for all your application's management tasks.
