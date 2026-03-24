=================
Flask Integration
=================

Advanced Alchemy integrates with Flask through an extension that manages application-context sessions,
supports sync and async SQLAlchemy configs, and registers database migration commands on the Flask CLI.

Basic Setup
-----------

Use ``SQLAlchemySyncConfig`` for standard Flask applications:

.. code-block:: python

    from flask import Flask
    from sqlalchemy import select
    from sqlalchemy.orm import Mapped, mapped_column

    from advanced_alchemy.extensions.flask import AdvancedAlchemy, SQLAlchemySyncConfig, base


    class User(base.BigIntBase):
        __tablename__ = "flask_user_account"

        name: Mapped[str]


    app = Flask(__name__)
    alchemy = AdvancedAlchemy(
        SQLAlchemySyncConfig(
            connection_string="sqlite:///local.db",
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

Sessions are cached on Flask's application context, so repeated ``get_session()`` calls within the same request
reuse the same SQLAlchemy session.

Multiple Databases
------------------

Provide a sequence of configs when you need more than one bind key:

.. code-block:: python

    configs = [
        SQLAlchemySyncConfig(connection_string="sqlite:///users.db", bind_key="users"),
        SQLAlchemySyncConfig(connection_string="sqlite:///products.db", bind_key="products"),
    ]

    alchemy = AdvancedAlchemy(configs, app)

    users_session = alchemy.get_sync_session("users")
    products_session = alchemy.get_sync_session("products")

If you register multiple configs, call ``get_session()`` or ``get_sync_session()`` with an explicit bind key unless
you also have a ``default`` bind configured.

Async Support
-------------

Flask can also work with async SQLAlchemy sessions:

.. code-block:: python

    from advanced_alchemy.extensions.flask import SQLAlchemyAsyncConfig

    alchemy = AdvancedAlchemy(
        SQLAlchemyAsyncConfig(
            connection_string="sqlite+aiosqlite:///local.db",
            create_all=True,
        ),
        app,
    )


    @app.route("/users")
    async def list_users_async() -> dict[str, list[dict[str, object]]]:
        session = alchemy.get_async_session()
        users = (await session.execute(select(User))).scalars().all()
        return {"users": [{"id": user.id, "name": user.name} for user in users]}

For sync routes that need to call an async session explicitly, use the extension portal:

.. code-block:: python

    @app.route("/users/sync-bridge")
    def list_users_via_portal() -> dict[str, list[dict[str, object]]]:
        session = alchemy.get_async_session()
        users = alchemy.portal.call(session.execute, select(User)).scalars().all()
        return {"users": [{"id": user.id, "name": user.name} for user in users]}

Service Integration
-------------------

``FlaskServiceMixin`` adds a ``jsonify()`` helper that serializes service results using Advanced Alchemy's configured serializer:

.. code-block:: python

    import datetime
    from typing import Optional
    from uuid import UUID

    from flask import request
    from msgspec import Struct
    from sqlalchemy.orm import Mapped, mapped_column

    from advanced_alchemy.extensions.flask import (
        FlaskServiceMixin,
        SQLAlchemySyncConfig,
        AdvancedAlchemy,
        base,
        filters,
        repository,
        service,
    )


    class Author(base.UUIDBase):
        __tablename__ = "flask_author"

        name: Mapped[str]
        dob: Mapped[Optional[datetime.date]]


    class AuthorSchema(Struct):
        id: Optional[UUID] = None
        name: str
        dob: Optional[datetime.date] = None


    class AuthorService(service.SQLAlchemySyncRepositoryService[Author], FlaskServiceMixin):
        class Repo(repository.SQLAlchemySyncRepository[Author]):
            model_type = Author

        repository_type = Repo


    alchemy = AdvancedAlchemy(
        SQLAlchemySyncConfig(connection_string="sqlite:///local.db", commit_mode="autocommit"),
        app,
    )


    @app.route("/authors", methods=["GET"])
    def list_authors():
        current_page = request.args.get("currentPage", 1, type=int)
        page_size = request.args.get("pageSize", 10, type=int)
        limit_offset = filters.LimitOffset(limit=page_size, offset=page_size * (current_page - 1))

        author_service = AuthorService(session=alchemy.get_sync_session())
        results, total = author_service.list_and_count(limit_offset)
        payload = author_service.to_schema(
            results,
            total,
            filters=[limit_offset],
            schema_type=AuthorSchema,
        )
        return author_service.jsonify(payload)


    @app.route("/authors", methods=["POST"])
    def create_author():
        author_service = AuthorService(session=alchemy.get_sync_session())
        author = author_service.create(data=request.get_json())
        return author_service.jsonify(author_service.to_schema(author, schema_type=AuthorSchema))

Database Migrations
-------------------

When the Flask extension is initialized, database commands are added to the Flask CLI:

.. code-block:: bash

    flask database init
    flask database revision --autogenerate -m "add users table"
    flask database upgrade
    flask database downgrade
    flask database history
