"""Utilities for working with SQLAlchemy polymorphic entities in repositories and services."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Optional, Union

from sqlalchemy import inspect as sa_inspect
from sqlalchemy.exc import NoInspectionAvailable
from sqlalchemy.orm import class_mapper

if TYPE_CHECKING:
    from sqlalchemy.orm import Mapper
    from sqlalchemy.orm.util import AliasedInsp

__all__ = (
    "PolymorphicEntityConfig",
    "get_base_class_mapper",
    "get_base_model_class",
    "get_model_display_name",
    "get_polymorphic_type_map",
    "get_table_name",
    "is_aliased_class",
    "resolve_polymorphic_subclass",
    "validate_polymorphic_entity",
)


def is_aliased_class(model: Any) -> bool:
    """Return True if *model* is a SQLAlchemy ``AliasedClass`` (e.g. from ``with_polymorphic``).

    Args:
        model: A SQLAlchemy mapped class or aliased entity to inspect.

    Returns:
        bool: True when *model* was produced by ``with_polymorphic()`` or ``aliased()``.
    """
    try:
        from sqlalchemy.orm.util import AliasedInsp  # noqa: PLC0415

        insp = sa_inspect(model, raiseerr=False)
        return isinstance(insp, AliasedInsp)
    except (NoInspectionAvailable, Exception):  # noqa: BLE001
        return False


def _get_aliased_insp(model: Any) -> "Optional[AliasedInsp]":
    """Return the ``AliasedInsp`` for *model*, or None if it is not aliased."""
    try:
        from sqlalchemy.orm.util import AliasedInsp  # noqa: PLC0415

        insp = sa_inspect(model, raiseerr=False)
        if isinstance(insp, AliasedInsp):
            return insp
    except (NoInspectionAvailable, Exception):  # noqa: BLE001
        pass
    return None


def get_base_model_class(model: Any) -> Any:
    """Return the concrete mapped class for *model*.

    When *model* is a plain mapped class the same object is returned.  When it
    is an ``AliasedClass`` (e.g. the result of ``with_polymorphic()``), the
    underlying base class obtained from ``AliasedInsp.mapper.class_`` is
    returned.  This is the class that should be used for DML statements
    (``delete()``, ``update()``) and for instantiating new ORM objects.

    Args:
        model: A mapped class or aliased entity.

    Returns:
        The concrete mapped class.
    """
    aliased_insp = _get_aliased_insp(model)
    if aliased_insp is not None:
        return aliased_insp.mapper.class_
    return model


def get_model_display_name(model: Any) -> str:
    """Return a human-readable name for *model* suitable for error messages.

    For plain mapped classes this is ``model.__name__``.  For aliased entities
    it falls back to the underlying mapper's class name.

    Args:
        model: A mapped class or aliased entity.

    Returns:
        str: A display name for the model.
    """
    aliased_insp = _get_aliased_insp(model)
    if aliased_insp is not None:
        return aliased_insp.mapper.class_.__name__
    return getattr(model, "__name__", repr(model))


def get_table_name(model: Any) -> Optional[str]:
    """Return the ``__tablename__`` for *model*, or ``None`` when unavailable.

    For aliased entities produced by ``with_polymorphic()`` the table name of
    the base mapper's mapped table is returned.

    Args:
        model: A mapped class or aliased entity.

    Returns:
        Optional[str]: The table name, or None.
    """
    aliased_insp = _get_aliased_insp(model)
    if aliased_insp is not None:
        mapped_table = aliased_insp.mapper.mapped_table
        return getattr(mapped_table, "name", None) or getattr(mapped_table, "key", None)
    return getattr(model, "__tablename__", None)


def resolve_polymorphic_subclass(model: Any, data: dict[str, Any]) -> Any:
    """Return the correct concrete subclass to instantiate for *data*.

    When *model* is an ``AliasedClass`` from ``with_polymorphic()`` and the
    underlying mapper has a polymorphic discriminator, the value of that
    discriminator column in *data* is used to locate the matching subclass in
    the mapper hierarchy.  If no match is found, or if *model* is not
    polymorphic, the base mapped class is returned.

    Args:
        model: A mapped class or ``AliasedClass``.
        data: A dict of column/attribute values for the record to be created.

    Returns:
        The concrete mapped class to instantiate.
    """
    aliased_insp = _get_aliased_insp(model)
    if aliased_insp is None:
        return model

    mapper: "Mapper[Any]" = aliased_insp.mapper
    discriminator_col = mapper.polymorphic_on
    if discriminator_col is None:
        return mapper.class_

    disc_key: Optional[str] = getattr(discriminator_col, "key", None)
    if disc_key is None:
        disc_key = getattr(discriminator_col, "name", None)
    if disc_key is None:
        return mapper.class_

    disc_value = data.get(disc_key)
    if disc_value is None:
        return mapper.class_

    for sub_mapper in mapper.self_and_descendants:
        if sub_mapper.polymorphic_identity == disc_value:
            return sub_mapper.class_

    return mapper.class_


@dataclass
class PolymorphicEntityConfig:
    """Configuration object for a polymorphic entity used with repositories and services.

    This captures the information needed to work with a ``with_polymorphic()``
    aliased entity, including the base class, the discriminator column name, and
    a pre-built map from discriminator value to concrete subclass.

    Attributes:
        entity: The ``AliasedClass`` returned by ``with_polymorphic()``.
        base_class: The base mapped class (e.g. ``Alert``).
        discriminator_attr: The attribute name of the polymorphic discriminator
            column on *base_class*, or ``None`` when not configured.
        subclass_map: Mapping from discriminator value to concrete subclass.
            Empty when the mapper has no polymorphic discriminator.

    Example::

        from sqlalchemy.orm import with_polymorphic
        from advanced_alchemy.repository._polymorphic import PolymorphicEntityConfig

        AllAlerts = with_polymorphic(Alert, (UnexpectedAlert, ExpectedAlert))
        config = PolymorphicEntityConfig.from_entity(AllAlerts)
        # config.base_class is Alert
        # config.subclass_map == {"unexpected": UnexpectedAlert, "expected": ExpectedAlert}
    """

    entity: Any
    base_class: Any
    discriminator_attr: Optional[str] = None
    subclass_map: dict[Any, Any] = field(default_factory=dict)

    @classmethod
    def from_entity(cls, entity: Any) -> "PolymorphicEntityConfig":
        """Build a :class:`PolymorphicEntityConfig` from a ``with_polymorphic`` entity.

        Args:
            entity: The ``AliasedClass`` produced by ``with_polymorphic()``.

        Returns:
            PolymorphicEntityConfig: Populated configuration object.

        Raises:
            ValueError: If *entity* is not an aliased class.
        """
        aliased_insp = _get_aliased_insp(entity)
        if aliased_insp is None:
            msg = f"{entity!r} is not an AliasedClass; use with_polymorphic() to create one."
            raise ValueError(msg)

        mapper: "Mapper[Any]" = aliased_insp.mapper
        base_class = mapper.class_

        disc_attr: Optional[str] = None
        subclass_map: dict[Any, Any] = {}
        discriminator_col = mapper.polymorphic_on
        if discriminator_col is not None:
            disc_attr = getattr(discriminator_col, "key", None) or getattr(discriminator_col, "name", None)
            for sub_mapper in mapper.self_and_descendants:
                identity = sub_mapper.polymorphic_identity
                if identity is not None:
                    subclass_map[identity] = sub_mapper.class_

        return cls(
            entity=entity,
            base_class=base_class,
            discriminator_attr=disc_attr,
            subclass_map=subclass_map,
        )

    def resolve_class_for(self, data: dict[str, Any]) -> Any:
        """Return the concrete class to instantiate for *data*.

        Uses the discriminator attribute and :attr:`subclass_map` to pick the
        right subclass.  Falls back to :attr:`base_class` when no match is
        found.

        Args:
            data: Column/attribute values for the record to be created.

        Returns:
            The concrete mapped class to use.
        """
        if not self.discriminator_attr or not self.subclass_map:
            return self.base_class
        disc_value = data.get(self.discriminator_attr)
        return self.subclass_map.get(disc_value, self.base_class)


def get_polymorphic_type_map(model: Any) -> dict[Any, Any]:
    """Return a mapping of polymorphic identity → concrete subclass for *model*.

    When *model* has no polymorphic discriminator or is not a mapped class the
    returned dict is empty.  When *model* is an ``AliasedClass`` the mapping is
    built from its base mapper's :attr:`self_and_descendants` chain; when it is
    a plain mapped class the same chain is used directly.

    This is the same mapping that :meth:`PolymorphicEntityConfig.from_entity`
    builds internally; use this as a lightweight alternative when you do not
    need the full config object.

    Args:
        model: A mapped class or ``AliasedClass``.

    Returns:
        dict: ``{polymorphic_identity_value: concrete_class, ...}``.  Empty
        when no discriminator is configured.

    Examples::

        from sqlalchemy.orm import with_polymorphic
        from advanced_alchemy.repository._polymorphic import get_polymorphic_type_map

        AllAlerts = with_polymorphic(Alert, (UnexpectedAlert, ExpectedAlert))
        type_map = get_polymorphic_type_map(AllAlerts)
        # {"unexpected": UnexpectedAlert, "expected": ExpectedAlert}
    """
    aliased_insp = _get_aliased_insp(model)
    if aliased_insp is not None:
        mapper: "Mapper[Any]" = aliased_insp.mapper
    else:
        try:
            insp = sa_inspect(model, raiseerr=False)
            if insp is None:
                return {}
            mapper = insp
        except (NoInspectionAvailable, Exception):  # noqa: BLE001
            return {}

    disc_col = getattr(mapper, "polymorphic_on", None)
    if disc_col is None:
        return {}

    result: dict[Any, Any] = {}
    for sub_mapper in mapper.self_and_descendants:
        identity = sub_mapper.polymorphic_identity
        if identity is not None:
            result[identity] = sub_mapper.class_
    return result


def validate_polymorphic_entity(model: Any) -> None:
    """Raise :exc:`TypeError` if *model* cannot be used as a polymorphic entity.

    A valid polymorphic entity is either a plain SQLAlchemy mapped class **or**
    an ``AliasedClass`` produced by ``with_polymorphic()``.  This function is a
    lightweight guard that can be called in ``__init_subclass__`` or ``__set_name__``
    hooks of a repository class to provide an early, actionable error message instead
    of a cryptic ``AttributeError`` deep in the ORM stack.

    Args:
        model: The object to validate.

    Raises:
        TypeError: When *model* is neither a mapped class nor an ``AliasedClass``.

    Examples::

        from advanced_alchemy.repository._polymorphic import validate_polymorphic_entity

        # Raises TypeError immediately, not when the first query runs:
        validate_polymorphic_entity("not_a_model")
    """
    if model is None:
        msg = "model_type must not be None; provide a mapped class or with_polymorphic() entity."
        raise TypeError(msg)

    if is_aliased_class(model):
        return

    try:
        insp = sa_inspect(model, raiseerr=True)
    except NoInspectionAvailable as exc:
        msg = (
            f"{model!r} is not a SQLAlchemy mapped class or with_polymorphic() entity. "
            "Pass a class decorated with @mapped_column / declarative_base, or the result "
            "of with_polymorphic()."
        )
        raise TypeError(msg) from exc

    if not hasattr(insp, "mapper"):
        msg = (
            f"{model!r} resolved to a {type(insp).__name__!r} inspection object, "
            "but a Mapper was expected.  Pass a mapped class, not an instance."
        )
        raise TypeError(msg)


def get_base_class_mapper(model: Any) -> Any:
    """Return a SQLAlchemy mapper for the base class of *model*.

    Handles both plain mapped classes (``class_mapper(model)``) and
    ``AliasedClass`` entities (``aliased_insp.mapper``).

    Args:
        model: A mapped class or aliased entity.

    Returns:
        The SQLAlchemy mapper instance.
    """
    aliased_insp = _get_aliased_insp(model)
    if aliased_insp is not None:
        return aliased_insp.mapper
    return class_mapper(model)
