========
Advanced
========

Advanced Alchemy provides sophisticated patterns for complex modeling requirements.

Prerequisites
=============

This section assumes familiarity with :doc:`basics` and :doc:`relationships`.

.. _using_unique_mixin:

Using UniqueMixin
=================

``UniqueMixin`` provides automatic handling of unique constraints and merging of duplicate records. When using the mixin,
you must implement two classmethods: ``unique_hash`` and ``unique_filter``. These methods enable:

- Automatic lookup of existing records
- Safe merging of duplicates
- Atomic get-or-create operations
- Configurable uniqueness criteria

Basic UniqueMixin Usage
-----------------------

Enhancing the Tag model with ``UniqueMixin``:

.. code-block:: python

    from advanced_alchemy.base import BigIntAuditBase
    from advanced_alchemy.mixins import SlugKey, UniqueMixin
    from advanced_alchemy.utils.text import slugify
    from sqlalchemy.sql.elements import ColumnElement
    from sqlalchemy.orm import Mapped, mapped_column
    from typing import Hashable

    class Tag(BigIntAuditBase, SlugKey, UniqueMixin):
        """Tag model with unique name constraint and automatic slug generation.

        The UniqueMixin provides:
        - Automatic lookup of existing records
        - Safe merging of duplicates
        - Consistent slug generation
        """

        name: Mapped[str] = mapped_column(unique=True, index=True)
        posts: Mapped[list[Post]] = relationship(
            secondary=post_tag,
            back_populates="tags",
            viewonly=True
        )

        @classmethod
        def unique_hash(cls, name: str, slug: str | None = None) -> Hashable:
            """Generate a unique hash for deduplication.

            Args:
                name: Tag name
                slug: Optional slug (auto-generated if not provided)

            Returns:
                Hashable value for deduplication
            """
            return slugify(name)

        @classmethod
        def unique_filter(
            cls,
            name: str,
            slug: str | None = None,
        ) -> ColumnElement[bool]:
            """SQL filter for finding existing records.

            Args:
                name: Tag name
                slug: Optional slug

            Returns:
                SQLAlchemy filter expression
            """
            return cls.slug == slugify(name)

The ``unique_hash`` method generates a deduplication key, while ``unique_filter`` creates the SQL WHERE clause for lookups.

Using as_unique_async
---------------------

The ``as_unique_async`` method simplifies get-or-create logic:

.. code-block:: python

    from sqlalchemy.ext.asyncio import AsyncSession
    from advanced_alchemy.utils.text import slugify

    async def add_tags_to_post(
        db_session: AsyncSession,
        post: Post,
        tag_names: list[str]
    ) -> Post:
        """Add tags to a post, creating new tags if needed."""
        # The UniqueMixin automatically handles:
        # 1. Looking up existing tags
        # 2. Creating new tags if needed
        # 3. Merging duplicates
        post.tags = [
          await Tag.as_unique_async(db_session, name=tag_text, slug=slugify(tag_text))
          for tag_text in tag_names
        ]
        db_session.merge(post)
        await db_session.flush()
        return post

This pattern:

- Calls ``unique_filter`` to search for existing tags
- Creates new tag if not found
- Returns existing tag if found
- Handles race conditions during concurrent creation

UniqueMixin in Production
--------------------------

Real-world get-or-create pattern for tags:

.. code-block:: python

    from advanced_alchemy.utils.text import slugify

    async def get_or_create_tag(session: AsyncSession, name: str) -> Tag:
        """Get existing tag or create new one atomically."""
        tag = await Tag.as_unique_async(
            session=session,
            name=name,
            slug=slugify(name),
        )
        return tag

    async def sync_post_tags(
        session: AsyncSession,
        post: Post,
        tag_names: list[str]
    ) -> Post:
        """Synchronize post tags, handling adds and removes."""
        # Get or create all tags
        new_tags = [
            await get_or_create_tag(session, name)
            for name in tag_names
        ]

        # Find tags to remove
        existing_tag_names = {tag.name for tag in post.tags}
        tags_to_remove = [
            tag for tag in post.tags
            if tag.name not in tag_names
        ]

        # Remove old tags
        for tag in tags_to_remove:
            post.tags.remove(tag)

        # Add new tags
        new_tag_names = set(tag_names) - existing_tag_names
        post.tags.extend([
            tag for tag in new_tags
            if tag.name in new_tag_names
        ])

        await session.flush()
        return post

This pattern:

- Atomically gets or creates tags
- Handles tag addition and removal
- Prevents duplicate tags
- Works with concurrent requests
- Integrates with service layer

Sync Version
------------

For synchronous code, use ``as_unique``:

.. code-block:: python

    from sqlalchemy.orm import Session

    def add_tags_to_post(
        db_session: Session,
        post: Post,
        tag_names: list[str]
    ) -> Post:
        """Sync version of tag addition."""
        post.tags = [
          Tag.as_unique(db_session, name=tag_text, slug=slugify(tag_text))
          for tag_text in tag_names
        ]
        db_session.merge(post)
        db_session.flush()
        return post

Implementation Patterns
=======================

Composite Unique Constraints
-----------------------------

``UniqueMixin`` supports composite unique constraints:

