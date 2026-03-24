=====================
Advanced Repository
=====================

This section covers advanced repository features including composite primary keys and row locking.

.. _composite-primary-keys:

Composite Primary Keys
----------------------

Advanced Alchemy supports models with composite primary keys. For these models, the repository methods accept several formats for identifying records.

**Tuple Format**

Pass primary key values as a tuple in the order they are defined on the model.

.. code-block:: python

    class UserRole(Base):
        __tablename__ = "user_role"
        user_id: int = Column(Integer, ForeignKey("user.id"), primary_key=True)
        role_id: int = Column(Integer, ForeignKey("role.id"), primary_key=True)

    # Values in column definition order
    role = await repository.get((user_id, role_id))

**Dict Format**

Pass primary key values as a dictionary with column names as keys. This is more explicit and avoids ordering issues.

.. code-block:: python

    role = await repository.get({"user_id": user_id, "role_id": role_id})

**Bulk Operations**

You can also use sequences of tuples or dicts for bulk operations like ``delete_many`` or ``get_many``.

.. code-block:: python

    roles = await repository.get_many([
        {"user_id": 1, "role_id": 5},
        {"user_id": 1, "role_id": 6},
    ])

Row Locking (FOR UPDATE)
------------------------

.. versionadded:: 1.9.0

The ``get_one`` and ``get_one_or_none`` methods support a ``with_for_update`` parameter, allowing you to emit a ``SELECT ... FOR UPDATE`` query for row-level locking.

.. code-block:: python

    # Lock the row for the duration of the transaction
    user = await repository.get_one(id=user_id, with_for_update=True)

    # You can also pass advanced options
    user = await repository.get_one(
        id=user_id,
        with_for_update={"nowait": True, "of": User.id}
    )

Custom DELETE WHERE
--------------------

For deleting multiple records matching a specific criteria:

.. code-block:: python

    await repository.delete_where(Post.published.is_(False))
