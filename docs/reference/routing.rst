=======
routing
=======

API Reference for the ``routing`` module

.. note:: Private methods and attributes are not included in the API reference.

Read/Write Routing
------------------

The routing module provides automatic routing of read operations to read replicas while directing
write operations to the primary database. This enables better scalability by distributing read
load across multiple replica databases.

Key Features
~~~~~~~~~~~~

- **Automatic Routing**: SELECT queries route to replicas, INSERT/UPDATE/DELETE to primary
- **Sticky-After-Write**: Ensures read-your-writes consistency by routing reads to primary after writes
- **FOR UPDATE Detection**: Automatically routes ``SELECT ... FOR UPDATE`` to primary
- **Multiple Replica Support**: Round-robin or random selection across multiple replicas
- **Context Managers**: Explicit control with ``primary_context()`` and ``replica_context()``
- **Framework Integration**: Built-in support for Litestar, FastAPI, Flask, Sanic, Starlette

Configuration Classes
~~~~~~~~~~~~~~~~~~~~~

.. autoclass:: advanced_alchemy.config.routing.RoutingConfig
    :members:
    :undoc-members:

.. autoclass:: advanced_alchemy.config.routing.ReplicaConfig
    :members:
    :undoc-members:

.. autoclass:: advanced_alchemy.config.routing.RoutingStrategy
    :members:
    :undoc-members:

Session Classes
~~~~~~~~~~~~~~~

.. autoclass:: advanced_alchemy.routing.RoutingSession
    :members:
    :undoc-members:
    :special-members: __init__

.. autoclass:: advanced_alchemy.routing.RoutingAsyncSession
    :members:
    :undoc-members:
    :special-members: __init__

Session Makers
~~~~~~~~~~~~~~

.. autoclass:: advanced_alchemy.routing.RoutingAsyncSessionMaker
    :members:
    :undoc-members:

.. autoclass:: advanced_alchemy.routing.RoutingSyncSessionMaker
    :members:
    :undoc-members:

Replica Selectors
~~~~~~~~~~~~~~~~~

.. autoclass:: advanced_alchemy.routing.ReplicaSelector
    :members:
    :undoc-members:

.. autoclass:: advanced_alchemy.routing.RoundRobinSelector
    :members:
    :undoc-members:

.. autoclass:: advanced_alchemy.routing.RandomSelector
    :members:
    :undoc-members:

Context Managers
~~~~~~~~~~~~~~~~

.. autofunction:: advanced_alchemy.routing.primary_context

.. autofunction:: advanced_alchemy.routing.replica_context

.. autofunction:: advanced_alchemy.routing.reset_routing_context

Context Variables
~~~~~~~~~~~~~~~~~

.. autodata:: advanced_alchemy.routing.stick_to_primary_var
    :annotation:

.. autodata:: advanced_alchemy.routing.force_primary_var
    :annotation:
