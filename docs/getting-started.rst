===============
Getting Started
===============

Advanced Alchemy is a carefully crafted, thoroughly tested, optimized companion library for :doc:`SQLAlchemy <sqlalchemy:index>`.

It provides :doc:`base classes <reference/base>`, :doc:`mixins <reference/mixins/index>`, :doc:`custom column types <usage/modeling/types>`,
and implementations of the :doc:`repository <usage/repositories/index>` and :doc:`service layer <usage/services>` patterns
to simplify your database operations.

.. seealso:: It is built on:

    * `SQLAlchemy <https://www.sqlalchemy.org/>`_
    * `Alembic <https://alembic.sqlalchemy.org/en/latest/>`_
    * `Typing Extensions <https://typing-extensions.readthedocs.io/en/latest/>`_

It is designed to work standalone or with your favorite web framework:

* `Litestar <https://docs.litestar.dev/>`_
* `FastAPI <https://fastapi.tiangolo.com/>`_
* `Starlette <https://www.starlette.io/>`_
* `Flask <https://flask.palletsprojects.com/>`_
* `Sanic <https://sanicframework.org/>`_

If your framework is not listed, Advanced Alchemy is modular and integrates cleanly with any Python web or worker framework.
`Join our Discord <https://discord.gg/dSDXd4mKhp>`_ if you have questions or need a hand getting started.

Installation
------------

Install ``advanced-alchemy`` with your preferred Python package manager:

.. tab-set::
    :sync-group: pkg

    .. tab-item:: uv
        :sync: uv

        .. code-block:: bash

            uv add advanced-alchemy

    .. tab-item:: pip
        :sync: pip

        .. code-block:: bash

            pip install advanced-alchemy

    .. tab-item:: pdm
        :sync: pdm

        .. code-block:: bash

            pdm add advanced-alchemy

    .. tab-item:: poetry
        :sync: poetry

        .. code-block:: bash

            poetry add advanced-alchemy
