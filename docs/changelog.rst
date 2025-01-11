:orphan:

0.x Changelog
=============

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
