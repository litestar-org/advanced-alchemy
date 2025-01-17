===============
Getting Started
===============

Advanced Alchemy is a carefully crafted, thoroughly tested, optimized companion library for :doc:`SQLAlchemy <sqlalchemy:index>`.

It provides :doc:`base classes <reference/base>`, :doc:`mixins <reference/mixins/index>`, :doc:`custom column types <usage/types>`,
and implementations of the :doc:`repository <usage/repositories>` and :doc:`service layer <usage/services>` patterns
to simplify your database operations.

.. seealso:: It is built on:

    * `SQLAlchemy <https://www.sqlalchemy.org/>`_
    * `Alembic <https://alembic.sqlalchemy.org/en/latest/>`_
    * `Typing Extensions <https://typing-extensions.readthedocs.io/en/latest/>`_

It's designed to work on its own or with your favorite web framework.

We've built extensions for some of the most popular frameworks, so you can get the most out of Advanced Alchemy with minimal effort.

* `Litestar <https://docs.litestar.dev/>`_
* `FastAPI <https://fastapi.tiangolo.com/>`_
* `Starlette <https://www.starlette.io/>`_
* `Flask <https://flask.palletsprojects.com/>`_
* `Sanic <https://sanicframework.org/>`_

If your framework is not listed, don't worry! Advanced Alchemy is designed to be modular and easily integrated with any Python web framework.
`Join our Discord <https://discord.gg/dSDXd4mKhp>`_ and we'll help you get started.

Installation
------------

Install ``advanced-alchemy`` with your favorite Python package manager:

.. tab-set::

    .. tab-item:: pip
        :sync: key1

        .. code-block:: bash
            :caption: Using pip

            python3 -m pip install advanced-alchemy

    .. tab-item:: uv

        .. code-block:: bash
            :caption: Using `UV <https://docs.astral.sh/uv/>`_

            uv add advanced-alchemy

    .. tab-item:: pipx
        :sync: key2

        .. code-block:: bash
            :caption: Using `pipx <https://pypa.github.io/pipx/>`_

            pipx install advanced-alchemy


    .. tab-item:: pdm

        .. code-block:: bash
            :caption: Using `PDM <https://pdm.fming.dev/>`_

            pdm add advanced-alchemy

    .. tab-item:: Poetry

        .. code-block:: bash
            :caption: Using `Poetry <https://python-poetry.org/>`_

            poetry add advanced-alchemy
