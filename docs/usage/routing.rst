==================
Read/Write Routing
==================

Advanced Alchemy routes write operations (``INSERT``, ``UPDATE``, ``DELETE``, and ``SELECT ... FOR UPDATE``) to a primary engine group while distributing read queries across replica engine groups.

Routing Architecture
--------------------

.. mermaid::

    flowchart LR
        Session["Routing Session"] --> Selector["Operation & Context Check"]
        Selector -->|"Write / FOR UPDATE / Sticky"| Primary["Primary Group (default)"]
        Selector -->|"Read (Clean Context)"| Replica["Read Group (read)"]

1. **Mutations and locks**: ``INSERT``, ``UPDATE``, ``DELETE``, and ``SELECT ... FOR UPDATE`` statements bind to ``default_group`` (primary).
2. **Sticky-after-write consistency**: Once a session performs a write, subsequent reads stay on the primary engine until ``commit()`` or ``rollback()`` resets stickiness.
3. **Load-balanced reads**: Clean read operations select an engine from ``read_group`` using ``RoutingStrategy.ROUND_ROBIN`` or ``RoutingStrategy.RANDOM``.

Routing Configuration
---------------------

Configure named engine groups on :class:`~advanced_alchemy.config.routing.RoutingConfig` and pass it to :class:`~advanced_alchemy.config.SQLAlchemyAsyncConfig` or :class:`~advanced_alchemy.config.SQLAlchemySyncConfig`:

.. code-block:: python

    from advanced_alchemy.config import SQLAlchemyAsyncConfig
    from advanced_alchemy.config.routing import EngineConfig, RoutingConfig, RoutingStrategy

    config = SQLAlchemyAsyncConfig(
        routing_config=RoutingConfig(
            engines={
                "default": ["postgresql+asyncpg://user:pass@primary:5432/db"],
                "read": [
                    EngineConfig(
                        connection_string="postgresql+asyncpg://user:pass@replica-1:5432/db",
                        weight=2,
                        name="replica-east",
                    ),
                    EngineConfig(
                        connection_string="postgresql+asyncpg://user:pass@replica-2:5432/db",
                        weight=1,
                        name="replica-west",
                    ),
                ],
                "analytics": ["postgresql+asyncpg://user:pass@analytics:5432/db"],
            },
            default_group="default",
            read_group="read",
            routing_strategy=RoutingStrategy.ROUND_ROBIN,
            sticky_after_write=True,
        ),
    )

Bind Groups and Context Managers
--------------------------------

Route operations to specific engine groups with :func:`~advanced_alchemy.routing.use_bind_group`, :func:`~advanced_alchemy.routing.primary_context`, :func:`~advanced_alchemy.routing.replica_context`, or the repository ``bind_group`` parameter:

.. code-block:: python

    from typing import Any

    from advanced_alchemy.routing import (
        primary_context,
        replica_context,
        reset_routing_context,
        stick_to_primary_var,
        use_bind_group,
    )


    async def query_across_groups(repo: Any, item_id: Any) -> tuple[Any, list[Any], int]:
        with primary_context():
            critical_row = await repo.get(item_id)

        with replica_context():
            replica_rows = await repo.get_many()

        with use_bind_group("analytics"):
            analytics_total = await repo.count()

        if stick_to_primary_var.get():
            reset_routing_context()

        return critical_row, replica_rows, analytics_total

You can also pass ``bind_group="analytics"`` directly to repository methods such as ``await repo.get_many(bind_group="analytics")``.

Complete Runnable Example
-------------------------

The example below initializes primary and replica SQLite databases, verifies sticky-after-write behavior on the primary engine, and reads committed data from the replica group:

.. literalinclude:: /examples/routing/read_write_routing.py
    :language: python

Managed Database Endpoints
--------------------------

.. tab-set::

    .. tab-item:: Cloud SQL for PostgreSQL

        .. code-block:: python

            from advanced_alchemy.config.routing import RoutingConfig

            cloud_sql_routing = RoutingConfig(
                engines={
                    "default": ["postgresql+asyncpg://user:pass@primary-ip:5432/mydb"],
                    "read": [
                        "postgresql+asyncpg://user:pass@replica-1-ip:5432/mydb",
                        "postgresql+asyncpg://user:pass@replica-2-ip:5432/mydb",
                    ],
                },
            )

    .. tab-item:: AlloyDB for PostgreSQL

        .. code-block:: python

            from advanced_alchemy.config.routing import RoutingConfig

            alloydb_routing = RoutingConfig(
                engines={
                    "default": ["postgresql+asyncpg://user:pass@primary.alloydb.internal:5432/mydb"],
                    "read": ["postgresql+asyncpg://user:pass@read-pool.alloydb.internal:5432/mydb"],
                },
            )

    .. tab-item:: Amazon Aurora PostgreSQL

        .. code-block:: python

            from advanced_alchemy.config.routing import RoutingConfig

            aurora_routing = RoutingConfig(
                engines={
                    "default": ["postgresql+asyncpg://user:pass@cluster-writer.rds.amazonaws.com:5432/mydb"],
                    "read": ["postgresql+asyncpg://user:pass@cluster-reader.rds.amazonaws.com:5432/mydb"],
                },
            )

Disabling Routing for Debugging
-------------------------------

Set ``enabled=False`` on :class:`~advanced_alchemy.config.routing.RoutingConfig` to send all read and write queries to the first engine in ``default_group``:

.. code-block:: python

    from advanced_alchemy.config.routing import RoutingConfig

    disabled_routing = RoutingConfig(
        engines={
            "default": ["postgresql+asyncpg://user:pass@primary:5432/db"],
            "read": ["postgresql+asyncpg://user:pass@replica:5432/db"],
        },
        enabled=False,
    )

See Also
--------

- :doc:`/reference/routing`
- :doc:`/reference/config/asyncio`
- :doc:`/usage/repositories/index`
