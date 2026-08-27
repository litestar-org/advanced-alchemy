from advanced_alchemy.alembic.commands import AlembicCommands
from advanced_alchemy.config.sync import AlembicSyncConfig, SQLAlchemySyncConfig


def test_alembic_command_config_propagates_alembic_options() -> None:
    sqlalchemy_config = SQLAlchemySyncConfig(
        connection_string="sqlite://",
        bind_key="analytics",
        alembic_config=AlembicSyncConfig(
            version_table_name="custom_alembic_versions",
            version_table_schema="custom_schema",
            render_as_batch=False,
            compare_type=True,
            user_module_prefix="sqlalchemy.",
        ),
    )

    command_config = AlembicCommands(sqlalchemy_config).config

    assert command_config.bind_key == "analytics"
    assert command_config.version_table_name == "custom_alembic_versions"
    assert command_config.version_table_schema == "custom_schema"
    assert command_config.render_as_batch is False
    assert command_config.compare_type is True
    assert command_config.user_module_prefix == "sqlalchemy."
