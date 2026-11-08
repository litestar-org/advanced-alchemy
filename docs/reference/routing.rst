=======
routing
=======

.. py:module:: advanced_alchemy.routing

Read/write replica session routing for SQLAlchemy engines and sessions. See
:class:`~advanced_alchemy.config.routing.RoutingConfig`,
:class:`~advanced_alchemy.config.routing.ReplicaConfig`, and
:class:`~advanced_alchemy.config.routing.RoutingStrategy` for configuration.

Routing Sessions & Session Makers
---------------------------------

.. autoclass:: advanced_alchemy.routing.RoutingAsyncSession
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.routing.RoutingSyncSession
    :members: get_bind
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.routing.RoutingAsyncSessionMaker
    :members: close_all
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.routing.RoutingSyncSessionMaker
    :members: close_all
    :no-inherited-members:
    :show-inheritance:

.. autofunction:: advanced_alchemy.routing.dispose_session_maker_async

.. autofunction:: advanced_alchemy.routing.dispose_session_maker_sync

Replica Selectors
-----------------

.. py:module:: advanced_alchemy.routing.selectors
    :no-typesetting:

.. autoclass:: advanced_alchemy.routing.selectors.EngineSelector
    :members: next
    :no-inherited-members:
    :show-inheritance:

.. py:currentmodule:: advanced_alchemy.routing

.. autoclass:: advanced_alchemy.routing.ReplicaSelector
    :members: next, has_replicas, count
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.routing.RoundRobinSelector
    :members: next
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.routing.RandomSelector
    :members: next
    :no-inherited-members:
    :show-inheritance:

Routing Context Managers & State
--------------------------------

.. autofunction:: advanced_alchemy.routing.primary_context

.. autofunction:: advanced_alchemy.routing.replica_context

.. autofunction:: advanced_alchemy.routing.use_bind_group

.. autofunction:: advanced_alchemy.routing.reset_routing_context

.. py:data:: stick_to_primary_var
    :type: contextvars.ContextVar[bool]

    Context variable tracking whether subsequent reads should stick to the primary after a write.

.. py:data:: force_primary_var
    :type: contextvars.ContextVar[bool]

    Context variable forcing operations onto the primary engine.
