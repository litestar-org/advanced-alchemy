from __future__ import annotations

import datetime  # noqa: TC003
import os
from uuid import UUID  # noqa: TC003

from flask import Flask, request
from msgspec import Struct
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from advanced_alchemy.extensions.flask import (
    AdvancedAlchemy,
    FlaskServiceMixin,
    SQLAlchemySyncConfig,
    base,
    filters,
    repository,
    service,
)


class Author(base.UUIDBase):
    """Author model."""

    name: Mapped[str]
    dob: Mapped[datetime.date | None]
    books: Mapped[list[Book]] = relationship(back_populates="author", lazy="noload")


class Book(base.UUIDAuditBase):
    """Book model."""

    title: Mapped[str]
    author_id: Mapped[UUID] = mapped_column(ForeignKey("author.id"))
    author: Mapped[Author] = relationship(lazy="joined", innerjoin=True, viewonly=True)


class AuthorService(service.SQLAlchemySyncRepositoryService[Author], FlaskServiceMixin):
    """Author service."""

    class Repo(repository.SQLAlchemySyncRepository[Author]):
        """Author repository."""

        model_type = Author

    repository_type = Repo


class AuthorSchema(Struct):
    """Author schema."""

    name: str
    id: UUID | None = None
    dob: datetime.date | None = None


app = Flask(__name__)
config = SQLAlchemySyncConfig(connection_string="sqlite:///local.db", commit_mode="autocommit", create_all=True)
alchemy = AdvancedAlchemy(config, app)


@app.route("/authors", methods=["GET"])
def list_authors():
    """List authors with pagination."""
    page, page_size = request.args.get("currentPage", 1, type=int), request.args.get("pageSize", 10, type=int)
    limit_offset = filters.LimitOffset(limit=page_size, offset=page_size * (page - 1))
    service = AuthorService(session=alchemy.get_sync_session())
    results, total = service.list_and_count(limit_offset)
    response = service.to_schema(results, total, filters=[limit_offset], schema_type=AuthorSchema)
    return service.jsonify(response)


@app.route("/authors", methods=["POST"])
def create_author():
    """Create a new author."""
    service = AuthorService(session=alchemy.get_sync_session())
    obj = service.create(**request.get_json())
    return service.jsonify(obj)


@app.route("/authors/<uuid:author_id>", methods=["GET"])
def get_author(author_id: UUID):
    """Get an existing author."""
    service = AuthorService(session=alchemy.get_sync_session(), load=[Author.books])
    obj = service.get(author_id)
    return service.jsonify(obj)


@app.route("/authors/<uuid:author_id>", methods=["PATCH"])
def update_author(author_id: UUID):
    """Update an author."""
    service = AuthorService(session=alchemy.get_sync_session(), load=[Author.books])
    obj = service.update(**request.get_json(), item_id=author_id)
    return service.jsonify(obj)


@app.route("/authors/<uuid:author_id>", methods=["DELETE"])
def delete_author(author_id: UUID):
    """Delete an author."""
    service = AuthorService(session=alchemy.get_sync_session())
    service.delete(author_id)
    return "", 204


if __name__ == "__main__":
    app.run(debug=os.environ["ENV"] == "dev")
