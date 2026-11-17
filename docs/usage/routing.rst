==================
Read/Write Routing
==================

Read/write routing directs mutating statements to a **Primary Database** and distributes ``SELECT`` queries across one or more **Read Replica** pools without changing repository or service calls:

.. raw:: html

    <div class="aa-diagram">
        <img src="../_static/diagrams/routing-topology-light.svg" alt="How Read and Write Routing Works" class="aa-diagram--light" />
        <img src="../_static/diagrams/routing-topology-dark.svg" alt="How Read and Write Routing Works" class="aa-diagram--dark" />
    </div>

Primary Pinning After Writes
----------------------------

Asynchronous replication introduces replication lag between the primary database and read replicas. When ``sticky_after_write=True`` (the default), once a session flushes a write, subsequent reads within that transaction remain pinned to the primary database until ``commit()`` or ``rollback()`` completes:

.. raw:: html

    <div class="aa-diagram">
        <img src="../_static/diagrams/routing-sticky-light.gif" alt="Reading Your Own Changes Without Stale Data" class="aa-diagram--light" />
        <img src="../_static/diagrams/routing-sticky-dark.gif" alt="Reading Your Own Changes Without Stale Data" class="aa-diagram--dark" />
    </div>

Setting Up Primary and Replica Pools
------------------------------------

Define your ``"default"`` writer and ``"read"`` replica pools in ``RoutingConfig`` and pass it to ``SQLAlchemyAsyncConfig`` (or ``SQLAlchemySyncConfig``):

.. tab-set::

    .. tab-item:: Weighted Replicas

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
                    routing_strategy=RoutingStrategy.ROUND_ROBIN,
                    sticky_after_write=True,
                ),
            )

    .. tab-item:: Cloud SQL

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

    .. tab-item:: AlloyDB & Aurora

        .. code-block:: python

            from advanced_alchemy.config.routing import RoutingConfig

            pool_endpoint_routing = RoutingConfig(
                engines={
                    "default": ["postgresql+asyncpg://user:pass@writer.db.internal:5432/mydb"],
                    "read": ["postgresql+asyncpg://user:pass@reader-pool.db.internal:5432/mydb"],
                },
            )

    .. tab-item:: Turn Off in Local Dev

        .. code-block:: python

            from advanced_alchemy.config.routing import RoutingConfig

            local_routing = RoutingConfig(
                engines={
                    "default": ["postgresql+asyncpg://user:pass@localhost:5432/mydb"],
                },
                enabled=False,
            )

Choosing a Pool Manually
------------------------

Use ``primary_context()``, ``replica_context()``, or ``use_bind_group()`` to target a specific engine pool for an individual operation (such as forcing a primary read or routing reporting queries to an ``"analytics"`` pool):

.. code-block:: python

    from typing import Any
    from advanced_alchemy.routing import primary_context, replica_context, use_bind_group


    async def run_targeted_queries(repo: Any, item_id: Any) -> tuple[Any, list[Any], int]:
        with primary_context():
            fresh_row = await repo.get(item_id)

        with replica_context():
            feed_rows = await repo.get_many()

        with use_bind_group("analytics"):
            report_count = await repo.count()

        return fresh_row, feed_rows, report_count

Complete Runnable Example
-------------------------

.. dropdown:: View Complete SQLite Primary & Replica Script
    :icon: code

    .. literalinclude:: /examples/routing/read_write_routing.py
        :language: python

See :doc:`/reference/routing` for the full routing API reference.
