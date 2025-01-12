from __future__ import annotations

import os
from datetime import date  # noqa: TC003
from uuid import UUID  # noqa: TC003

from flask import Flask, request
from pydantic import BaseModel as PydanticBaseModel
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from advanced_alchemy.base import UUIDAuditBase, UUIDBase
from advanced_alchemy.extensions.flask import AdvancedAlchemy, SQLAlchemySyncConfig, SQLAlchemySyncRepositoryService
from advanced_alchemy.filters import LimitOffset
from advanced_alchemy.repository import SQLAlchemySyncRepository


class BaseModel(PydanticBaseModel):
    """Base model for all schemas."""

    model_config = {"from_attributes": True}


class AuthorModel(UUIDBase):
    """Author model."""

    __tablename__ = "author"

    name: Mapped[str]
    dob: Mapped[date | None]
    books: Mapped[list[BookModel]] = relationship(back_populates="author", lazy="noload")


class BookModel(UUIDAuditBase):
    """Book model."""

    __tablename__ = "book"

    title: Mapped[str]
    author_id: Mapped[UUID] = mapped_column(ForeignKey("author.id"))
    author: Mapped[AuthorModel] = relationship(lazy="joined", innerjoin=True, viewonly=True)


class Author(BaseModel):
    """Author schema."""

    id: UUID | None = None
    name: str
    dob: date | None = None


class AuthorRepository(SQLAlchemySyncRepository[AuthorModel]):
    """Author repository."""

    model_type = AuthorModel


class AuthorService(SQLAlchemySyncRepositoryService[AuthorModel]):
    """Author service."""

    repository_type = AuthorRepository


app = Flask(__name__)
config = SQLAlchemySyncConfig(connection_string="sqlite:///:memory:")
alchemy = AdvancedAlchemy(config, app)


@app.route("/authors", methods=["GET"])
def list_authors():
    """List authors with pagination."""
    page = request.args.get("currentPage", 1, type=int)
    page_size = request.args.get("pageSize", 10, type=int)
    limit_offset = LimitOffset(limit=page_size, offset=page_size * (page - 1))

    with alchemy.session() as session, AuthorService.new(session=session) as service:
        results, total = service.list_and_count(limit_offset)
        response = service.to_schema(results, total, filters=[limit_offset], schema_type=Author)
        return service.jsonify(response)


@app.route("/authors", methods=["POST"])
def create_author():
    """Create a new author."""
    with alchemy.session() as session, AuthorService.new(session=session) as service:
        obj = service.create(**request.get_json())
        return service.jsonify(obj)


@app.route("/authors/<uuid:author_id>", methods=["GET"])
def get_author(author_id: UUID):
    """Get an existing author."""
    with alchemy.session() as session, AuthorService.new(session=session, load=[AuthorModel.books]) as service:
        obj = service.get(author_id)
        return service.jsonify(obj)


@app.route("/authors/<uuid:author_id>", methods=["PATCH"])
def update_author(author_id: UUID):
    """Update an author."""
    with alchemy.session() as session, AuthorService.new(session=session, load=[AuthorModel.books]) as service:
        obj = service.update(**request.get_json(), item_id=author_id)
        return service.jsonify(obj)


@app.route("/authors/<uuid:author_id>", methods=["DELETE"])
def delete_author(author_id: UUID):
    """Delete an author."""
    with alchemy.session() as session, AuthorService.new(session=session) as service:
        service.delete(author_id)
        return "", 204


if __name__ == "__main__":
    app.run(debug=os.environ["ENV"] == "dev")
