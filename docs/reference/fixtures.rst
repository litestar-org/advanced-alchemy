:tocdepth: 2

========
Fixtures
========

.. py:module:: advanced_alchemy.utils.fixtures

Streaming fixture loaders, batch iterators, sharded writers, and format aliases.

Fixture Formats & Readers
-------------------------

.. autodata:: advanced_alchemy.utils.fixtures.FixtureFormat

.. autodata:: advanced_alchemy.utils.fixtures.FixtureCompression

.. autofunction:: advanced_alchemy.utils.fixtures.open_fixture_sync

.. autofunction:: advanced_alchemy.utils.fixtures.open_fixture_async

Streaming, Writing & Legacy Alias
---------------------------------

.. autofunction:: advanced_alchemy.utils.fixtures.iter_fixture_sync

.. autofunction:: advanced_alchemy.utils.fixtures.iter_fixture_async

.. autofunction:: advanced_alchemy.utils.fixtures.write_fixture_sync

.. autofunction:: advanced_alchemy.utils.fixtures.write_fixture_async

.. autofunction:: advanced_alchemy.utils.fixtures.open_fixture
