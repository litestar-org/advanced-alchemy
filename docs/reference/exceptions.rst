==========
exceptions
==========

.. py:module:: advanced_alchemy.exceptions

Exception hierarchy and SQLAlchemy error translation utilities converting
low-level driver errors such as :exc:`sqlalchemy.exc.IntegrityError` and
:exc:`sqlalchemy.exc.OperationalError` into typed domain exceptions.

Base & Configuration Exceptions
-------------------------------

.. autoexception:: advanced_alchemy.exceptions.AdvancedAlchemyError
    :members: detail
    :no-inherited-members:
    :show-inheritance:

.. autoexception:: advanced_alchemy.exceptions.ImproperConfigurationError
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoexception:: advanced_alchemy.exceptions.MissingDependencyError
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoexception:: advanced_alchemy.exceptions.SerializationError
    :no-members:
    :no-inherited-members:
    :show-inheritance:

Repository & Integrity Exceptions
---------------------------------

.. autoexception:: advanced_alchemy.exceptions.RepositoryError
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoexception:: advanced_alchemy.exceptions.IntegrityError
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoexception:: advanced_alchemy.exceptions.DuplicateKeyError
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoexception:: advanced_alchemy.exceptions.ForeignKeyError
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoexception:: advanced_alchemy.exceptions.NotFoundError
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoexception:: advanced_alchemy.exceptions.MultipleResultsFoundError
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoexception:: advanced_alchemy.exceptions.InvalidRequestError
    :no-members:
    :no-inherited-members:
    :show-inheritance:

Exception Translation & Error Templates
---------------------------------------

.. autoclass:: advanced_alchemy.exceptions.ErrorMessages
    :members:
    :no-inherited-members:
    :show-inheritance:

.. autofunction:: advanced_alchemy.exceptions.wrap_sqlalchemy_exception
