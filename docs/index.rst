:layout: landing
:description: Advanced Alchemy is a carefully crafted, thoroughly tested, optimized companion library for SQLAlchemy.

.. container::
    :name: home-head

    .. container::

        .. raw:: html

            <div class="title-with-logo">
                <div class="brand-text">Advanced Alchemy</div>
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

    Advanced Alchemy is a carefully crafted, thoroughly tested, optimized companion library for
    :doc:`SQLAlchemy <sqlalchemy:index>`.

It provides :doc:`base classes <reference/base>`, :doc:`mixins <reference/mixins/index>`, :doc:`custom column types <usage/types>`,
and implementations of the :doc:`repository <usage/repositories>` and :doc:`service layer <usage/services>` patterns
to simplify your database operations.

.. container:: buttons wrap

  .. raw:: html

    <a href="getting-started.html" class="btn-no-wrap">Get Started</a>
    <a href="usage/index.html" class="btn-no-wrap">Usage Docs</a>
    <a href="reference/index.html" class="btn-no-wrap">API Docs</a>

.. grid:: 1 1 2 2
    :padding: 0
    :gutter: 2

    .. grid-item-card:: :octicon:`versions` Changelog
      :link: changelog
      :link-type: doc

      The latest updates and enhancements to Advanced-Alchemy

    .. grid-item-card:: :octicon:`comment-discussion` Discussions
      :link: https://github.com/litestar-org/advanced-alchemy/discussions

      Join discussions, pose questions, or share insights.

    .. grid-item-card:: :octicon:`issue-opened` Issues
      :link: https://github.com/litestar-org/advanced-alchemy/issues

      Report issues or suggest new features.

    .. grid-item-card:: :octicon:`beaker` Contributing
      :link: contribution-guide
      :link-type: doc

      Contribute to Advanced Alchemy's growth with code, docs, and more.


.. _sponsor-github: https://github.com/sponsors/litestar-org
.. _sponsor-oc: https://opencollective.com/litestar
.. _sponsor-polar: https://polar.sh/litestar-org

.. toctree::
    :titlesonly:
    :caption: Documentation
    :hidden:

    getting-started
    usage/index
    reference/index

.. toctree::
    :titlesonly:
    :caption: Contributing
    :hidden:

    changelog
    contribution-guide
    Available Issues <https://github.com/search?q=user%3Alitestar-org+state%3Aopen+label%3A%22good+first+issue%22+++no%3Aassignee+repo%3A%22advanced-alchemy%22&type=issues>
    Code of Conduct <https://github.com/litestar-org/.github?tab=coc-ov-file#readme>
