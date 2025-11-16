========
Modeling
========

Advanced Alchemy enhances SQLAlchemy's modeling capabilities with production-ready base classes, mixins, and specialized types.

Learning Path
=============

Follow this progression to master Advanced Alchemy modeling:

.. grid:: 1 1 3 3
    :gutter: 2

    .. grid-item-card:: 1. Basics
        :link: basics
        :link-type: doc
        :text-align: center

        Core concepts and simple models

    .. grid-item-card:: 2. Relationships
        :link: relationships
        :link-type: doc
        :text-align: center

        Connecting models together

    .. grid-item-card:: 3. Advanced
        :link: advanced
        :link-type: doc
        :text-align: center

        Complex patterns and optimization

.. toctree::
   :hidden:
   :maxdepth: 1

   basics
   relationships
   advanced

Overview
========

Advanced Alchemy provides:

- Pre-configured base classes with common primary key strategies (UUID, BigInt, NanoID)
- Automatic audit fields (created_at, updated_at)
- Mixins for common patterns (slugs, unique constraints)
- Support for all SQLAlchemy 2.0 features

Quick Start
===========

The simplest model using BigIntAuditBase:

.. code-block:: python

    from advanced_alchemy.base import BigIntAuditBase
    from sqlalchemy.orm import Mapped, mapped_column

    class Post(BigIntAuditBase):
        title: Mapped[str] = mapped_column(index=True)
        content: Mapped[str]

This model includes:

- Auto-incrementing BigInt primary key (``id``)
- Automatic ``created_at`` timestamp on creation
- Automatic ``updated_at`` timestamp on modifications
- Automatic table naming convention

Next Steps
==========

- :doc:`basics` - Base classes, simple models, primary key patterns
- :doc:`relationships` - Foreign keys and many-to-many relationships
- :doc:`advanced` - Mixins, custom types, and advanced patterns
