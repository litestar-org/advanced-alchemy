====
base
====

.. py:module:: advanced_alchemy.base

Core Protocols & Attribute Mixins
---------------------------------

.. autoclass:: advanced_alchemy.base.ModelProtocol
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.base.BasicAttributes
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.base.CommonTableAttributes
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.base.AdvancedDeclarativeBase
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.base.SQLQuery
    :no-members:
    :no-inherited-members:
    :show-inheritance:

UUID Declarative Bases
----------------------

.. autoclass:: advanced_alchemy.base.UUIDBase
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.base.UUIDAuditBase
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.base.UUIDv6Base
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.base.UUIDv6AuditBase
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.base.UUIDv7Base
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.base.UUIDv7AuditBase
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.base.DefaultBase
    :no-members:
    :no-inherited-members:
    :show-inheritance:

Integer & NanoID Declarative Bases
----------------------------------

.. autoclass:: advanced_alchemy.base.BigIntBase
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.base.BigIntAuditBase
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.base.IdentityBase
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.base.IdentityAuditBase
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.base.NanoIDBase
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.base.NanoIDAuditBase
    :no-members:
    :no-inherited-members:
    :show-inheritance:

Registries, Utilities & Type Aliases
------------------------------------

.. autoclass:: advanced_alchemy.base.MetadataRegistry
    :members: get, set
    :no-inherited-members:
    :show-inheritance:

.. autofunction:: advanced_alchemy.base.create_registry

.. autofunction:: advanced_alchemy.base.merge_table_arguments

.. autofunction:: advanced_alchemy.base.model_to_dict

.. py:data:: orm_registry
    :type: sqlalchemy.orm.registry

    Default SQLAlchemy ORM registry instance.

.. py:data:: metadata_registry
    :type: MetadataRegistry

    Global registry mapping bind keys to SQLAlchemy ``MetaData`` instances.

.. py:data:: convention
    :type: dict[str, str]

    Default SQLAlchemy constraint naming convention dictionary.

.. py:data:: table_name_regexp
    :type: re.Pattern[str]

    Compiled regular expression used to derive snake_case table names.

.. py:data:: TableArgsType
    :type: typing.TypeAlias

    Type alias representing SQLAlchemy ``__table_args__`` declarations.

.. autodata:: advanced_alchemy.base.UUIDBaseT
    :no-value:

.. autodata:: advanced_alchemy.base.UUIDv6BaseT
    :no-value:

.. autodata:: advanced_alchemy.base.UUIDv7BaseT
    :no-value:

.. autodata:: advanced_alchemy.base.BigIntBaseT
    :no-value:

.. autodata:: advanced_alchemy.base.IdentityBaseT
    :no-value:

.. autodata:: advanced_alchemy.base.NanoIDBaseT
    :no-value:
