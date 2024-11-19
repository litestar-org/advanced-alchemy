========
Modeling
========

Advanced Alchemy enhances SQLAlchemy's modeling capabilities with production-ready base classes, mixins, and specialized types.
This guide will walk you through building a complete domain model for a blog application.

Base Models
-----------

The foundation of any Advanced Alchemy application starts with choosing the right base class. The library provides several
options, each optimized for different use cases:

.. code-block:: python

    from advanced_alchemy.base import BigIntAuditBase
    from sqlalchemy.orm import Mapped, mapped_column
    from datetime import datetime

    class Post(BigIntAuditBase):
        """Blog post model with auto-incrementing ID.

        Uses a BIGINT primary key for an integer based ID.
        """

        __tablename__ = "post"

        title: Mapped[str]
        content: Mapped[str]
        published: Mapped[bool] = mapped_column(default=False)

Relationships and Foreign Keys
------------------------------

Let's expand our blog models to include relationships:

.. code-block:: python
    from __future__ import annotations

    from sqlalchemy import Column, DateTime, ForeignKey, Table, func
    from sqlalchemy.orm import relationship
    from advanced_alchemy.base import orm_registry
    from typing import List


    post_tag = Table(
        "post_tag",
        orm_registry.metadata,
        Column("post_id", ForeignKey("post.id", ondelete="CASCADE"), primary_key=True),
        Column("tag_id", ForeignKey("tag.id", ondelete="CASCADE"), primary_key=True)
    )

    class Post(BigIntAuditBase):
        __tablename__ = "post"

        title: Mapped[str]
        content: Mapped[str]
        published: Mapped[bool] = mapped_column(default=False)
        author: Mapped[str]

        # Relationships
        tags: Mapped[List["Tag"]] = relationship(
            secondary=post_tag,
            back_populates="posts"
        )

    class Tag(BigIntAuditBase):
        __tablename__ = "tag"

        name: Mapped[str] = mapped_column(unique=True)
        posts: Mapped[List["Post"]] = relationship(
            secondary=post_tag
            back_populates="tags"
        )

TODO: Summarize the models, the relationship cardinality, and other core details.

TODO: Show how to execute a insert/update/delete for tags in this many to many.


Simply with the UniqueMixin
-------------------

While this models our relationships perfectly, we can make things even easier to access.  We are going to use a few SQLAlchemy operators and a special advanced Alchemy mixin for Many-to-many relationships.

.. code-block:: python

    from __future__ import annotations

    from sqlalchemy import Column, DateTime, ForeignKey, Table
    from sqlalchemy.orm import relationship
    from advanced_alchemy.base import orm_registry, SlugKey, UUIDv7AuditBase, BigIntAuditBase
    from advanced_alchemy.mixins import UniqueMixin
    from advanced_alchemy.utils.text import slugify


    post_tag = Table(
        "post_tag",
        orm_registry.metadata,
        Column("post_id", ForeignKey("post.id", ondelete="CASCADE"), primary_key=True),
        Column("tag_id", ForeignKey("tag.id", ondelete="CASCADE"), primary_key=True)
    )

    class Post(BigIntAuditBase):
        __tablename__ = "post"

        title: Mapped[str]
        content: Mapped[str]
        published: Mapped[bool] = mapped_column(default=False)
        author: Mapped[str]

        # Relationships
        tags: Mapped[list[Tag]] = relationship(
            secondary=post_tag,
            back_populates="posts"
        )

    class Tag(UUIDv7AuditBase, SlugKey, UniqueMixin):
        __tablename__ = "tag"

        name: Mapped[str] = mapped_column(unique=True)
        posts: Mapped[list[Post]] = relationship(
            secondary=post_tag
            back_populates="tags"
        )

        @classmethod
        def unique_hash(cls, name: str, slug: str | None = None) -> Hashable:
            """Return a unique hashsable object that represents the row."""
            return slugify(name)

        @classmethod
        def unique_filter(
            cls,
            name: str,
            slug: str | None = None,
        ) -> ColumnElement[bool]:
            return cls.slug == slugify(name)


TODO: Show how the UniqueMixin enables you to automatically look up existing records and merge into the SQLA session

With this foundation in place, let's look at the repository pattern.
