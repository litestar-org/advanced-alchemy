====================
Relationships
====================

SQLAlchemy relationships connect models together. Advanced Alchemy supports all SQLAlchemy 2.0 relationship patterns.

Prerequisites
=============

This section builds on :doc:`basics`. Ensure you understand base classes before working with relationships.

Understanding Relationships
===========================

SQLAlchemy relationships define how models connect:

- **One-to-Many**: One record relates to multiple records (User → Posts)
- **Many-to-One**: Multiple records relate to one record (Posts → User)
- **Many-to-Many**: Multiple records relate to multiple records (Posts ↔ Tags)

Relationships use foreign keys and association tables to connect data.

.. _many_to_many_relationships:

Many-to-Many Relationships
===========================

Many-to-many relationships require an association table. This example demonstrates a tagging system for blog posts:

.. code-block:: python

    from __future__ import annotations
    from sqlalchemy import Column, ForeignKey, Table
    from sqlalchemy.orm import relationship
    from sqlalchemy.orm import Mapped, mapped_column
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
        """Blog post model."""

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

        name: Mapped[str] = mapped_column(unique=True, index=True)
        posts: Mapped[List[Post]] = relationship(
            secondary=post_tag,
            back_populates="tags",
            viewonly=True
        )

This configuration creates:

- ``post_tag`` association table with foreign keys
- ``Post.tags`` relationship (owning side, can modify)
- ``Tag.posts`` relationship (viewonly, read-only)
- Cascade delete on both foreign keys

Working with Tags
-----------------

Manual Get-or-Create Pattern
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Without mixins, adding tags requires manual get-or-create logic:

.. code-block:: python

    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy import select
    from advanced_alchemy.utils.text import slugify

    async def add_tags_to_post(
        db_session: AsyncSession,
        post: Post,
        tag_names: list[str]
    ) -> Post:
        """Add tags to a post, looking up existing tags and creating new ones if needed."""
        existing_tags = await db_session.scalars(
            select(Tag).filter(Tag.slug.in_([slugify(name) for name in tag_names]))
        )
        new_tags = [Tag(name=name, slug=slugify(name)) for name in tag_names if name not in {tag.name for tag in existing_tags}]
        post.tags.extend(new_tags + list(existing_tags))
        db_session.merge(post)
        await db_session.flush()
        return post

This manual pattern:

- Queries existing tags by slug
- Creates new tags for missing names
- Adds tags to the post
- Flushes changes to database

Using UniqueMixin
~~~~~~~~~~~~~~~~~

The ``UniqueMixin`` simplifies get-or-create operations. The ``Tag`` model from the example above includes ``UniqueMixin`` - see :ref:`using_unique_mixin` for the complete implementation.

.. code-block:: python

    from advanced_alchemy.utils.text import slugify

    async def add_tags_to_post(
        db_session: AsyncSession,
        post: Post,
        tag_names: list[str]
    ) -> Post:
        """Add tags using UniqueMixin for automatic get-or-create."""
        # Identify tags to add (only new ones)
        existing_tag_names = [tag.name for tag in post.tags]
        tags_to_add = [name for name in tag_names if name not in existing_tag_names]

        # Extend with new tags using UniqueMixin
        post.tags.extend([
            await Tag.as_unique_async(
                db_session,
                name=tag_name,
                slug=slugify(tag_name)
            )
            for tag_name in tags_to_add
        ])
        await db_session.flush()
        return post

The ``UniqueMixin`` pattern:

- Automatically looks up existing tags by unique key (slug)
- Creates new tags only if needed
- Single method call per tag
- Handles uniqueness constraints safely

Implementation Patterns
=======================

Relationship Loading Strategies
--------------------------------

SQLAlchemy provides multiple loading strategies:

**selectinload - Separate Query**

.. code-block:: python

    from sqlalchemy.orm import selectinload

    posts: Mapped[List["Tag"]] = relationship(
        secondary=post_tag,
        back_populates="posts",
        lazy="selectin"
    )

Characteristics:

- Executes separate SELECT query for related items
- Loads all related items in one additional query
- Efficient for one-to-many relationships
- Default strategy for Advanced Alchemy examples

**joinedload - Single Query with JOIN**

.. code-block:: python

    from sqlalchemy.orm import joinedload

    # Use in query, not in relationship definition
    stmt = select(Post).options(joinedload(Post.tags))
    posts = await session.scalars(stmt)

Characteristics:

- Executes single query with LEFT OUTER JOIN
- Loads parent and related items together
- Can result in duplicate rows (SQLAlchemy handles deduplication)
- Efficient for many-to-one relationships

**lazy='select' - Lazy Loading**

