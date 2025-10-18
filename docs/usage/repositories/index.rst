============
Repositories
============

Advanced Alchemy's repository pattern provides a clean, consistent interface for database operations with type-safe CRUD operations and filtering capabilities.

Learning Path
=============

.. toctree::
   :maxdepth: 1

   basics
   filtering
   advanced

Prerequisites
=============

- Understanding of :doc:`../modeling/basics`
- Python 3.9+
- SQLAlchemy 2.0+

Overview
========

A repository acts as a collection-like interface to your database models, providing:

- Type-safe CRUD operations
- Filtering and pagination
- Bulk operations
- Transaction management
- Specialized repository types for common patterns

Repository Types
================

Advanced Alchemy provides async and sync repository implementations:

.. list-table:: Repository Types
   :header-rows: 1
   :widths: 30 70

   * - Repository Class
     - Features
   * - ``SQLAlchemyAsyncRepository``
     - | - Async session support
       | - Basic CRUD operations
       | - Filtering and pagination
       | - Bulk operations
   * - ``SQLAlchemyAsyncSlugRepository``
     - | - Async session support
       | - All base repository features
       | - Slug-based lookups
       | - URL-friendly operations
   * - ``SQLAlchemyAsyncQueryRepository``
     - | - Async session support
       | - Custom query execution
       | - Complex aggregations
       | - Raw SQL support
   * - ``SQLAlchemySyncRepository``
     - | - Sync session support
       | - Basic CRUD operations
       | - Filtering and pagination
       | - Bulk operations
   * - ``SQLAlchemySyncSlugRepository``
     - | - Sync session support
       | - All base repository features
       | - Slug-based lookups
       | - URL-friendly operations
   * - ``SQLAlchemySyncQueryRepository``
     - | - Sync session support
       | - Custom query execution
       | - Complex aggregations
       | - Raw SQL support

Quick Start
===========

Creating a basic repository:

.. code-block:: python

    from advanced_alchemy.repository import SQLAlchemyAsyncRepository
    from sqlalchemy.ext.asyncio import AsyncSession

    class PostRepository(SQLAlchemyAsyncRepository[Post]):
        """Repository for managing blog posts."""
        model_type = Post

    async def create_post(db_session: AsyncSession, title: str, content: str) -> Post:
        repository = PostRepository(session=db_session)
        return await repository.add(
            Post(title=title, content=content), auto_commit=True
        )

Next Steps
==========

- :doc:`basics` - CRUD operations and simple queries
- :doc:`filtering` - Pagination, sorting, and search
- :doc:`advanced` - Bulk operations and custom queries

Related Topics
==============

- :doc:`../modeling/basics` - Defining models for repositories
- :doc:`../services/index` - Service layer built on repositories
