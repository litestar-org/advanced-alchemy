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

    from advanced_alchemy.base import BigIntAuditBase, UUIDAuditBase
    from sqlalchemy.orm import Mapped, mapped_column
    from datetime import datetime
    from typing import Optional

    class User(UUIDAuditBase):
        """User model with UUID primary key and audit fields.

        This model automatically includes:
        - UUID primary key
        - created_at timestamp
        - updated_at timestamp
        """

        __tablename__ = "user"

        name: Mapped[str] = mapped_column(unique=True)
        email: Mapped[str] = mapped_column(unique=True)
        last_login: Mapped[Optional[datetime]] = mapped_column(default=None)

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

    from sqlalchemy import ForeignKey
    from sqlalchemy.orm import relationship
    from typing import List

    class Post(BigIntAuditBase):
        __tablename__ = "post"

        title: Mapped[str]
        content: Mapped[str]
        published: Mapped[bool] = mapped_column(default=False)
        author_id: Mapped[UUID] = mapped_column(ForeignKey("user.id"))

        # Relationships
        author: Mapped["User"] = relationship(back_populates="posts")
        tags: Mapped[List["Tag"]] = relationship(
            secondary="post_tags",
            back_populates="posts"
        )

    class Tag(BigIntAuditBase):
        __tablename__ = "tag"

        name: Mapped[str] = mapped_column(unique=True)
        posts: Mapped[List["Post"]] = relationship(
            secondary="post_tags",
            back_populates="tags"
        )

    # Association table for many-to-many relationship
    class PostTag(BigIntAuditBase):
        __tablename__ = "post_tags"

        post_id: Mapped[int] = mapped_column(ForeignKey("post.id"), primary_key=True)
        tag_id: Mapped[int] = mapped_column(ForeignKey("tag.id"), primary_key=True)
