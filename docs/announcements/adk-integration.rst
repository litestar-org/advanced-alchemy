:orphan:

================
ADK Integration
================

Advanced Alchemy now includes Google ADK 2.x persistence services for sessions,
artifacts, and memory. The integration follows the same model ownership pattern
as the existing framework session extension: applications subclass mixins and
keep control over table names, extra columns, and migrations.

Highlights:

- ADK session persistence backed by Advanced Alchemy model mixins.
- Transactional artifact storage through ``FileObject`` and configured storage
  backends.
- SQL-backed memory search with PostgreSQL full-text search support.
- Litestar, FastAPI, Flask, Sanic, and Starlette framework helpers.

See :doc:`../usage/adk/index` for setup and migration guidance.
