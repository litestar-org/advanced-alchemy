========
Services
========

Services in Advanced Alchemy build upon repositories to provide higher-level business logic, data transformation, and schema validation.

Learning Path
=============

Follow this progression to master Advanced Alchemy services:

.. grid:: 1 1 3 3
    :gutter: 2

    .. grid-item-card:: 1. Basics
        :link: basics
        :link-type: doc
        :text-align: center

        Service pattern and basic CRUD

    .. grid-item-card:: 2. Schemas
        :link: schemas
        :link-type: doc
        :text-align: center

        Pydantic/msgspec integration

    .. grid-item-card:: 3. Advanced
        :link: advanced
        :link-type: doc
        :text-align: center

        Complex operations and hooks

.. toctree::
   :hidden:
   :maxdepth: 1

   basics
   schemas
   advanced

Prerequisites
=============

- Understanding of :doc:`../repositories/basics`
- Python 3.9+
- SQLAlchemy 2.0+
- Optional: Pydantic v2 or Msgspec for schema validation

Overview
========

Services provide:

- Business logic abstraction
- Data transformation using Pydantic, Msgspec, or attrs models
- Input validation and type-safe schema conversion
- Complex operations involving multiple repositories
- Consistent error handling
- Automatic schema validation and transformation

Service Layer Benefits
======================

While repositories handle database operations, services handle:

**Business Logic**
  Complex rules spanning multiple models

**Data Transformation**
  Convert between database models and API schemas

**Schema Validation**
  Type-safe input validation using Pydantic/msgspec

**Multi-Repository Coordination**
  Operations across multiple repositories in single transaction

Quick Start
===========

Creating a basic service:

.. code-block:: python

    from advanced_alchemy.service import SQLAlchemyAsyncRepositoryService
    from pydantic import BaseModel

    class PostCreate(BaseModel):
        title: str
        content: str

    class PostService(SQLAlchemyAsyncRepositoryService[Post]):
        """Service for managing blog posts with automatic schema validation."""

        repository_type = PostRepository

    async def create_post(
        post_service: PostService,
        data: PostCreate,
    ) -> Post:
        """Create a post with validation."""
        return await post_service.create(
            data,
            auto_commit=True,
        )

Next Steps
==========

- :doc:`basics` - Service pattern and basic CRUD
- :doc:`schemas` - Pydantic/msgspec integration
- :doc:`advanced` - Complex operations and hooks

Related Topics
==============

- :doc:`../repositories/index` - Repository layer
- :doc:`../frameworks/index` - Framework integration
