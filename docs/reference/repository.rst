============
Repositories
============

.. py:module:: advanced_alchemy.repository

Async Repositories
------------------

.. autoclass:: advanced_alchemy.repository.SQLAlchemyAsyncRepository
    :members: add, get, list, list_and_count, update, delete, count
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.repository.SQLAlchemyAsyncSlugRepository
    :members: get_by_slug
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.repository.SQLAlchemyAsyncQueryRepository
    :members: get_one, list
    :no-inherited-members:
    :show-inheritance:

Sync Repositories
-----------------

.. autoclass:: advanced_alchemy.repository.SQLAlchemySyncRepository
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.repository.SQLAlchemySyncSlugRepository
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.repository.SQLAlchemySyncQueryRepository
    :no-members:
    :no-inherited-members:
    :show-inheritance:

Protocols & Base Mixins
-----------------------

.. autoclass:: advanced_alchemy.repository.SQLAlchemyAsyncRepositoryProtocol
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.repository.SQLAlchemyAsyncSlugRepositoryProtocol
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.repository.SQLAlchemySyncRepositoryProtocol
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.repository.SQLAlchemySyncSlugRepositoryProtocol
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.repository.FilterableRepository
    :members: model_type
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.repository.FilterableRepositoryProtocol
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.repository.ModelRepositoryMixin
    :no-members:
    :no-inherited-members:
    :show-inheritance:

Helpers & Type Definitions
--------------------------

.. autofunction:: advanced_alchemy.repository.get_instrumented_attr

.. autofunction:: advanced_alchemy.repository.model_from_dict

.. autofunction:: advanced_alchemy.repository.resolve_generic_type_args

.. py:data:: DEFAULT_ERROR_MESSAGE_TEMPLATES
    :type: ErrorMessages

    Default error message templates mapped by exception category.

.. autodata:: advanced_alchemy.repository.LoadSpec
    :no-value:

.. autodata:: advanced_alchemy.repository.ModelT
    :no-value:

.. autodata:: advanced_alchemy.repository.ModelOrRowMappingT
    :no-value:

.. autodata:: advanced_alchemy.repository.OrderingPair
    :no-value:
