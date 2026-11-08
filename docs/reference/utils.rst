=====
utils
=====

.. py:module:: advanced_alchemy.utils

Dataclass & Sentinel Utilities
------------------------------

.. py:module:: advanced_alchemy.utils.dataclass
    :no-typesetting:

.. autoclass:: advanced_alchemy.utils.dataclass.DataclassProtocol
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.utils.dataclass.Empty
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autodata:: advanced_alchemy.utils.dataclass.EmptyType
    :no-value:

.. autofunction:: advanced_alchemy.utils.dataclass.extract_dataclass_fields

.. autofunction:: advanced_alchemy.utils.dataclass.extract_dataclass_items

.. autofunction:: advanced_alchemy.utils.dataclass.is_dataclass_class

.. autofunction:: advanced_alchemy.utils.dataclass.is_dataclass_instance

.. autofunction:: advanced_alchemy.utils.dataclass.simple_asdict

.. py:module:: advanced_alchemy.utils.serialization
    :no-typesetting:

.. autofunction:: advanced_alchemy.utils.serialization.decode_json

.. autofunction:: advanced_alchemy.utils.serialization.encode_json

Dependency & Filter Helpers
---------------------------

.. py:module:: advanced_alchemy.utils.dependencies
    :no-typesetting:

.. autoclass:: advanced_alchemy.utils.dependencies.FilterConfig
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.utils.dependencies.ChoiceField
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.utils.dependencies.FieldNameType
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.utils.dependencies.DependencyCache
    :members: add_dependencies, get_dependencies
    :no-inherited-members:
    :show-inheritance:

.. autofunction:: advanced_alchemy.utils.dependencies.resolve_filter_aliases

.. autofunction:: advanced_alchemy.utils.dependencies.normalize_field_name_types

.. autofunction:: advanced_alchemy.utils.dependencies.normalize_choice_field_types

.. autofunction:: advanced_alchemy.utils.dependencies.normalize_sort_field

.. autofunction:: advanced_alchemy.utils.dependencies.make_hashable

.. autofunction:: advanced_alchemy.utils.dependencies.filter_cache_key

Async Portals & Sync Execution Tools
------------------------------------

.. py:module:: advanced_alchemy.utils.portals
    :no-typesetting:

.. autoclass:: advanced_alchemy.utils.portals.Portal
    :members: call
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.utils.portals.PortalProvider
    :members: start, stop, portal
    :no-inherited-members:
    :show-inheritance:

.. autoclass:: advanced_alchemy.utils.portals.PortalProviderSingleton
    :no-members:
    :no-inherited-members:
    :show-inheritance:

.. py:module:: advanced_alchemy.utils.sync_tools
    :no-typesetting:

.. autoclass:: advanced_alchemy.utils.sync_tools.CapacityLimiter
    :members: total_tokens
    :no-inherited-members:
    :show-inheritance:

.. autofunction:: advanced_alchemy.utils.sync_tools.run_

.. autofunction:: advanced_alchemy.utils.sync_tools.async_

.. autofunction:: advanced_alchemy.utils.sync_tools.await_

.. autofunction:: advanced_alchemy.utils.sync_tools.ensure_async_

.. autofunction:: advanced_alchemy.utils.sync_tools.with_ensure_async_

Module Loading, Fixtures, Text & Deprecation
--------------------------------------------

.. py:module:: advanced_alchemy.utils.module_loader
    :no-typesetting:

.. autofunction:: advanced_alchemy.utils.module_loader.import_string

.. autofunction:: advanced_alchemy.utils.module_loader.module_to_os_path

.. py:module:: advanced_alchemy.utils.fixtures
    :no-typesetting:

.. autofunction:: advanced_alchemy.utils.fixtures.open_fixture

.. autofunction:: advanced_alchemy.utils.fixtures.open_fixture_async

.. py:module:: advanced_alchemy.utils.text
    :no-typesetting:

.. autofunction:: advanced_alchemy.utils.text.slugify

.. autofunction:: advanced_alchemy.utils.text.check_email

.. py:module:: advanced_alchemy.utils.deprecation
    :no-typesetting:

.. autofunction:: advanced_alchemy.utils.deprecation.deprecated

.. autofunction:: advanced_alchemy.utils.deprecation.warn_deprecation
