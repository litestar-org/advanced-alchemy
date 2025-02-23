:orphan:

0.x Changelog
=============

.. changelog:: 0.32.0
    :date: 2025-02-23

    .. change:: remove `limit` and `offset` from count statement
        :type: bugfix
        :pr: 395

        Remove `limit` and `offset` from count statement

    .. change:: rename `force_basic_query_mode`
        :type: misc
        :pr: 396

        Renames `force_basic_query_mode` to `count_with_window_function`.  This is also exposed as a class/init parameter for the service and repository.

    .. change:: add Enum to default type decoders
        :type: feature
        :pr: 397

        Extends the default `msgspec` type decoders to handle Enum types by converting them to their underlying value during serialization



.. changelog:: 0.31.0
    :date: 2025-02-18

    .. change:: Fix reference in `changelog.py`
        :type: bugfix
        :pr: 383

        Should link to the AA repo, not litestar :)

    .. change:: Query repository list method for custom queries
        :type: bugfix
        :pr: 379
        :issue: 338

        Fix query repositories list method according to [documentation](https://docs.advanced-alchemy.litestar.dev/latest/usage/repositories.html#query-repository).

        Now its return a list of tuples with values instead of first column of the query.

    .. change:: remove 3.8 support
        :type: misc
        :pr: 386

        Removes 3.8 support and removes future annotations in a few places for better compatibility

    .. change:: remove future annotations
        :type: feature
        :pr: 387

        This removes the usage of future annotations.

    .. change:: add `uniquify` to service and repo
        :type: feature
        :pr: 389

        Exposes the `uniquify` flag in all functions on the repository and add to the service

    .. change:: improved default serializer
        :type: feature
        :pr: 390

        Improves the default serializer so that it handles various types a bit better


.. changelog:: 0.30.3
    :date: 2025-01-26

    .. change:: add `wrap_exceptions` option to exception handler.
        :type: feature
        :pr: 363
        :issue: 356

        When `wrap_exceptions` is `False`, the original SQLAlchemy error message will be raised instead of the wrapped Repository error

        Fixes #356 (Bug: `wrap_sqlalchemy_exception` masks db errors)

    .. change:: simplify configuration hash
        :type: feature
        :pr: 366

        The hashing method on the SQLAlchemy configs can be simplified.  This should be enough to define a unique configuration.

    .. change:: use `lifespan` context manager in Starlette and FastAPI
        :type: bugfix
        :pr: 368
        :issue: 367

        Modifies the Starlette and FastAPI integrations to use the `lifespan` context manager instead of the `startup`\`shutdown` hooks.  If the application already has a lifespan set, it is wrapped so that both execute.


.. changelog:: 0.30.2
    :date: 2025-01-21

    .. change:: add hash to config classes
        :type: feature
        :pr: 358
        :issue: 357

        Adds hash function to `SQLAlchemySyncConfig` and `SQLAlchemyAsyncConfig` classes.


.. changelog:: 0.30.1
    :date: 2025-01-20

    .. change:: Using init db CLI command creates migrations directory in unexpected place
        :type: bugfix
        :pr: 354
        :issue: 351

        When initializing migrations with the CLI, if no directory is specified, the directory from the configuration will be used.


.. changelog:: 0.30.0
    :date: 2025-01-19

    .. change:: standardize on `autocommit_include_redirect`
        :type: bugfix
        :pr: 349

        The flask plugin incorrectly used the term `autocommit_with_redirect` instead of the existing `autocommit_include_redirect`.

        This changes makes the name consistent before we bump to a `1.x` release

    .. change:: implement default schema serializer
        :type: bugfix
        :pr: 350

        This corrects an issue that caused the Flask extension to use the incorrect serializer for encoding JSON

    .. change:: refactored integration with CLI support
        :type: feature
        :pr: 352

        Refactored the Starlette and FastAPI integration to support multiple configurations and sessions.  Additionally, FastAPI will now have the database commands automatically registered with the FastAPI CLI.

    .. change:: reorganize Sanic extension
        :type: feature
        :pr: 353

        The Sanic integration now aligns with the structure and idioms used in the other integrations.


.. changelog:: 0.29.1
    :date: 2025-01-17

    .. change:: add convenience hooks for `to_model` operations
        :type: feature
        :pr: 347

        The service layer has always has a `to_model` function that accepts data and optionally an operation name.  It would return a SQLAlchemy model no matter the input you gave it.

        It is possible to move business logic into this `to_model` layer for populating fields on insert.  (i.e. slug fields or tags, etc.).

        When having logic for `insert`, `update`, `delete`, and `upsert`, that function can be a bit overwhelcoming.  Now, there are helper functions that you can use that is specific to each DML hook:

        * `to_model_on_create`
        * `to_model_on_update`
        * `to_model_on_delete`
        * `to_model_on_upsert`


.. changelog:: 0.29.0
    :date: 2025-01-17

    .. change:: fully qualify all `datetime` module references
        :type: bugfix
        :pr: 341

        All date time references are now full qualified to prevent any forward resolution issues with

        `from datetime import datetime`

        and

        `import datetime`

    .. change:: disabled `timezone` in alembic.ini
        :type: bugfix
        :pr: 344

        Disabled `timezone` in alembic.ini to fix `alembic.util.exc.CommandError: Can't locate timezone: UTC` error while applying migrations

        Reference:
        https://alembic.sqlalchemy.org/en/latest/tutorial.html#editing-the-ini-file

    .. change:: various typing improvements for services
        :type: feature
        :pr: 342
        :issue: 261

        Improved typing in the service layer and adds a additional type guards.

    .. change:: Auto extend Flask CLI and add session integration
        :type: feature
        :pr: 111

        The Advanced Alchemy alembic CLI is now auto-extended to your Flask application.

        The Flask extension now also has a session handling middleware for handling auto-commits.

        Last, but not least, there's an experimental async portal that integrates a long running asyncio loop for running async operations in Flask.  Using `foo = portal.call(<async function>)` you can get the result of an asynchronous function from a sync context.



.. changelog:: 0.28.0
    :date: 2025-01-13

    .. change:: add `bind-key` option to CLI
        :type: feature
        :pr: 339

        Adds a `bind-key` option to the Advance Alchemy CLI groups.

        When present, the Alembic configs will be injected with the corresponding key.


.. changelog:: 0.27.1
    :date: 2025-01-11

    .. change:: correction for `3.8` and `3.9` type hints
        :type: bugfix
        :pr: 330

        Makes a few corrections to type hints in examples and tests to ensure 3.8 and 3.9 support


.. changelog:: 0.27.0
    :date: 2025-01-11


    .. change:: add `error_messages` as class level configuration
        :type: feature
        :pr: 315

        Exposes ``error_messages`` as a class level configuration in the repository and service classes.

    .. change:: implement reusable CLI
        :type: feature
        :pr: 320

        Exposes a reusable CLI for creating and updating releases.  This can be used to extend any existing Click or Typer CLI.

    .. change:: adds additional type guard helpers
        :type: feature
        :pr: 322

        Addition typing utilities to help with type checking and validation.



.. changelog:: 0.26.0
    :date: 2025-01-11

    .. change:: `AsyncAttrs` & remove `noload` default
        :type: feature
        :pr: 305

        This PR adds the `AsyncAttrs` to the default declarative bases for convenience.

        It also changes the `inherit_lazy_relationships == False` behavior to use `lazyload`.  SQLAlchemy will be deprecating `noload` in version 2.1

    .. change:: `litestar` DTO enhancements
        :type: feature
        :pr: 310
        :issue: 306

        The Litestar DTO has been enhanced with:
        - The SQLAlchemyDTOConfig's `exclude`, `include`, and `rename_fields` fields will now accept string or `InstrumentedAttributes`
        - DTO supports `WriteOnlyMapped` and `DynamicMapped`


    .. change:: add default exception handler for `litestar` integration
        :type: feature
        :pr: 308
        :issue: 275

        This adds a configuration option to automatically enable an exception handler for Repository errors.

        This will update the exception handler if you do not have one already configured for the RepositoryException class


.. changelog:: 0.25.0
    :date: 2025-01-11

    .. change:: add max length for encrypted string
        :type: feature
        :pr: 290

        The EncryptedString field now has the ability to validate against a set length.


    .. change:: `AsyncAttrs` & remove `noload` default
        :type: feature
        :pr: 305

        This PR adds the `AsyncAttrs` to the default declarative bases for convenience.

        It also changes the `inherit_lazy_relationships == False` behavior to use `lazyload`.  SQLAlchemy will be deprecating `noload` in version 2.1


.. changelog:: 0.24.0
    :date: 2025-01-11

    .. change:: remove lambda statement usage
        :type: feature
        :pr: 288
        :issue: 286, 287

        Removes the use of lambda statements in the repository and service classes.  This has no change on the end user API, however, it should remove strange queries errors seen.

.. changelog:: 0.23.0
    :date: 2025-01-11

    .. change:: regression caused by conditional import Sequence for pagination.py
        :type: bugfix
        :pr: 274
        :issue: 272

        Import Sequence directly from collections.abc
        Remove conditional import using TYPE_CHECKING
        Add noqa comment to suppress potential linter warnings

    .. change:: make sure `anyio` is optional
        :type: bugfix
        :pr: 278

        When running standalone or with a synchronous web framework, `anyio` is not required.  This PR ensures that there are no module loading failures due to the missing import.

    .. change:: Improved typing of `ModelDictT`
        :type: feature
        :pr: 277

        Fixes typing issues in service


        https://github.com/litestar-org/advanced-alchemy/issues/265

        This still doesn't solve the problem of UnknownVariableType if the subtypes of ModelDictT are not installed (eg: Pydantic)
        But at least it solves the problem of incompatibilities when they are installed


.. changelog:: 0.22.0
    :date: 2025-01-11

    .. change:: CLI argument adjustment
        :type: bugfix
        :pr: 270

        Changes the argument name so that it matches the name given in `click.option`.


.. changelog:: 0.21.0
    :date: 2025-01-11

    .. change:: bind session to session class instead of to the session maker
        :type: bugfix
        :pr: 268
        :issue: 267

        binds session into sanic extension as expected

        in the original code, session maker was defined and then the dependency for session overwrites it with a session maker as the type.  this seems non-ideal -- you can't get the session maker and when you ask for the session maker you get a session object

        instead, this looks at the sessionmaker `class_` property for adding the sanic dependency


    .. change:: correct regex mappings for duplicate and foreign key errors
        :type: bugfix
        :pr: 266
        :issue: 262

        Swap the variable names for DUPLICATE_KEY_REGEXES and FOREIGN_KEY_REGEXES to correctly match their contents.
        This ensures that the error detection for duplicate keys and foreign key violations works as intended across different database backends.

    .. change:: Dump all tables as JSON
        :type: feature
        :pr: 259

        Adds a new CLI command to export tables to JSON.  Similar to a Django dumpdata command.


.. changelog:: <=0.20.0
    :date: 2025-01-11

    .. change:: CollectionFilter returns all entries if values is empty
        :type: bugfix
        :pr: 52
        :issue: 51

        Fixes #51

        Bug: CollectionFilter returns all entries if values is empty

        a simple `1=-1` is appended into the `where` clause when an empty list is passed into the `in` statement.

    .. change:: better handle empty collection filters
        :type: bugfix
        :pr: 62

        Currently, [this](https://github.com/cofin/litestar-fullstack/blob/main/src/app/lib/dependencies.py#L169) is how you can inject these filters in your app.

        When using the `id_filter` dependency on it's own, you have to have an additional not-null check before passing it into the repository.

        This change handles that and allows you to pass in all filters into the repository function without checking their nullability.

    .. change:: service `exists` should use `exists` from repository
        :type: bugfix
        :pr: 68

        The service should use the repository's implementation of `exists` instead of a new one with a `count`.

    .. change:: do not set `id` with `item_id` when `None`
        :type: bugfix
        :pr: 67

        This PR prevents the primary key from being overrwitten with `None` when using the service without the `item_id` parameter.

    .. change:: sqlalchemy dto for models non `Column` fields
        :type: bugfix
        :pr: 75

        Examples of such fields are `ColumnClause` and `Label`, these are generated when using `sqlalchemy.func`

        - Fix SQLAlchemy dto generation for litestar when using models that have fields that are not instances of `Column`. Such fields arise from using expressions such as `func`.
