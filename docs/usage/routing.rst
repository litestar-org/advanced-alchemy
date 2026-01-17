==================
Read/Write Routing
==================

Advanced Alchemy provides automatic routing of read operations to read replicas while directing
write operations to the primary database. This enables better scalability by distributing read
load across multiple replica databases.

Why Use Read/Write Routing?
----------------------------

Read/write routing is essential for scaling read-heavy applications:

- **Scalability**: Distribute read load across multiple replica databases
- **Performance**: Reduce primary database load by offloading read queries
- **High Availability**: Continue serving reads even if primary is under maintenance
- **Cloud-Native**: Leverage managed database replicas (AWS Aurora, Google Cloud SQL, etc.)

Quick Start
-----------

Basic configuration with a single replica:

.. code-block:: python

    from advanced_alchemy.config import SQLAlchemyAsyncConfig
    from advanced_alchemy.config.routing import RoutingConfig

    config = SQLAlchemyAsyncConfig(
        routing_config=RoutingConfig(
            primary_connection_string="postgresql+asyncpg://user:pass@primary:5432/db",
            read_replicas=[
                "postgresql+asyncpg://user:pass@replica1:5432/db",
            ],
        ),
    )

    # Create session factory
    session_maker = config.create_session_maker()

    # Use with repository - reads automatically go to replica
    async with session_maker() as session:
        repo = UserRepository(session=session)
        users = await repo.list()  # Routes to replica

Configuration
-------------

Routing Strategy
~~~~~~~~~~~~~~~~

Choose how replicas are selected for read operations:

.. code-block:: python

    from advanced_alchemy.config.routing import RoutingConfig, RoutingStrategy

    # Round-robin (default) - distributes load evenly
    config = RoutingConfig(
        primary_connection_string="postgresql+asyncpg://...",
        read_replicas=["postgresql+asyncpg://replica1:5432/db", "..."],
        routing_strategy=RoutingStrategy.ROUND_ROBIN,
    )

    # Random - randomly selects replica
    config = RoutingConfig(
        primary_connection_string="postgresql+asyncpg://...",
        read_replicas=["postgresql+asyncpg://replica1:5432/db", "..."],
        routing_strategy=RoutingStrategy.RANDOM,
    )

Multiple Replicas
~~~~~~~~~~~~~~~~~

Configure multiple replicas with custom weights:

.. code-block:: python

    from advanced_alchemy.config.routing import RoutingConfig, ReplicaConfig

    config = RoutingConfig(
        primary_connection_string="postgresql+asyncpg://user:pass@primary:5432/db",
        read_replicas=[
            ReplicaConfig(
                connection_string="postgresql+asyncpg://user:pass@replica1:5432/db",
                weight=2,  # Gets 2x traffic
                name="replica-1-us-east",
            ),
            ReplicaConfig(
                connection_string="postgresql+asyncpg://user:pass@replica2:5432/db",
                weight=1,
                name="replica-2-us-west",
            ),
        ],
        routing_strategy=RoutingStrategy.ROUND_ROBIN,
    )

Sticky-After-Write
~~~~~~~~~~~~~~~~~~

By default, routing ensures **read-your-writes consistency**. After a write operation,
all subsequent reads use the primary database until the transaction is committed:

.. code-block:: python

    async with session_maker() as session:
        repo = UserRepository(session=session)

        # Read routes to replica
        users = await repo.list()

        # Write routes to primary
        new_user = await repo.add(User(name="Alice"))

        # Read now routes to primary (sticky-after-write)
        user = await repo.get(new_user.id)

        # Commit resets stickiness
        await session.commit()

        # Read can use replica again
        users = await repo.list()

To disable sticky-after-write:

.. code-block:: python

    config = RoutingConfig(
        primary_connection_string="postgresql+asyncpg://...",
        read_replicas=["..."],
        sticky_after_write=False,  # Reads may not see recent writes
    )

Routing Rules
-------------

The routing layer follows these rules:

1. **INSERT/UPDATE/DELETE** → Primary
2. **SELECT with FOR UPDATE** → Primary
3. **SELECT after write** (if sticky-after-write enabled) → Primary
4. **SELECT (no writes)** → Replica (round-robin/random)
5. **After commit** → Reset stickiness, replicas available again

