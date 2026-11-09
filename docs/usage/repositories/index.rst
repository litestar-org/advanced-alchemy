============
Repositories
============

Without a repository, every web route ends up repeating the same SQLAlchemy query code: building a ``select()``, adding ``where()`` clauses, counting total rows for pagination, and handling ``NoResultFound`` errors.

A **Repository** wraps one table model and gives you ready-made, type-checked methods—``add``, ``get``, ``get_many``, ``list_and_count``, ``upsert_many``, and ``delete``—so your routes read like plain English.

.. container:: aa-diagram

    .. image:: /_static/diagrams/repository-flow-light.svg
        :alt: How a repository connects your code and filters to your SQL database
        :class: aa-diagram--light

    .. image:: /_static/diagrams/repository-flow-dark.svg
        :alt: How a repository connects your code and filters to your SQL database
        :class: aa-diagram--dark

.. grid:: 1 1 3 3
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

    .. grid-item-card:: :octicon:`lock` Advanced Patterns
      :link: advanced
      :link-type: doc

      Work with composite primary keys, row-level locks, and bulk conditional deletes.

.. toctree::
    :maxdepth: 1
    :hidden:

    basics
    filtering
    advanced
