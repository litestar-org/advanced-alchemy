===========
Usage Guide
===========

Advanced Alchemy separates database access into three layers so route handlers remain concise and testable:

.. raw:: html

    <div class="aa-diagram">
        <img src="../_static/diagrams/architecture-overview-light.svg" alt="How Advanced Alchemy Fits Into Your App" class="aa-diagram--light" />
        <img src="../_static/diagrams/architecture-overview-dark.svg" alt="How Advanced Alchemy Fits Into Your App" class="aa-diagram--dark" />
    </div>

1. **Models** define SQLAlchemy declarative tables with primary keys, audit timestamps, and custom column types.
2. **Repositories** execute single-model CRUD, filtering, sorting, pagination, and bulk upsert queries.
3. **Services** wrap repositories to convert between ORM models and typed API schemas (Pydantic, Msgspec, dataclass, ``attrs``, or SQLModel) and apply domain logic.

.. grid:: 1 1 2 2
    :padding: 0
    :gutter: 3

    .. grid-item-card:: :octicon:`table` 1. Data Modeling
      :link: modeling/index
      :link-type: doc

      Define tables with automatic UUID or integer primary keys, audit timestamps, JSON, encrypted columns, and file storage.

    .. grid-item-card:: :octicon:`database` 2. Repositories
      :link: repositories/index
      :link-type: doc

      Add, fetch, filter, paginate, and bulk-upsert records using async or sync sessions.

    .. grid-item-card:: :octicon:`package` 3. Services
      :link: services
      :link-type: doc

      Convert database rows into Pydantic, Msgspec, dataclass, attrs, or SQLModel schemas and centralize domain logic.

    .. grid-item-card:: :octicon:`plug` 4. Framework Integrations
      :link: frameworks/index
      :link-type: doc

      Connect your services to Litestar, FastAPI, Starlette, Flask, or Sanic with automatic session management.

Operational Features
--------------------

Enable routing, caching, migrations, and fixture seeding without rewriting repository queries:

* :doc:`Replica Routing <routing>`: Route writes to a primary database and distribute reads across replica pools.
* :doc:`Caching <caching>`: Cache lookups in memory, Redis, or Memcached with automatic invalidation on commit.
* :doc:`OpenTelemetry <opentelemetry>`: Trace queries, including routed replicas, with OpenTelemetry's SQLAlchemy instrumentation.
* :doc:`CLI & Migrations <cli>`: Generate and apply Alembic schema migrations from the terminal.
* :doc:`Database Seeding <database_seeding>`: Stream and load seed data from JSON, JSONL, or CSV fixtures.
