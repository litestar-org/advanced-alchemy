=================
Flask Integration
=================

Advanced Alchemy integrates with Flask through :class:`~advanced_alchemy.extensions.flask.AdvancedAlchemy`, managing application-context sessions, synchronous and asynchronous SQLAlchemy configurations, and Flask CLI database migration commands.

Basic Setup
-----------

Use :class:`~advanced_alchemy.extensions.flask.SQLAlchemySyncConfig` for standard WSGI Flask applications:

.. code-block:: python

    from flask import Flask
    from sqlalchemy import select
    from sqlalchemy.orm import Mapped

    from advanced_alchemy.extensions.flask import AdvancedAlchemy, SQLAlchemySyncConfig, base


    class User(base.BigIntBase):
        __tablename__ = "flask_user_account"

        name: Mapped[str]


    app = Flask(__name__)
    alchemy = AdvancedAlchemy(
        SQLAlchemySyncConfig(
            connection_string="sqlite:///:memory:",
            commit_mode="autocommit",
            create_all=True,
        ),
        app,
    )


    @app.route("/users")
    def list_users() -> dict[str, list[dict[str, object]]]:
        session = alchemy.get_sync_session()
        users = session.execute(select(User)).scalars().all()
        return {"users": [{"id": user.id, "name": user.name} for user in users]}

Sessions are cached on Flask's application context, so repeated ``get_session()`` calls within the same request reuse the same SQLAlchemy session.

Multiple Databases
------------------

Provide a sequence of configurations when you need more than one bind key:

.. code-block:: python

    multi_app = Flask("flask_multi_db")
    multi_alchemy = AdvancedAlchemy(
        [
            SQLAlchemySyncConfig(connection_string="sqlite:///:memory:", bind_key="users"),
            SQLAlchemySyncConfig(connection_string="sqlite:///:memory:", bind_key="products"),
        ],
        multi_app,
    )

    with multi_app.app_context():
        users_session = multi_alchemy.get_sync_session("users")
        products_session = multi_alchemy.get_sync_session("products")

Async Support and Portal Execution
----------------------------------

Flask routes can also use asynchronous SQLAlchemy sessions or execute async coroutines from synchronous routes through the extension portal:

.. code-block:: python

    from advanced_alchemy.extensions.flask import SQLAlchemyAsyncConfig

    async_app = Flask("flask_async_db")
    async_alchemy = AdvancedAlchemy(
        SQLAlchemyAsyncConfig(
            connection_string="sqlite+aiosqlite:///:memory:",
            create_all=True,
        ),
        async_app,
    )


    @async_app.route("/users")
    async def list_users_async() -> dict[str, list[dict[str, object]]]:
        session = async_alchemy.get_async_session()
        users = (await session.execute(select(User))).scalars().all()
        return {"users": [{"id": user.id, "name": user.name} for user in users]}


    @async_app.route("/users/sync-bridge")
    def list_users_via_portal() -> dict[str, list[dict[str, object]]]:
        session = async_alchemy.get_async_session()
        users = async_alchemy.portal.call(session.execute, select(User)).scalars().all()
        return {"users": [{"id": user.id, "name": user.name} for user in users]}

Service Integration
-------------------

:class:`~advanced_alchemy.extensions.flask.FlaskServiceMixin` adds a ``jsonify()`` helper that serializes service results into a Flask ``Response``:

.. code-block:: python

    import datetime
    from typing import Optional
    from uuid import UUID

    from flask import Response, request
    from msgspec import Struct
    from sqlalchemy.orm import Mapped

    from advanced_alchemy.extensions.flask import (
        FlaskServiceMixin,
        filters,
        repository,
        service,
    )


    class Author(base.UUIDBase):
        __tablename__ = "flask_author"

        name: Mapped[str]
        dob: Mapped[Optional[datetime.date]]


    class AuthorSchema(Struct):
        name: str
        id: Optional[UUID] = None
        dob: Optional[datetime.date] = None


    class AuthorRepository(repository.SQLAlchemySyncRepository[Author]):
        model_type = Author


    class AuthorService(
        service.SQLAlchemySyncRepositoryService[Author, AuthorRepository],
        FlaskServiceMixin,
    ):
        repository_type = AuthorRepository


    service_app = Flask("flask_service_db")
    service_alchemy = AdvancedAlchemy(
        SQLAlchemySyncConfig(connection_string="sqlite:///:memory:", commit_mode="autocommit"),
        service_app,
    )


    @service_app.route("/authors", methods=["GET"])
    def list_authors() -> Response:
        current_page = request.args.get("currentPage", 1, type=int)
        page_size = request.args.get("pageSize", 10, type=int)
        limit_offset = filters.LimitOffset(limit=page_size, offset=page_size * (current_page - 1))

        author_service = AuthorService(session=service_alchemy.get_sync_session())
        results, total = author_service.get_many_and_count(limit_offset)
        payload = author_service.to_schema(
            results,
            total,
            filters=[limit_offset],
            schema_type=AuthorSchema,
        )
        return author_service.jsonify(payload)

Database Migrations
-------------------

When the Flask extension is initialized, database migration commands are registered on the Flask CLI:

.. code-block:: bash

    flask database init
    flask database revision --autogenerate -m "add users table"
    flask database upgrade
    flask database downgrade
    flask database history
