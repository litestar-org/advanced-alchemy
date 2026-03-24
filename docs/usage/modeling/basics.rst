===============
Modeling Basics
===============

Advanced Alchemy enhances SQLAlchemy's modeling capabilities with production-ready base classes, mixins, and specialized types.
This guide demonstrates modeling for a blog system with posts and tags, showcasing key features and best practices.

Base Classes
------------

Advanced Alchemy provides several declarative bases optimized for different use cases. The common
ID and audit combinations are ready to use, while the lower-level bases let you assemble your own
model hierarchy without rebuilding SQLAlchemy's declarative setup from scratch.

.. list-table:: Base Classes and Features
   :header-rows: 1
   :widths: 20 80

   * - Base Class
     - Features
   * - ``AdvancedDeclarativeBase``
     - Low-level registry-aware base for building custom declarative hierarchies
   * - ``DefaultBase``
     - Automatic table naming and bind-aware metadata without a predefined primary key
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
   * - ``SQLQuery``
     - Registry-backed base for custom mapped query objects and other specialized mapped constructs

For most applications, start with one of the opinionated bases such as ``BigIntAuditBase`` or
``UUIDAuditBase``. Reach for ``DefaultBase`` when you want Advanced Alchemy's table naming and
metadata handling but need to define your own primary key fields.

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

    class BasicBlogPost(BigIntAuditBase):
        """Blog post model with auto-incrementing ID and audit fields."""

        __tablename__ = "basic_blog_post"

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

    # Association table for post-topic relationships
    blog_post_topic = Table(
        "blog_post_topic",
        orm_registry.metadata,
        Column("post_id", ForeignKey("tagged_blog_post.id", ondelete="CASCADE"), primary_key=True),
        Column("topic_id", ForeignKey("blog_topic.id", ondelete="CASCADE"), primary_key=True),
    )

    class TaggedBlogPost(BigIntAuditBase):
        __tablename__ = "tagged_blog_post"

        title: Mapped[str] = mapped_column(index=True)
        content: Mapped[str]
        published: Mapped[bool] = mapped_column(default=False)

        # Many-to-many relationship with topics
        topics: Mapped[List["BlogTopic"]] = relationship(
            secondary=blog_post_topic,
            back_populates="posts",
            lazy="selectin",
        )

    class BlogTopic(BigIntAuditBase, SlugKey):
        """Topic model with automatic slug generation."""

        __tablename__ = "blog_topic"

        name: Mapped[str] = mapped_column(unique=True, index=True)
        posts: Mapped[List["TaggedBlogPost"]] = relationship(
            secondary=blog_post_topic,
            back_populates="topics",
            lazy="selectin",
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

    class UniqueTopic(BigIntAuditBase, SlugKey, UniqueMixin):
        """Topic model with unique name constraint."""

        __tablename__ = "unique_topic"

        name: Mapped[str] = mapped_column(unique=True, index=True)

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

    async def get_or_create_topics(
        db_session: AsyncSession,
        topic_names: list[str],
    ) -> list[UniqueTopic]:
        """Create or fetch topic rows without duplicating existing slugs."""
        return [
            await UniqueTopic.as_unique_async(db_session, name=topic_name, slug=slugify(topic_name))
            for topic_name in topic_names
        ]

Using ``MappedAsDataclass``
---------------------------

Advanced Alchemy's built-in bases can also be combined with SQLAlchemy's
``MappedAsDataclass`` helper. ``DefaultBase`` is the best starting point when you want
dataclass-style construction but need to define your own primary key fields.

.. code-block:: python

    from typing import Optional

    from advanced_alchemy.base import DefaultBase
    from sqlalchemy.orm import Mapped, MappedAsDataclass, mapped_column

    class DataclassAuthor(MappedAsDataclass, DefaultBase):
        __tablename__ = "dataclass_author"

        id: Mapped[int] = mapped_column(primary_key=True, init=False)
        name: Mapped[str]
        bio: Mapped[Optional[str]] = mapped_column(default=None)

If a field is generated by the database or SQLAlchemy itself, mark it ``init=False`` or provide a
default so the generated dataclass constructor remains valid.

Customizing Declarative Base
-----------------------------

If the built-in primary key strategies are close but not exact, start from ``DefaultBase`` and add
your own columns or mixins. That keeps the Advanced Alchemy registry and table-name behavior while
letting you replace the primary key strategy.

.. code-block:: python

    import datetime
    from typing import Optional
    from uuid import UUID, uuid4

    from advanced_alchemy.base import DefaultBase
    from sqlalchemy import text
    from sqlalchemy.orm import (
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

    class ServerSideUUIDBase(ServerSideUUIDPrimaryKey, DefaultBase):
        __abstract__ = True

    class ServerSideUser(ServerSideUUIDBase):
        __tablename__ = "server_side_user"

        username: Mapped[str] = mapped_column(unique=True, index=True)
        email: Mapped[str] = mapped_column(unique=True)
        full_name: Mapped[str]
        is_active: Mapped[bool] = mapped_column(default=True)
        last_login: Mapped[Optional[datetime.datetime]] = mapped_column(default=None)