FOR UPDATE Detection
~~~~~~~~~~~~~~~~~~~~

Queries with ``FOR UPDATE`` are automatically routed to the primary:

.. code-block:: python

    from sqlalchemy import select

    async with session_maker() as session:
        # Routes to primary (FOR UPDATE detected)
        stmt = select(User).where(User.id == user_id).with_for_update()
        result = await session.execute(stmt)
        user = result.scalar_one()

Advanced Routing with Bind Groups
---------------------------------

While the primary/read-replica pattern is common, you might need more complex routing scenarios, such as:

- Dedicated analytics database
- Region-specific replicas
- Separate reporting databases
- Multiple primary databases (sharding)

You can achieve this by defining **Bind Groups** in your configuration.

Configuration
~~~~~~~~~~~~~

Use the ``engines`` dictionary to define named groups of engines:

.. code-block:: python

    from advanced_alchemy.config import SQLAlchemyAsyncConfig
    from advanced_alchemy.config.routing import RoutingConfig

    config = SQLAlchemyAsyncConfig(
        routing_config=RoutingConfig(
            # Define multiple engine groups
            engines={
                "default": ["postgresql+asyncpg://primary:5432/db"],
                "read": ["postgresql+asyncpg://replica1:5432/db"],
                "analytics": ["postgresql+asyncpg://analytics:5432/db"],
                "reporting": [
                    "postgresql+asyncpg://report-1:5432/db",
                    "postgresql+asyncpg://report-2:5432/db",
                ],
            },
            default_group="default",
            read_group="read",
        ),
    )

Using Bind Groups
~~~~~~~~~~~~~~~~~

You can route operations to specific groups using context managers or explicit parameters.

**Context Manager**

Use ``use_bind_group`` to route all operations within a block to a specific group:

.. code-block:: python

    from advanced_alchemy.routing import use_bind_group

    async with session_maker() as session:
        repo = UserRepository(session=session)

        # Route to analytics database
        with use_bind_group("analytics"):
            stats = await repo.count()

        # Route to reporting group (load balanced if multiple engines)
        with use_bind_group("reporting"):
            report = await repo.list()

**Explicit Parameter**

All repository methods accept a ``bind_group`` parameter:

.. code-block:: python

    # Query directly from analytics group
    users = await repo.list(bind_group="analytics")

    # Count from reporting group
    count = await repo.count(bind_group="reporting")

Context Managers
----------------

Use context managers for explicit control over routing:

Primary Context
~~~~~~~~~~~~~~~

Force operations to use the default (primary) group. This is an alias for ``use_bind_group("default")``:

.. code-block:: python

    from advanced_alchemy.routing import primary_context

    async with session_maker() as session:
        repo = UserRepository(session=session)

        # Force this read to use primary (e.g. for critical consistency)
        with primary_context():
            critical_user = await repo.get(user_id)

Replica Context
~~~~~~~~~~~~~~~

Force operations to use the read group. This is an alias for ``use_bind_group("read")``:

.. code-block:: python

    from advanced_alchemy.routing import replica_context

    async with session_maker() as session:
        repo = UserRepository(session=session)

        # Force read from replica (even if sticky-primary is active)
        with replica_context():
            users = await repo.list()

Temporarily Disable Routing
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Disable routing to send all traffic to the default primary engine:

.. code-block:: python

    config = RoutingConfig(
        engines={"default": ["..."], "read": ["..."]},
        enabled=False,  # All traffic to default group's first engine
    )

Framework Integration
---------------------

Routing automatically integrates with all supported frameworks.

Litestar
~~~~~~~~

.. code-block:: python

    from litestar import Litestar
    from litestar.plugins.sqlalchemy import SQLAlchemyAsyncConfig, SQLAlchemyPlugin
    from advanced_alchemy.config.routing import RoutingConfig

    config = SQLAlchemyAsyncConfig(
        routing_config=RoutingConfig(
            primary_connection_string="postgresql+asyncpg://primary:5432/db",
            read_replicas=["postgresql+asyncpg://replica1:5432/db"],
        ),
    )

    app = Litestar(plugins=[SQLAlchemyPlugin(config=config)])

