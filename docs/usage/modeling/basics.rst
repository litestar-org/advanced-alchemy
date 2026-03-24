===============
Modeling Basics
===============

Advanced Alchemy enhances SQLAlchemy's modeling capabilities with production-ready base classes, mixins, and specialized types.
This guide demonstrates modeling for a blog system with posts and tags, showcasing key features and best practices.

Base Classes
------------

Advanced Alchemy provides several base classes optimized for different use cases. Any model can utilize these pre-defined declarative bases. Here's an overview of the included classes:

.. list-table:: Base Classes and Features
   :header-rows: 1
   :widths: 20 80

   * - Base Class
     - Features
   * - ``BigIntBase``
     - BIGINT primary keys for tables
   * - ``BigIntAuditBase``
     - BIGINT primary keys for tables, Automatic created_at/updated_at timestamps
   * - ``IdentityBase``
     - Primary keys using database IDENTITY feature instead of sequences
   * - ``IdentityAuditBase``
     - Primary keys using database IDENTITY feature, Automatic created_at/updated_at timestamps
   * - ``UUIDBase``
     - UUID primary keys
   * - ``UUIDv6Base``
     - UUIDv6 primary keys
   * - ``UUIDv7Base``
     - UUIDv7 primary keys
   * - ``UUIDAuditBase``
     - UUID primary keys, Automatic created_at/updated_at timestamps
   * - ``UUIDv6AuditBase``
     - UUIDv6 primary keys, Automatic created_at/updated_at timestamps
   * - ``UUIDv7AuditBase``
     - Time-sortable UUIDv7 primary keys, Automatic created_at/updated_at timestamps
   * - ``NanoIDBase``
     - URL-friendly unique identifiers, Shorter than UUIDs, collision resistant
   * - ``NanoIDAuditBase``
     - URL-friendly IDs with audit timestamps, Combines Nanoid benefits with audit trails

Mixins
-------

Additionally, Advanced Alchemy provides mixins to enhance model functionality:

.. list-table:: Available Mixins
   :header-rows: 1
   :widths: 20 80

   * - Mixin
     - Features
   * - ``SlugKey``
     - Adds URL-friendly slug field
   * - ``AuditColumns``
     - Automatic created_at/updated_at timestamps. Tracks record modifications.
   * - ``BigIntPrimaryKey``
     - Adds BigInt primary key with sequence
   * - ``IdentityPrimaryKey``
     - Adds primary key using database IDENTITY feature
   * - ``UniqueMixin``
     - Automatic Select or Create for many-to-many relationships


Basic Model Example
-------------------

Let's start with a simple blog post model:

.. code-block:: python

    import datetime
    from typing import Optional

    from advanced_alchemy.base import BigIntAuditBase
    from sqlalchemy.orm import Mapped, mapped_column

    class Post(BigIntAuditBase):
        """Blog post model with auto-incrementing ID and audit fields."""

        title: Mapped[str] = mapped_column(index=True)
        content: Mapped[str]
        published: Mapped[bool] = mapped_column(default=False)
        published_at: Mapped[Optional[datetime.datetime]] = mapped_column(default=None)

.. _many_to_many_relationships:

Many-to-Many Relationships
--------------------------

Let's implement a tagging system using a many-to-many relationship.

.. code-block:: python

    from sqlalchemy import Column, ForeignKey, Table
    from sqlalchemy.orm import Mapped, mapped_column, relationship
    from advanced_alchemy.base import BigIntAuditBase, orm_registry
    from advanced_alchemy.mixins import SlugKey
    from typing import List

    # Association table for post-tag relationship
    post_tag = Table(
        "post_tag",
        orm_registry.metadata,
        Column("post_id", ForeignKey("post.id", ondelete="CASCADE"), primary_key=True),
        Column("tag_id", ForeignKey("tag.id", ondelete="CASCADE"), primary_key=True)
    )

    class Post(BigIntAuditBase):
        title: Mapped[str] = mapped_column(index=True)
        content: Mapped[str]
        published: Mapped[bool] = mapped_column(default=False)

        # Many-to-many relationship with tags
        tags: Mapped[List["Tag"]] = relationship(
            secondary=post_tag,
            back_populates="posts",
            lazy="selectin"
        )

    class Tag(BigIntAuditBase, SlugKey):
        """Tag model with automatic slug generation."""
        name: Mapped[str] = mapped_column(unique=True, index=True)
        posts: Mapped[List["Post"]] = relationship(
            secondary=post_tag,
            back_populates="tags",
            viewonly=True
        )

