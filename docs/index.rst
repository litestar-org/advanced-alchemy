:layout: landing
:description: Advanced Alchemy is a carefully crafted, thoroughly tested, optimized companion library for SQLAlchemy.

.. container::
    :name: home-head

    .. raw:: html

        <div class="aa-hero">
            <img src="_static/banner-inline-light.svg" alt="Advanced Alchemy" class="aa-hero-banner aa-hero-banner--light" width="840" height="220" />
            <img src="_static/banner-inline-dark.svg" alt="Advanced Alchemy" class="aa-hero-banner aa-hero-banner--dark" width="840" height="220" />
        </div>

    .. container:: badges
        :name: badges

        .. image:: https://img.shields.io/github/actions/workflow/status/litestar-org/advanced-alchemy/publish.yml?labelColor=202235&logo=github&logoColor=edb641&label=Release
            :alt: GitHub Actions Latest Release Workflow Status

        .. image:: https://img.shields.io/github/actions/workflow/status/litestar-org/advanced-alchemy/ci.yml?labelColor=202235&logo=github&logoColor=edb641&label=Tests%20And%20Linting
            :alt: GitHub Actions CI Workflow Status

        .. image:: https://img.shields.io/github/actions/workflow/status/litestar-org/advanced-alchemy/docs.yml?labelColor=202235&logo=github&logoColor=edb641&label=Docs%20Build
            :alt: GitHub Actions Docs Build Workflow Status

        .. image:: https://img.shields.io/codecov/c/github/litestar-org/advanced-alchemy?labelColor=202235&logo=codecov&logoColor=edb641&label=Coverage
            :alt: Coverage

        .. image:: https://img.shields.io/pypi/v/advanced-alchemy?labelColor=202235&color=edb641&logo=python&logoColor=edb641
            :alt: PyPI Version

        .. image:: https://img.shields.io/pypi/dm/advanced-alchemy?logo=python&label=advanced-alchemy%20downloads&labelColor=202235&color=edb641&logoColor=edb641
            :alt: PyPI Downloads

        .. image:: https://img.shields.io/pypi/pyversions/advanced-alchemy?labelColor=202235&color=edb641&logo=python&logoColor=edb641
            :alt: Supported Python Versions

.. rst-class:: lead

    A carefully crafted, thoroughly tested, optimized companion library for `SQLAlchemy <https://docs.sqlalchemy.org/en/20/>`_.

Advanced Alchemy provides declarative bases with primary keys and audit timestamps, synchronous and asynchronous :doc:`repositories <usage/repositories/index>` and :doc:`services <usage/services>` for querying and schema conversion, and integrations for :doc:`Litestar, FastAPI, Starlette, Flask, and Sanic <usage/frameworks/index>`.

.. container:: buttons wrap

    .. raw:: html

        <a href="getting-started.html" class="aa-btn aa-btn--primary btn-no-wrap">Get Started</a>
        <a href="usage/index.html" class="aa-btn aa-btn--secondary btn-no-wrap">Usage Guide</a>
        <a href="usage/frameworks/index.html" class="aa-btn aa-btn--secondary btn-no-wrap">Frameworks</a>
        <a href="reference/index.html" class="aa-btn aa-btn--secondary btn-no-wrap">API Reference</a>

.. grid:: 1 1 2 2
    :padding: 0
    :gutter: 3

    .. grid-item-card:: :octicon:`table` Models & Column Types
      :link: usage/modeling/index
      :link-type: doc

      Start tables with built-in UUID or integer keys, automatic timestamps, encrypted fields, password hashes, and file storage.

    .. grid-item-card:: :octicon:`database` Repositories & Services
      :link: usage/repositories/index
      :link-type: doc

      Fetch, filter, paginate, and bulk-upsert records in one call, then convert rows directly into Pydantic or Msgspec schemas.

    .. grid-item-card:: :octicon:`plug` Web Framework Integrations
      :link: usage/frameworks/index
      :link-type: doc

      Automatic per-request database sessions, dependency injection, file uploads, and migration CLIs for Python web frameworks.

    .. grid-item-card:: :octicon:`server` Scaling & Operations
      :link: usage/routing
      :link-type: doc

      Configure read-replica routing, Dogpile query caching, Alembic migrations, and fixture seeding.


.. _sponsor-github: https://github.com/sponsors/litestar-org
.. _sponsor-oc: https://opencollective.com/litestar
.. _sponsor-polar: https://polar.sh/litestar-org

.. toctree::
    :titlesonly:
    :caption: Usage Guide
    :hidden:

    getting-started
    Overview <usage/index>
    Data Modeling <usage/modeling/index>
    Repositories <usage/repositories/index>
    Services <usage/services>
    Service Composition <usage/service_composition>
    Read/Write Routing <usage/routing>
    Caching <usage/caching>
    OpenTelemetry <usage/opentelemetry>
    CLI & Migrations <usage/cli>
    Database Seeding <usage/database_seeding>

.. toctree::
    :titlesonly:
    :caption: Framework Integrations
    :hidden:

    Overview <usage/frameworks/index>
    Litestar <usage/frameworks/litestar>
    FastAPI <usage/frameworks/fastapi>
    Starlette <usage/frameworks/starlette>
    Flask <usage/frameworks/flask>
    Sanic <usage/frameworks/sanic>

.. toctree::
    :titlesonly:
    :caption: API Reference
    :hidden:

    Overview <reference/index>
    Declarative Base <reference/base>
    Mixins <reference/mixins/index>
    Configuration <reference/config/index>
    Repositories <reference/repository>
    Memory Repositories <reference/repository_memory>
    Services <reference/service>
    Schema Conversion & Pagination <reference/service_conversion>
    Service Composition <reference/service_composition>
    Filters <reference/filters>
    Cursor Pagination <reference/cursor_pagination>
    Bulk Operations <reference/operations>
    Custom Types <reference/types>
    Replica Routing <reference/routing>
    Caching <reference/cache>
    Framework Extensions <reference/extensions/index>
    Alembic <reference/alembic/index>
    CLI Commands <reference/cli>
    Exceptions <reference/exceptions>
    Fixtures <reference/fixtures>
    Utilities <reference/utils>

.. toctree::
    :titlesonly:
    :caption: Contributing
    :hidden:

    changelog
    contribution-guide
    Available Issues <https://github.com/search?q=user%3Alitestar-org+state%3Aopen+label%3A%22good+first+issue%22+++no%3Aassignee+repo%3A%22advanced-alchemy%22&type=issues>
    Code of Conduct <https://github.com/litestar-org/.github?tab=coc-ov-file#readme>
