============
Repositories
============

A **Repository** binds to a single SQLAlchemy model and provides typed synchronous or asynchronous methods (``add``, ``get``, ``get_many``, ``get_many_and_count``, ``upsert_many``, ``delete``) for CRUD, filtering, pagination, and dialect-translated error handling.

.. container:: aa-diagram

    .. image:: /_static/diagrams/repository-flow-light.svg
        :alt: How a repository connects your code and filters to your SQL database
        :class: aa-diagram--light

    .. image:: /_static/diagrams/repository-flow-dark.svg
        :alt: How a repository connects your code and filters to your SQL database
        :class: aa-diagram--dark

.. grid:: 1 1 2 2
    :padding: 0
    :gutter: 3

    .. grid-item-card:: :octicon:`database` Repository Basics
      :link: basics
      :link-type: doc

      Add, fetch, update, bulk-upsert, and delete records with async or sync repositories.

    .. grid-item-card:: :octicon:`filter` Filtering & Pagination
      :link: filtering
      :link-type: doc

      Search text, filter by IDs or dates, and return paginated results with total counts.

    .. grid-item-card:: :octicon:`arrow-right` Cursor Pagination
      :link: cursor_pagination
      :link-type: doc

      Page large or changing tables by position, with signed tokens and stable ordering.

    .. grid-item-card:: :octicon:`lock` Advanced Patterns
      :link: advanced
      :link-type: doc

      Work with composite primary keys, row-level locks, and bulk conditional deletes.

.. toctree::
    :maxdepth: 1
    :hidden:

    basics
    filtering
    filtersets
    cursor_pagination
    advanced
