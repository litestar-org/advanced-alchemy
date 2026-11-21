=============
OpenTelemetry
=============

Advanced Alchemy looks up SQLAlchemy's ``create_engine`` and ``create_async_engine`` each time it creates an engine. OpenTelemetry's `SQLAlchemy instrumentation <https://pypi.org/project/opentelemetry-instrumentation-sqlalchemy/>`__ therefore traces the engines Advanced Alchemy creates with its default factories, including each engine in a :doc:`routing <routing>` configuration, without an Advanced Alchemy setting.

Installation
------------

.. code-block:: bash

    pip install opentelemetry-sdk opentelemetry-instrumentation-sqlalchemy

Enabling Tracing
----------------

Call ``SQLAlchemyInstrumentor().instrument()`` once at application startup, before the first engine is created:

.. code-block:: python

    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

    from advanced_alchemy.config import SQLAlchemyAsyncConfig

    SQLAlchemyInstrumentor().instrument()

    config = SQLAlchemyAsyncConfig(connection_string="postgresql+asyncpg://user:pass@localhost/db")

Queries on those engines are then traced. Which spans are recorded and exported depends on the OpenTelemetry SDK configuration (tracer provider, exporter, sampling), which your application sets up; Advanced Alchemy does not.

.. note::

    Each ``opentelemetry-instrumentation-sqlalchemy`` release declares the SQLAlchemy and Python versions it supports. For example, 0.66b2 requires Python 3.10 or later and SQLAlchemy earlier than 2.1. On an unsupported SQLAlchemy version, ``instrument()`` logs an error and traces nothing.

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