.. code-block:: python

    from sqlalchemy import UniqueConstraint
    from advanced_alchemy.base import BigIntAuditBase
    from advanced_alchemy.mixins import UniqueMixin
    from sqlalchemy.sql.elements import ColumnElement
    from sqlalchemy.orm import Mapped, mapped_column
    from typing import Hashable

    class UserProfile(BigIntAuditBase, UniqueMixin):
        """User profile with composite unique constraint."""

        __table_args__ = (
            UniqueConstraint("user_id", "profile_type", name="uq_user_profile"),
        )

        user_id: Mapped[int] = mapped_column(index=True)
        profile_type: Mapped[str] = mapped_column(index=True)
        data: Mapped[str]

        @classmethod
        def unique_hash(cls, user_id: int, profile_type: str, **kwargs) -> Hashable:
            """Generate hash from composite key."""
            return (user_id, profile_type)

        @classmethod
        def unique_filter(
            cls,
            user_id: int,
            profile_type: str,
            **kwargs
        ) -> ColumnElement[bool]:
            """Filter by composite key."""
            return (cls.user_id == user_id) & (cls.profile_type == profile_type)

This pattern handles uniqueness across multiple columns.

Custom Declarative Base
========================

Advanced Alchemy supports customizing the ``DeclarativeBase`` class for specific requirements.

Server-Side UUID Primary Key
-----------------------------

Example showing server-side UUID generation for PostgreSQL:

.. code-block:: python

    import datetime
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

        id: Mapped[UUID] = mapped_column(default=uuid4, primary_key=True, server_default=text("gen_random_uuid()"))
        """UUID Primary key column."""

        # noinspection PyMethodParameters
        @declared_attr
        def _sentinel(cls) -> Mapped[int]:
            """Sentinel value required for SQLAlchemy bulk DML with UUIDs."""
            return orm_insert_sentinel(name="sa_orm_sentinel")


    class ServerSideUUIDBase(ServerSideUUIDPrimaryKey, CommonTableAttributes, DeclarativeBase):
        """Base for all SQLAlchemy declarative models with the custom UUID primary key."""

        registry = orm_registry


    # Using ServerSideUUIDBase
    class User(ServerSideUUIDBase):
        """User model with ServerSideUUIDBase."""

        username: Mapped[str] = mapped_column(unique=True, index=True)
        email: Mapped[str] = mapped_column(unique=True)
        full_name: Mapped[str]
        is_active: Mapped[bool] = mapped_column(default=True)
        last_login: Mapped[datetime.datetime | None] = mapped_column(default=None)

This configuration:

- Generates UUIDs server-side using PostgreSQL's ``gen_random_uuid()``
- Includes sentinel value for SQLAlchemy bulk operations
- Uses ``CommonTableAttributes`` for table naming conventions
- Registers with ``orm_registry`` for Alembic integration

Custom Primary Key Strategy
----------------------------

Creating a custom primary key strategy:

.. code-block:: python

    from advanced_alchemy.base import CommonTableAttributes, orm_registry
    from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

    class CustomPrimaryKeyMixin:
        """Custom primary key mixin."""

        id: Mapped[str] = mapped_column(primary_key=True)

        def __init__(self, **kwargs):
            """Initialize with custom ID generation."""
            if "id" not in kwargs:
                kwargs["id"] = self.generate_id()
            super().__init__(**kwargs)

        @staticmethod
        def generate_id() -> str:
            """Generate custom ID format."""
            import secrets
            return f"cust_{secrets.token_urlsafe(16)}"


    class CustomBase(CustomPrimaryKeyMixin, CommonTableAttributes, DeclarativeBase):
        """Base with custom primary key generation."""

        registry = orm_registry


    class Product(CustomBase):
        """Product model with custom ID."""

        name: Mapped[str] = mapped_column(unique=True)
        price: Mapped[float]

This pattern generates custom ID formats (e.g., ``cust_xyz123``).

Technical Constraints
=====================

UniqueMixin Race Conditions
----------------------------

``UniqueMixin`` handles concurrent creation attempts:

.. code-block:: python

    # ✅ Correct - as_unique_async handles race conditions
    tag = await Tag.as_unique_async(session, name="python", slug="python")
    # If another transaction creates the tag between lookup and insert,
    # as_unique_async will detect and return the existing record

Implementation:

- Checks cache (``unique_hash``) first
- Queries database if not in cache
- Catches integrity errors on insert
- Re-queries to return existing record

Session State Requirements
---------------------------

``UniqueMixin`` requires an active session:

.. code-block:: python

    # ✅ Correct - session is active
    async with session.begin():
        tag = await Tag.as_unique_async(session, name="python")
        # Session is active, operations succeed

    # ❌ Incorrect - session is closed
    tag = await Tag.as_unique_async(session, name="python")
    await session.commit()
    # Accessing tag attributes after commit may fail

Keep session active when using ``as_unique_async`` results.

Custom Base Requirements
-------------------------

Custom declarative bases must include:

.. code-block:: python

    # ✅ Correct - includes required components
    class CustomBase(CommonTableAttributes, DeclarativeBase):
        registry = orm_registry  # Required for Alembic
        # CommonTableAttributes provides table naming conventions

    # ❌ Incorrect - missing registry
    class CustomBase(DeclarativeBase):
        pass  # Alembic integration will fail

Always include ``orm_registry`` and ``CommonTableAttributes`` for full Advanced Alchemy functionality.

Next Steps
==========

With advanced modeling patterns in place, explore repositories for data access.

Related Topics
==============

- :doc:`../repositories/index` - Using models with repositories
- :doc:`../types` - Custom column types
- :doc:`basics` - Base classes and simple models
- :doc:`relationships` - Foreign keys and many-to-many patterns
