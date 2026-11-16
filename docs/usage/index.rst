===========
Usage Guide
===========

Imagine you are building a blog with **Posts**, **Authors**, and **Tags**. A reader opens your home page, asks for page 2 of published posts, and creates a comment.

Advanced Alchemy organizes that work into three clear steps so your route handlers stay tiny and easy to test:

.. raw:: html

    <div class="aa-diagram">
        <img src="../_static/diagrams/architecture-overview-light.svg" alt="How Advanced Alchemy Fits Into Your App" class="aa-diagram--light" />
        <img src="../_static/diagrams/architecture-overview-dark.svg" alt="How Advanced Alchemy Fits Into Your App" class="aa-diagram--dark" />
    </div>

1. **Models** describe what your tables look like in the database (such as a post's title, author, and timestamps).
2. **Repositories** run SQL queries for one table—adding rows, filtering, sorting, and paginating without repeating query code.
3. **Services** sit in front of repositories to validate incoming API schemas (Pydantic or Msgspec) and enforce your app's business rules.

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

      Keep business rules in one place and convert database rows straight into Pydantic or Msgspec responses.

    .. grid-item-card:: :octicon:`plug` 4. Framework Integrations
      :link: frameworks/index
      :link-type: doc

      Connect your services to Litestar, FastAPI, Starlette, Flask, Sanic, or :doc:`Google ADK <adk/index>` with automatic session management.

Scaling and Day-Two Tools
-------------------------

Once your core tables and routes are running, you can turn on operational features without rewriting your queries:

* :doc:`Replica Routing <routing>` — Send writes to your primary database and spread reads across read replicas.
* :doc:`Caching <caching>` — Cache frequent lookups in Redis or memory and clear stale entries automatically on commit.
* :doc:`CLI & Migrations <cli>` — Generate and apply Alembic schema migrations from the terminal.
* :doc:`Database Seeding <database_seeding>` — Load starter data from JSON or CSV files.
* :doc:`Google ADK <adk/index>` — Persist agent sessions, artifacts, and searchable memory with Advanced Alchemy models.
