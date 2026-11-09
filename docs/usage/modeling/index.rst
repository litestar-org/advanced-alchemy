=============
Data Modeling
=============

Every database table needs a few essentials: a primary key, clear column types, and usually ``created_at`` and ``updated_at`` timestamps so you know when rows changed.

Advanced Alchemy gives you ready-to-use base classes and portable column types so you only write the columns unique to your app.

.. grid:: 1 1 2 2
    :padding: 0
    :gutter: 3

    .. grid-item-card:: :octicon:`rows` Modeling Basics
      :link: basics
      :link-type: doc

      Pick a base class for integer or UUID keys, add URL slugs, and wire relationships between tables.

    .. grid-item-card:: :octicon:`git-branch` Table Inheritance
      :link: inheritance
      :link-type: doc

      Share columns across related models using single-table, joined-table, or concrete-table layouts.

    .. grid-item-card:: :octicon:`sliders` Portable Column Types
      :link: types
      :link-type: doc

      Store UTC timestamps, UUIDs, JSON documents, and vector embeddings that work across SQLite and production SQL engines.

    .. grid-item-card:: :octicon:`shield-lock` Security & File Storage
      :link: security_and_storage_types
      :link-type: doc

      Encrypt sensitive strings, hash passwords, verify one-time codes, and attach uploaded files to rows.

.. toctree::
    :maxdepth: 1
    :hidden:

    basics
    inheritance
    sqlmodel
    types
    security_and_storage_types