.. _using_unique_mixin:

Using ``UniqueMixin``
---------------------

``UniqueMixin`` provides automatic handling of unique constraints and merging of duplicate records.

.. code-block:: python

    from advanced_alchemy.base import BigIntAuditBase
    from advanced_alchemy.mixins import SlugKey, UniqueMixin
    from advanced_alchemy.utils.text import slugify
    from sqlalchemy.sql.elements import ColumnElement
    from sqlalchemy.orm import Mapped, mapped_column, relationship
    from typing import Hashable, Optional

    class Tag(BigIntAuditBase, SlugKey, UniqueMixin):
        """Tag model with unique name constraint."""

        name: Mapped[str] = mapped_column(unique=True, index=True)
        posts: Mapped[list["Post"]] = relationship(
            secondary=post_tag,
            back_populates="tags",
            viewonly=True
        )

        @classmethod
        def unique_hash(cls, name: str, slug: Optional[str] = None) -> Hashable:
            """Generate a unique hash for deduplication."""
            return slugify(name)

        @classmethod
        def unique_filter(
            cls,
            name: str,
            slug: Optional[str] = None,
        ) -> ColumnElement[bool]:
            """SQL filter for finding existing records."""
            return cls.slug == slugify(name)

We can now use ``as_unique_async`` to simplify creation:

.. code-block:: python

    from sqlalchemy.ext.asyncio import AsyncSession
    from advanced_alchemy.utils.text import slugify

    async def add_tags_to_post(
        db_session: AsyncSession,
        post: Post,
        tag_names: list[str]
    ) -> Post:
        """Add tags to a post, creating new tags if needed."""
        post.tags = [
          await Tag.as_unique_async(db_session, name=tag_text, slug=slugify(tag_text))
          for tag_text in tag_names
        ]
        await db_session.merge(post)
        await db_session.flush()
        return post

Customizing Declarative Base
-----------------------------

Advanced Alchemy supports customizing the ``DeclarativeBase`` class.

.. code-block:: python

    import datetime
    from typing import Optional
    from uuid import UUID, uuid4

    from advanced_alchemy.base import CommonTableAttributes, orm_registry
    from sqlalchemy import text
    from sqlalchemy.orm import (
        DeclarativeBase,
        Mapped,
        declared_attr,
        mapped_column,
        orm_insert_sentinel,
    )

    class ServerSideUUIDPrimaryKey:
        """UUID Primary Key Field Mixin."""
        id: Mapped[UUID] = mapped_column(
            default=uuid4,
            primary_key=True,
            server_default=text("gen_random_uuid()"),
        )

        @declared_attr
        def _sentinel(cls) -> Mapped[int]:
            """Sentinel value required for bulk DML."""
            return orm_insert_sentinel(name="sa_orm_sentinel")

    class ServerSideUUIDBase(ServerSideUUIDPrimaryKey, CommonTableAttributes, DeclarativeBase):
        registry = orm_registry

    class User(ServerSideUUIDBase):
        username: Mapped[str] = mapped_column(unique=True, index=True)
        email: Mapped[str] = mapped_column(unique=True)
        full_name: Mapped[str]
        is_active: Mapped[bool] = mapped_column(default=True)
        last_login: Mapped[Optional[datetime.datetime]] = mapped_column(default=None)