.. code-block:: python

    posts: Mapped[List["Tag"]] = relationship(
        secondary=post_tag,
        back_populates="posts",
        lazy="select"
    )

Characteristics:

- Loads related items on first access
- Executes separate query per parent item
- Can cause N+1 query problems
- Requires active session when accessing relationship

Viewonly Relationships
----------------------

The ``viewonly=True`` parameter creates read-only relationships:

.. code-block:: python

    posts: Mapped[List[Post]] = relationship(
        secondary=post_tag,
        back_populates="tags",
        viewonly=True
    )

Characteristics:

- Cannot modify relationship (no append, remove)
- Prevents accidental modifications
- Used for the non-owning side of many-to-many relationships
- Reduces complexity of bidirectional relationships

.. _one_to_many_relationships:

One-to-Many Relationships
==========================

One-to-many relationships use foreign keys directly:

.. code-block:: python

    from sqlalchemy import ForeignKey
    from sqlalchemy.orm import Mapped, mapped_column, relationship
    from advanced_alchemy.base import BigIntAuditBase
    from typing import List, Optional

    class Author(BigIntAuditBase):
        """Author model."""

        name: Mapped[str] = mapped_column(index=True)
        email: Mapped[str] = mapped_column(unique=True)

        # One-to-many: one author has many posts
        posts: Mapped[List["Post"]] = relationship(
            back_populates="author",
            lazy="selectin"
        )

    class Post(BigIntAuditBase):
        """Blog post model with author relationship."""

        title: Mapped[str] = mapped_column(index=True)
        content: Mapped[str]

        # Many-to-one: many posts belong to one author
        author_id: Mapped[int] = mapped_column(ForeignKey("author.id"))
        author: Mapped["Author"] = relationship(back_populates="posts")

This configuration creates:

- Foreign key ``author_id`` in posts table
- ``Author.posts`` relationship (one-to-many)
- ``Post.author`` relationship (many-to-one)
- Bidirectional navigation between author and posts

Technical Constraints
=====================

N+1 Query Problem
-----------------

Lazy loading can cause performance issues:

.. code-block:: python

    # ❌ Incorrect - causes N+1 queries
    posts = await session.scalars(select(Post))
    for post in posts:
        print(post.author.name)  # Triggers separate query per post

    # ✅ Correct - eager loading prevents N+1 queries
    from sqlalchemy.orm import selectinload

    posts = await session.scalars(
        select(Post).options(selectinload(Post.author))
    )
    for post in posts:
        print(post.author.name)  # No additional queries

Use eager loading (``selectinload``, ``joinedload``) to avoid N+1 query problems.

Eager Loading in Dependency Injection
--------------------------------------

When using web frameworks, configure eager loading at the dependency provider level:

.. code-block:: python

    from advanced_alchemy.extensions.litestar.providers import create_service_provider
    from sqlalchemy.orm import selectinload, joinedload, load_only

    # Configure loading strategies at DI level
    provide_team_service = create_service_provider(
        TeamService,
        load=[
            # Load team members with nested user details
            selectinload(Team.members).options(
                joinedload(TeamMember.user, innerjoin=True),
            ),
            # Load owner relationship
            selectinload(Team.owner),
            # Load tags with limited fields
            selectinload(Team.tags).options(
                load_only(Tag.name, Tag.slug),
            ),
        ],
    )

This pattern:

- Configures loading once at dependency setup
- Applies to all uses of the service
- Prevents N+1 queries automatically
- Supports nested loading strategies
- Works with framework dependency injection

Viewonly Modification Constraint
---------------------------------

Viewonly relationships cannot be modified:

.. code-block:: python

    # ✅ Correct - modify on owning side
    post.tags.append(tag)

    # ❌ Incorrect - cannot modify viewonly relationship
    tag.posts.append(post)  # Raises error or silently ignored

Always modify relationships on the owning side (without ``viewonly=True``).

Cascade Behavior
----------------

Foreign key cascade options control delete behavior:

.. code-block:: python

    # With CASCADE delete
    Column("post_id", ForeignKey("post.id", ondelete="CASCADE"), primary_key=True)
    # Deleting post also deletes post_tag rows

    # Without CASCADE (default RESTRICT)
    Column("post_id", ForeignKey("post.id"), primary_key=True)
    # Deleting post fails if post_tag rows exist

Choose cascade behavior based on data integrity requirements.

Next Steps
==========

For automatic deduplication and advanced patterns, see :doc:`advanced`.

Related Topics
==============

- :doc:`../repositories/filtering` - Filtering relationships
- :doc:`advanced` - UniqueMixin for automatic get-or-create
- :doc:`basics` - Base classes and simple models
