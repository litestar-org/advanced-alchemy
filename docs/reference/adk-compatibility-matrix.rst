========================
ADK Compatibility Matrix
========================

The ADK extension targets Google ADK 2.x and later.

.. list-table::
    :header-rows: 1

    * - Area
      - Status
      - Notes
    * - Python
      - 3.10+
      - Matches Google ADK 2.x packaging requirements.
    * - SQLite
      - Tested
      - Focused unit and SQLite integration coverage for sessions, artifacts, and memory.
    * - PostgreSQL
      - Supported
      - Memory search uses PostgreSQL full-text search by default.
    * - MySQL, Oracle, SQL Server
      - Supported by SQLAlchemy model layer
      - Use existing Advanced Alchemy database fixtures and markers for backend-specific validation.
    * - Litestar, FastAPI, Flask, Sanic, Starlette
      - Supported
      - Framework helpers wire ADK services from existing Advanced Alchemy sessions.
    * - Spanner and CockroachDB
      - Not part of the initial ADK matrix
      - ADK upstream does not define first-party support expectations for these backends.
