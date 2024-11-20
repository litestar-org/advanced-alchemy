========
Modeling
========

Advanced Alchemy enhances SQLAlchemy's modeling capabilities with production-ready base classes, mixins, and specialized types.
This guide demonstrates building a complete domain model for a blog application, showcasing key features and best practices.

Base Classes
------------

Advanced Alchemy provides several base classes optimized for different use cases:

.. list-table:: Base Classes and Features
   :header-rows: 1
   :widths: 20 80

   * - Base Class
     - Features
   * - ``BigIntBase``
     - | - BIGINT primary keys for tables
   * - ``BigIntAuditBase``
     - | - BIGINT primary keys for tables
       | - Automatic created_at/updated_at timestamps
   * - ``UUIDBase``
     - | - UUID primary keys
   * - ``UUIDv6Base``
     - | - Time-sortable UUIDv6 primary keys
   * - ``UUIDv7Base``
     - | - Time-sortable UUIDv7 primary keys
   * - ``UUIDAuditBase``
     - | - UUID primary keys
       | - Automatic created_at/updated_at timestamps
   * - ``UUIDv6AuditBase``
     - | - Time-sortable UUIDv6 primary keys
       | - Automatic created_at/updated_at timestamps
   * - ``UUIDv7AuditBase``
     - | - Time-sortable UUIDv7 primary keys
       | - Automatic created_at/updated_at timestamps
   * - ``NanoidBase``
     - | - Nanoid primary keys
   * - ``NanoidAuditBase``
     - | - Nanoid primary keys
       | - Automatic created_at/updated_at timestamps
   * - ``SlugKey``
     - | - Adds URL-friendly slug field
   * - ``UniqueMixin``
     - | - Automatic unique constraint handling
       | - Duplicate record merging

Basic Model Example
-------------------

Let's start with a simple blog post model:

.. code-block:: python

    from advanced_alchemy.base import BigIntAuditBase
    from sqlalchemy.orm import Mapped, mapped_column
    from datetime import datetime
    from typing import Optional

    class Post(BigIntAuditBase):
        """Blog post model with auto-incrementing ID and audit fields.

        Attributes:
            title: The post title
            content: The post content
            published: Publication status
            created_at: Timestamp of creation (from BigIntAuditBase)
            updated_at: Timestamp of last update (from BigIntAuditBase)
        """
        __tablename__ = "post"

        title: Mapped[str] = mapped_column(index=True)
        content: Mapped[str]
        published: Mapped[bool] = mapped_column(default=False)
        published_at: Mapped[Optional[datetime]] = mapped_column(default=None)

Many-to-Many Relationships
--------------------------

Let's implement a tagging system using a many-to-many relationship. This example demonstrates:
- Association table configuration
- Relationship configuration with lazy loading
- Slug key mixin
- Index creation

.. code-block:: python

    from __future__ import annotations
    from sqlalchemy import Column, ForeignKey, Table
    from sqlalchemy.orm import relationship
    from sqlalchemy.orm import Mapped, mapped_column
    from advanced_alchemy.base import BigIntAuditBase, orm_registry, SlugKey
    from typing import List

    # Association table for post-tag relationship
    post_tag = Table(
        "post_tag",
        orm_registry.metadata,
        Column("post_id", ForeignKey("post.id", ondelete="CASCADE"), primary_key=True),
        Column("tag_id", ForeignKey("tag.id", ondelete="CASCADE"), primary_key=True)
    )

    class Post(BigIntAuditBase):
        __tablename__ = "post"

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
        """Tag model with automatic slug generation.

        The SlugKey mixin automatically adds a slug field to the model.
        """
        __tablename__ = "tag"

        name: Mapped[str] = mapped_column(unique=True, index=True)
        posts: Mapped[List[Post]] = relationship(
            secondary=post_tag,
            back_populates="tags",
            viewonly=True
        )

If we want to interact with the models above, we might use something like the following:


.. code-block:: python

    from sqlalchemy.ext.asyncio import AsyncSession

    async def add_tags_to_post(
        session: AsyncSession,
        post: Post,
        tag_names: list[str]
    ) -> Post:
        """Add tags to a post, looking up existing tags and creating new ones if needed."""
        existing_tags = await session.scalars(
            select(Tag).filter(Tag.slug.in_([slugify(name) for name in tag_names]))
        )
        new_tags = [Tag(name=name, slug=slugify(name)) for name in tag_names if name not in {tag.name for tag in existing_tags}]
        post.tags.extend(new_tags + list(existing_tags))
        return await session.add(post)


While not too difficult, there is definitely some additional logic required to handle the unique tags on this post.  Fortunately, we can remove some of this logic thanks to the ``UniqueMixin``.  Let's look at how we can do this.

Using the UniqueMixin
---------------------

The UniqueMixin provides automatic handling of unique constraints and merging of duplicate records. When using the mixin,
you must implement two classmethods: ``unique_hash`` and ``unique_filter``. These methods enable:

- Automatic lookup of existing records
- Safe merging of duplicates
- Atomic get-or-create operations
- Configurable uniqueness criteria

Let's enhance our Tag model with UniqueMixin:

.. code-block:: python

    from advanced_alchemy.base import BigIntAuditBase, SlugKey
    from advanced_alchemy.mixins import UniqueMixin
    from advanced_alchemy.utils.text import slugify
    from sqlalchemy.sql.elements import ColumnElement
    from typing import Hashable

    class Tag(BigIntAuditBase, SlugKey, UniqueMixin):
        """Tag model with unique name constraint and automatic slug generation.

        The UniqueMixin provides:
        - Automatic lookup of existing records
        - Safe merging of duplicates
        - Consistent slug generation
        """
        __tablename__ = "tag"

        name: Mapped[str] = mapped_column(unique=True, index=True)
        posts: Mapped[list[Post]] = relationship(
            secondary=post_tag,
            back_populates="tags",
            viewonly=True
        )

        @classmethod
        def unique_hash(cls, name: str, slug: str | None = None) -> Hashable:
            """Generate a unique hash for deduplication."""
            return slugify(name)

        @classmethod
        def unique_filter(
            cls,
            name: str,
            slug: str | None = None,
        ) -> ColumnElement[bool]:
            """SQL filter for finding existing records."""
            return cls.slug == slugify(name)

Using the Models
----------------

Here's how to use these models with the UniqueMixin:

.. code-block:: python

    from sqlalchemy.ext.asyncio import AsyncSession

    async def add_tags_to_post(
        session: AsyncSession,
        post: Post,
        tag_names: list[str]
    ) -> Post:
        """Add tags to a post, creating new tags if needed.

        The UniqueMixin automatically handles:
        1. Looking up existing tags
        2. Creating new tags if needed
        3. Merging duplicates
        """
        return await session.add(post.tags.extend(
                [
                await Tag.as_unique_async(session, name=tag_text, slug=slugify(tag_text))
                for tag_text in tag_names
            ],
        ))


With this foundation in place, let's look at the repository pattern.
