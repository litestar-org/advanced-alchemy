=============
OpenTelemetry
=============

Advanced Alchemy looks up SQLAlchemy's ``create_engine`` and ``create_async_engine`` each time it creates an engine. OpenTelemetry's `SQLAlchemy instrumentation <https://pypi.org/project/opentelemetry-instrumentation-sqlalchemy/>`__ therefore traces the engines Advanced Alchemy creates with its default factories, including each engine in a :doc:`routing <routing>` configuration, without an Advanced Alchemy setting.

Installation
------------

.. tab-set::
    :sync-group: pkg

    .. tab-item:: uv
        :sync: uv

        .. code-block:: bash

            uv add opentelemetry-sdk opentelemetry-instrumentation-sqlalchemy

    .. tab-item:: pip
        :sync: pip

        .. code-block:: bash

            pip install opentelemetry-sdk opentelemetry-instrumentation-sqlalchemy

    .. tab-item:: pdm
        :sync: pdm

        .. code-block:: bash

            pdm add opentelemetry-sdk opentelemetry-instrumentation-sqlalchemy

    .. tab-item:: poetry
        :sync: poetry

        .. code-block:: bash

            poetry add opentelemetry-sdk opentelemetry-instrumentation-sqlalchemy

Enabling Tracing
----------------

Call ``SQLAlchemyInstrumentor().instrument()`` once before the first engine is created. For standalone configs and Litestar, calling it before app startup works because engines are created during lifespan startup. For FastAPI, Starlette, Flask, and Sanic, call it before attaching ``AdvancedAlchemy(config, app)`` or calling ``init_app(app)``, which creates engines eagerly:

.. code-block:: python

    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

    from advanced_alchemy.config import SQLAlchemyAsyncConfig

    SQLAlchemyInstrumentor().instrument()

    config = SQLAlchemyAsyncConfig(connection_string="postgresql+asyncpg://user:pass@localhost/db")

Queries on those engines are then traced. Which spans are recorded and exported depends on the OpenTelemetry SDK configuration (tracer provider, exporter, sampling), which your application sets up; Advanced Alchemy does not.

.. note::

    Advanced Alchemy does not add an OpenTelemetry dependency, so installs and tests across Python 3.9--3.15 and SQLAlchemy 2.0/2.1 are unaffected. Each ``opentelemetry-instrumentation-sqlalchemy`` release enforces its own Python and SQLAlchemy version bounds; for example, 0.66b2 requires Python 3.10 or later and SQLAlchemy earlier than 2.1. On an unsupported SQLAlchemy version, ``instrument()`` logs a version conflict and skips tracing gracefully without breaking engine creation.

Engines Created Elsewhere
-------------------------

``instrument()`` traces engines created through SQLAlchemy's factories after it runs. It does not trace:

* an engine created before that call, such as one passed as ``engine_instance`` or through ``session_config`` ``bind`` / ``binds``
* engines owned by a custom ``session_maker``
* engines returned by a custom ``create_engine_callable`` that keeps its own reference to the factory

Calls to ``instrument()`` are ignored while the instrumentor is already active, so pass existing engines to the first call. Async engines need their ``sync_engine``:

.. code-block:: python

    SQLAlchemyInstrumentor().instrument(engines=[engine.sync_engine])

This covers engines that already exist. Engines that a custom factory creates later through its own reference to the factory cannot be added afterwards.
