======================
Framework Integrations
======================

Instead of manually opening, committing, and closing SQLAlchemy sessions inside every web route, Advanced Alchemy plugs directly into your web framework.

Each integration starts and stops database engines cleanly with your app, gives every incoming request its own session, and re-exports core models, repositories, services, and filters from one place.

At a Glance
-----------

.. list-table::
   :header-rows: 1
   :widths: 16 24 42 18

   * - Framework
     - Setup Class
     - Included Features
     - CLI Tool
   * - :doc:`Litestar <litestar>`
     - ``SQLAlchemyPlugin``
     - Automatic DI, :doc:`DTOs & filters <litestar_dtos>`, :doc:`session stores <litestar_sessions>`, and :doc:`file uploads <litestar_storage>`
     - ``litestar database``
   * - :doc:`FastAPI <fastapi>`
     - ``AdvancedAlchemy``
     - Lifespan sessions, :doc:`Depends services & filters <fastapi_dependencies>`, and :doc:`file uploads <fastapi_storage>`
     - ``alchemy``
   * - :doc:`Starlette <starlette>`
     - ``AdvancedAlchemy``
     - ASGI session middleware, sync & async sessions, and multi-database support
     - ``alchemy``
   * - :doc:`Flask <flask>`
     - ``AdvancedAlchemy``
     - Request-context sessions, sync/async bridge, and ``jsonify()`` service helper
     - ``flask database``
   * - :doc:`Sanic <sanic>`
     - ``AdvancedAlchemy``
     - ``sanic-ext`` dependency injection, ``request.ctx`` sessions, and multi-binds
     - ``alchemy``

Choose Your Framework
---------------------

.. grid:: 1 1 2 2
    :padding: 0
    :gutter: 3

    .. grid-item-card:: :octicon:`zap` Litestar
      :link: litestar
      :link-type: doc

      Full plugin integration with DTOs, controller dependency injection, server-side session stores, file storage, and ``litestar database`` commands.

    .. grid-item-card:: :octicon:`rocket` FastAPI
      :link: fastapi
      :link-type: doc

      ASGI lifespan management, typed ``Depends`` providers for services and OpenAPI query filters, multi-binds, and multipart file storage.

    .. grid-item-card:: :octicon:`globe` Starlette
      :link: starlette
      :link-type: doc

      Lightweight ASGI middleware that attaches sync or async sessions to ``request.state`` across single or multiple databases.

    .. grid-item-card:: :octicon:`server` Flask
      :link: flask
      :link-type: doc

      WSGI and async route sessions, ``FlaskServiceMixin`` JSON responses, and built-in ``flask database`` migration commands.

    .. grid-item-card:: :octicon:`flame` Sanic
      :link: sanic
      :link-type: doc

      Automatic session injection with ``sanic-ext``, lazy ``request.ctx`` sessions, and multi-database bind keys.

    .. grid-item-card:: :octicon:`book` Extensions API Reference
      :link: /reference/extensions/index
      :link-type: doc

      Full class, provider, DTO, store, and CLI signatures for all five framework packages.
