=====================
Framework Integration
=====================

Advanced Alchemy integrates with multiple Python web frameworks.

.. toctree::
   :maxdepth: 1

   litestar
   fastapi
   flask

Overview
========

Advanced Alchemy provides framework-specific extensions for:

- Litestar (async)
- FastAPI (async)
- Flask (sync)
- Sanic (async)
- Starlette (async)

Framework Comparison
====================

.. list-table:: Framework Characteristics
   :header-rows: 1
   :widths: 20 20 30 30

   * - Framework
     - Async Support
     - Integration Method
     - Session Management
   * - Litestar
     - Yes
     - SQLAlchemyPlugin
     - Dependency injection
   * - FastAPI
     - Yes
     - AdvancedAlchemy extension
     - Depends()
   * - Flask
     - No (sync)
     - AdvancedAlchemy extension
     - Request context

Quick Start
===========

**Litestar**

.. code-block:: python

    from litestar import Litestar
    from advanced_alchemy.extensions.litestar import SQLAlchemyPlugin, SQLAlchemyAsyncConfig

    alchemy = SQLAlchemyPlugin(
        config=SQLAlchemyAsyncConfig(connection_string="sqlite+aiosqlite:///test.sqlite"),
    )
    app = Litestar(plugins=[alchemy])

**FastAPI**

.. code-block:: python

    from fastapi import FastAPI
    from advanced_alchemy.extensions.fastapi import AdvancedAlchemy, SQLAlchemyAsyncConfig

    app = FastAPI()
    alchemy = AdvancedAlchemy(
        config=SQLAlchemyAsyncConfig(connection_string="sqlite+aiosqlite:///test.sqlite"),
        app=app,
    )

**Flask**

.. code-block:: python

    from flask import Flask
    from advanced_alchemy.extensions.flask import AdvancedAlchemy, SQLAlchemySyncConfig

    app = Flask(__name__)
    alchemy = AdvancedAlchemy(
        config=SQLAlchemySyncConfig(connection_string="sqlite:///test.sqlite"),
        app=app,
    )

Next Steps
==========

- :doc:`litestar` - Litestar integration details
- :doc:`fastapi` - FastAPI integration details
- :doc:`flask` - Flask integration details

Related Topics
==============

- :doc:`../services/index` - Service layer for framework integration
- :doc:`../repositories/index` - Repository pattern
