Contribution guide
==================

Setting up the environment
--------------------------

1. Run ``make install-uv`` to install `uv <https://docs.astral.sh/uv/>`_ if not already installed
1. Run ``make install`` to install all dependencies and pre-commit hooks

Code contributions
------------------

Workflow
++++++++

1. `Fork <https://github.com/litestar-org/advanced-alchemy/fork>`_ the `Advanced Alchemy repository <https://github.com/litestar-org/advanced-alchemy>`_
2. Clone your fork locally with git
3. `Set up the environment <#setting-up-the-environment>`_
4. Make your changes
5. Run ``make lint`` to run linters and formatters. This step is optional and will be executed
   automatically by git before you make a commit, but you may want to run it manually in order to apply fixes  automatically by git before you make a commit, but you may want to run it manually in order to apply fixes
6. Commit your changes to git
7. Push the changes to your fork
8. Open a `pull request <https://docs.github.com/en/pull-requests>`_. Give the pull request a descriptive title
   indicating what it changes. If it has a corresponding open issue, the issue number should be included in the title as
   well. For example a pull request that fixes issue ``bug: Increased stack size making it impossible to find needle #100``
   could be titled ``fix(#100): Make needles easier to find by applying fire to haystack``

.. tip:: Pull requests and commits all need to follow the
    `Conventional Commit format <https://www.conventionalcommits.org>`_

.. note:: To run the integration tests locally, you will need the `ODBC Driver for SQL Server <https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server?view=sql-server-ver16>`_, one option is using `unixODBC <https://www.unixodbc.org/>`_.

Guidelines for writing code
----------------------------

- All code should be fully `typed <https://peps.python.org/pep-0484/>`_. This is enforced via
  `mypy <https://mypy.readthedocs.io/en/stable/>`_.
- All code should be tested. This is enforced via `pytest <https://docs.pytest.org/en/stable/>`_.
- All code should be properly formatted. This is enforced via `Ruff <https://beta.ruff.rs/docs/>`_.

Writing and running tests
+++++++++++++++++++++++++

.. todo:: Write this section

Project documentation
---------------------

The documentation is located in the ``/docs`` directory and is `ReST <https://docutils.sourceforge.io/rst.html>`_ and
`Sphinx <https://www.sphinx-doc.org/en/master/>`_. If you're unfamiliar with any of those,
`ReStructuredText primer <https://www.sphinx-doc.org/en/master/lib/usage/restructuredtext/basics.html>`_ and
`Sphinx quickstart <https://www.sphinx-doc.org/en/master/lib/usage/quickstart.html>`_ are recommended reads.

Running the docs locally
++++++++++++++++++++++++

To run or build the docs locally, you need to first install the required dependencies:

``make install``

Then you can serve the documentation with ``make docs-serve``, or build them with ``make docs``.

Creating a new release
----------------------

1. **Set up your environment**

   - Ensure you have the ``gh`` CLI installed and logged in to GitHub.
   - Switch to the ``main`` branch.

2. **Install and update dependencies**

   - Run:

     .. code-block:: bash

        make install   # Install all dependencies
        make upgrade   # Update dependencies to the latest versions
        make docs      # Verify documentation builds

3. **Bump the version**

   - Run:

     .. code-block:: bash

        make release bump=patch

   - Use ``bump=minor`` or ``bump=major`` if you need to bump the minor or major version instead.

4. **Prepare the release**

   - Run:

     .. code-block:: bash

        uv run tools/prepare_release.py -c -i --base v{current_version} {new_version}

   - Replace ``{current_version}`` with the current version (e.g., ``1.2.3``).
   - Replace ``{new_version}`` with the new version (e.g., ``1.2.4``).
   - Example: ``uv run tools/prepare_release.py -c -i --base v1.4.4 1.4.5``

5. **Run linters and formatters**

   - Ensure code style compliance:

     .. code-block:: bash

        make lint

6. **Clean up the changelog**

   - Open ``docs/changelog.rst`` and remove any placeholder comments, such as:

     .. code-block:: rst

        <!-- By submitting this pull request, you agree to ... -->
        <!-- Please add in issue numbers this pull request will close ... -->

7. **Commit the release**

   - Create a new branch:

     .. code-block:: bash

        git checkout -b v{new_version}

   - Commit the changes:

     .. code-block:: bash

        git commit -am "chore(release): bump to v{new_version}"

8. **Open a pull request**

   - Push the branch and create a PR into ``main``.
   - Merge once CI checks pass.

9.  **Verify the release draft**

    - Once merged, a draft release will be created under ``Releases`` on GitHub.
    - Edit and publish it.

10. **Publish to PyPI**

    - Approve the ``Latest Release`` workflow under ``Actions`` to publish the package to PyPI.