Routing context is automatically reset per request.

FastAPI
~~~~~~~

.. code-block:: python

    from fastapi import FastAPI, Depends
    from sqlalchemy.ext.asyncio import AsyncSession
    from advanced_alchemy.extensions.fastapi import SQLAlchemyAsyncConfig, get_session

    config = SQLAlchemyAsyncConfig(
        routing_config=RoutingConfig(
            primary_connection_string="postgresql+asyncpg://primary:5432/db",
            read_replicas=["postgresql+asyncpg://replica1:5432/db"],
        ),
    )

    app = FastAPI()

    @app.get("/users")
    async def list_users(session: AsyncSession = Depends(get_session)):
        repo = UserRepository(session=session)
        return await repo.list()  # Routes to replica

Flask
~~~~~

.. code-block:: python

    from flask import Flask
    from advanced_alchemy.extensions.flask import SQLAlchemyExtension
    from advanced_alchemy.config.routing import RoutingConfig

    app = Flask(__name__)
    app.config["SQLALCHEMY_ROUTING_CONFIG"] = RoutingConfig(
        primary_connection_string="postgresql://primary:5432/db",
        read_replicas=["postgresql://replica1:5432/db"],
    )

    db = SQLAlchemyExtension(app=app)

AWS Aurora / Cloud SQL Example
-------------------------------

AWS Aurora and Google Cloud SQL provide automatic replica endpoints:

.. code-block:: python

    # AWS Aurora configuration
    config = RoutingConfig(
        primary_connection_string=(
            "postgresql+asyncpg://user:pass@mydb-cluster.cluster-xxx.us-east-1.rds.amazonaws.com:5432/mydb"
        ),
        read_replicas=[
            # Aurora reader endpoint (load-balanced across replicas)
            "postgresql+asyncpg://user:pass@mydb-cluster.cluster-ro-xxx.us-east-1.rds.amazonaws.com:5432/mydb",
        ],
    )

.. code-block:: python

    # Google Cloud SQL configuration
    config = RoutingConfig(
        primary_connection_string="postgresql+asyncpg://user:pass@primary-ip:5432/mydb",
        read_replicas=[
            "postgresql+asyncpg://user:pass@replica1-ip:5432/mydb",
            "postgresql+asyncpg://user:pass@replica2-ip:5432/mydb",
        ],
    )

Best Practices
--------------

1. **Use Sticky-After-Write**: Keep ``sticky_after_write=True`` (default) to avoid read-after-write inconsistency
2. **Monitor Replica Lag**: Ensure replicas stay close to primary (< 1 second lag)
3. **Test Failover**: Verify behavior when replicas are unavailable
4. **Use Context Managers**: Use ``primary_context()`` for critical reads that must be up-to-date
5. **Connection Pooling**: Configure appropriate pool sizes for primary and replicas
6. **Health Checks**: Implement health checks to detect unhealthy replicas (future feature)

Troubleshooting
---------------

Reads Not Using Replicas
~~~~~~~~~~~~~~~~~~~~~~~~~

Check if sticky-after-write is active:

.. code-block:: python

    from advanced_alchemy.routing import stick_to_primary_var

    # Check current state
    if stick_to_primary_var.get():
        print("Currently stuck to primary")

Reset routing context manually:

.. code-block:: python

    from advanced_alchemy.routing import reset_routing_context

    reset_routing_context()

Stale Reads from Replicas
~~~~~~~~~~~~~~~~~~~~~~~~~~

If replicas have significant lag, use ``primary_context()`` for critical reads:

.. code-block:: python

    from advanced_alchemy.routing import primary_context

    # Force primary for latest data
    with primary_context():
        user = await repo.get(user_id)

Temporarily Disable Routing
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

For debugging, disable routing to send all traffic to primary:

.. code-block:: python

    config = RoutingConfig(
        primary_connection_string="postgresql+asyncpg://...",
        read_replicas=["..."],
        enabled=False,  # All to primary
    )

See Also
--------

- :doc:`/reference/routing` - API Reference
- :doc:`/usage/repositories` - Repository Pattern
- :doc:`/usage/services` - Service Layer
- :doc:`/reference/config/asyncio` - Async Configuration
