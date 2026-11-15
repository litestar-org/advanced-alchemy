=================
Flask Integration
=================

Advanced Alchemy plugs into both classic synchronous Flask apps and ``async def`` Flask routes—giving every request a managed SQLAlchemy session, adding a ``jsonify()`` helper onto your services, and registering ``flask database`` migration commands automatically.

What's Included for Flask
-------------------------

.. list-table::
   :header-rows: 1
   :widths: 28 46 26

   * - Feature
     - What It Gives You
     - Reference
   * - **App-Context Sessions**
     - Reuses one session per Flask request and closes or commits it cleanly on teardown.
     - :doc:`API </reference/extensions/flask/index>`
   * - **FlaskServiceMixin**
     - Adds ``service.jsonify(...)`` to return paginated ``msgspec`` or Pydantic schemas directly from routes.
     - :doc:`API </reference/extensions/flask/index>`
   * - **Sync & Async Support**
     - Works with standard sync engines, async engines, and multiple databases via ``bind_key``.
     - :doc:`API </reference/extensions/flask/index>`
   * - **Flask CLI**
     - Registers ``flask database init``, ``upgrade``, and ``downgrade`` commands automatically.
     - :doc:`CLI Guide </usage/cli>`

Installation
------------

.. tab-set::
    :sync-group: pkg

    .. tab-item:: uv
        :sync: uv

        .. code-block:: bash

            uv add "advanced-alchemy[flask]"

    .. tab-item:: pip
        :sync: pip

        .. code-block:: bash

            pip install "advanced-alchemy[flask]"

    .. tab-item:: pdm
        :sync: pdm

        .. code-block:: bash

            pdm add "advanced-alchemy[flask]"

    .. tab-item:: poetry
        :sync: poetry

        .. code-block:: bash

            poetry add "advanced-alchemy[flask]"

Sync, Async, and Multi-Database Setup
-------------------------------------

.. tab-set::

    .. tab-item:: Sync Flask (WSGI)

        .. code-block:: python

            from flask import Flask
            from sqlalchemy import select
            from sqlalchemy.orm import Mapped
            from advanced_alchemy.extensions.flask import AdvancedAlchemy, SQLAlchemySyncConfig, base


            class User(base.BigIntBase):
                __tablename__ = "flask_user_account"
                name: Mapped[str]


            app = Flask("flask_basic_db")
            alchemy = AdvancedAlchemy(
                SQLAlchemySyncConfig(connection_string="sqlite:///:memory:", commit_mode="autocommit", create_all=True),
                app,
            )


            @app.route("/users")
            def list_users() -> dict[str, list[dict[str, object]]]:
                session = alchemy.get_sync_session()
                users = session.execute(select(User)).scalars().all()
                return {"users": [{"id": u.id, "name": u.name} for u in users]}

    .. tab-item:: Async Flask

        .. code-block:: python

            from advanced_alchemy.extensions.flask import SQLAlchemyAsyncConfig

            async_app = Flask("flask_async_db")
            async_alchemy = AdvancedAlchemy(
                SQLAlchemyAsyncConfig(connection_string="sqlite+aiosqlite:///:memory:", create_all=True),
                async_app,
            )


            @async_app.route("/users")
            async def list_users_async() -> dict[str, list[dict[str, object]]]:
                session = async_alchemy.get_async_session()
                users = (await session.execute(select(User))).scalars().all()
                return {"users": [{"id": u.id, "name": u.name} for u in users]}

    .. tab-item:: Multiple Databases

        .. code-block:: python

            multi_db_app = Flask("flask_multi_db")
            multi_alchemy = AdvancedAlchemy(
                [
                    SQLAlchemySyncConfig(connection_string="sqlite:///:memory:", bind_key="users"),
                    SQLAlchemySyncConfig(connection_string="sqlite:///:memory:", bind_key="products"),
                ],
                multi_db_app,
            )

            with multi_db_app.app_context():
                users_session = multi_alchemy.get_sync_session("users")
                products_session = multi_alchemy.get_sync_session("products")

Using Services and JSON Responses
---------------------------------

Mix ``FlaskServiceMixin`` into your service class so route handlers can paginate, convert rows to schemas, and return a Flask JSON ``Response`` in one clean step:

.. code-block:: python

    import datetime
    from typing import Optional
    from uuid import UUID
    from flask import Response, request
    from msgspec import Struct
    from sqlalchemy.orm import Mapped
    from advanced_alchemy.extensions.flask import FlaskServiceMixin, filters, repository, service


    class Author(base.UUIDBase):
        __tablename__ = "flask_author"
        name: Mapped[str]
        dob: Mapped[Optional[datetime.date]]


    class AuthorSchema(Struct):
        name: str
        id: Optional[UUID] = None
        dob: Optional[datetime.date] = None


    class AuthorService(service.SQLAlchemySyncRepositoryService[Author], FlaskServiceMixin):
        class Repo(repository.SQLAlchemySyncRepository[Author]):
            model_type = Author
        repository_type = Repo


    service_app = Flask("flask_service_db")
    alchemy_config = SQLAlchemySyncConfig(
        connection_string="sqlite:///:memory:", commit_mode="autocommit", create_all=True
    )
    alchemy = AdvancedAlchemy(alchemy_config, service_app)


    @service_app.route("/authors", methods=["GET"])
    def list_authors() -> Response:
        limit_offset = filters.LimitOffset(
            limit=request.args.get("pageSize", 10, type=int),
            offset=request.args.get("pageSize", 10, type=int) * (request.args.get("currentPage", 1, type=int) - 1),
        )
        authors_service = AuthorService(session=alchemy.get_sync_session())
        results, total = authors_service.get_many_and_count(limit_offset)
        return authors_service.jsonify(
            authors_service.to_schema(results, total, filters=[limit_offset], schema_type=AuthorSchema)
        )

Running Migrations with Flask CLI
---------------------------------

.. code-block:: bash

    flask database init
    flask database revision --autogenerate -m "add users table"
    flask database upgrade

See :doc:`/reference/extensions/flask/index` for full API signatures.
