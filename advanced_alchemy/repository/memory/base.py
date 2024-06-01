# ruff: noqa: PD011

from __future__ import annotations

import builtins
import contextlib
from collections import defaultdict
from inspect import isclass, signature
from typing import TYPE_CHECKING, Any, Generic, TypeVar, cast, overload

from sqlalchemy import ColumnElement, inspect
from sqlalchemy.orm import RelationshipProperty, Session, class_mapper, object_mapper

from advanced_alchemy.exceptions import AdvancedAlchemyError
from advanced_alchemy.repository.typing import _MISSING, MISSING, ModelT  # pyright: ignore[reportPrivateUsage]

if TYPE_CHECKING:
    from collections.abc import Iterable

    from sqlalchemy.orm import Mapper


CollectionT = TypeVar("CollectionT")
T = TypeVar("T")
AnyObject = TypeVar("AnyObject", bound="Any")


class _NotSet:
    pass


class InMemoryStore(Generic[T]):
    def __init__(self) -> None:
        self._store: dict[Any, T] = {}

    def _resolve_key(self, key: Any) -> Any:
        """Test different key representations

        Args:
            key: The key to test

        Raises:
            KeyError: Raised if key is not present

        Returns:
            The key representation that is present in the store
        """
        for key_ in (key, str(key)):
            if key_ in self._store:
                return key_
        raise KeyError

    def key(self, obj: T) -> Any:
        return hash(obj)

    def add(self, obj: T) -> T:
        if (key := self.key(obj)) not in self._store:
            self._store[key] = obj
            return obj
        raise KeyError

    def update(self, obj: T) -> T:
        key = self._resolve_key(self.key(obj))
        self._store[key] = obj
        return obj

    @overload
    def get(self, key: Any, default: type[_NotSet] = _NotSet) -> T: ...

    @overload
    def get(self, key: Any, default: AnyObject) -> T | AnyObject: ...

    def get(self, key: Any, default: AnyObject | type[_NotSet] = _NotSet) -> T | AnyObject:
        """Get the object identified by `key`, or return `default` if set or raise a `KeyError` otherwise

        Args:
            key: The key to test
            default: Value to return if key is not present. Defaults to _NotSet.

        Raises:
            KeyError: Raised if key is not present

        Returns:
            The object identified by key
        """
        try:
            key = self._resolve_key(key)
        except KeyError as error:
            if isclass(default) and not issubclass(default, _NotSet):  # pyright: ignore[reportUnnecessaryIsInstance]
                return cast(AnyObject, default)
            raise KeyError from error
        return self._store[key]

    def get_or_none(self, key: Any, default: Any = _NotSet) -> T | None:
        return self.get(key) if default is _NotSet else self.get(key, default)

    def remove(self, key: Any) -> T:
        return self._store.pop(self._resolve_key(key))

    def list(self) -> list[T]:
        return list(self._store.values())

    def remove_all(self) -> None:
        self._store = {}

    def __contains__(self, obj: T) -> bool:
        try:
            self._resolve_key(self.key(obj))
        except KeyError:
            return False
        else:
            return True

    def __bool__(self) -> bool:
        return bool(self._store)


class MultiStore(Generic[T]):
    def __init__(self, store_type: type[InMemoryStore[T]]) -> None:
        self.store_type = store_type
        self._store: defaultdict[Any, InMemoryStore[T]] = defaultdict(store_type)

    def add(self, identity: Any, obj: T) -> T:
        return self._store[identity].add(obj)

    def store(self, identity: Any) -> InMemoryStore[T]:
        return self._store[identity]

    def identity(self, obj: T) -> Any:
        return type(obj)

    def remove_all(self) -> None:
        self._store = defaultdict(self.store_type)


class SQLAlchemyInMemoryStore(InMemoryStore[ModelT]):
    id_attribute: str = "id"

    def _update_relationship(self, data: ModelT, ref: ModelT) -> None:
        """Set relationship data fields targeting ref class to ref.

        Example:
        ```python
            class Parent(Base):
                child = relationship("Child")

            class Child(Base):
                pass
        ```

        If data and ref are respectively a `Parent` and `Child` instances,
        then `data.child` will be set to `ref`

        Args:
            data: Model instance on which to update relationships
            ref: Target model instance to set on data relationships
        """
        ref_mapper = object_mapper(ref)
        for relationship in object_mapper(data).relationships:
            local = next(iter(relationship.local_columns))
            remote = next(iter(relationship.remote_side))
            if not local.key or not remote.key:
                msg = f"Cannot update relationship {relationship} for model {ref_mapper.class_}"
                raise AdvancedAlchemyError(msg)
            value = getattr(data, relationship.key)
            if not value and relationship.mapper.class_ is ref_mapper.class_:
                if relationship.uselist:
                    for elem in value:
                        if local_value := getattr(data, local.key):
                            setattr(elem, remote.key, local_value)
                else:
                    setattr(data, relationship.key, ref)

    def _update_fks(self, data: ModelT) -> None:
        """Update foreign key fields according to their corresponding relationships.

        This make sure that `data.child_id` == `data.child.id`
        or `data.children[0].parent_id` == `data.id`

        Args:
            data: Instance to be updated
        """
        ref_mapper = object_mapper(data)
        for relationship in ref_mapper.relationships:
            if value := getattr(data, relationship.key):
                local = next(iter(relationship.local_columns))
                remote = next(iter(relationship.remote_side))
                if not local.key or not remote.key:
                    msg = f"Cannot update relationship {relationship} for model {ref_mapper.class_}"
                    raise AdvancedAlchemyError(msg)
                if relationship.uselist:
                    for elem in value:
                        if local_value := getattr(data, local.key):
                            setattr(elem, remote.key, local_value)
                        self._update_relationship(elem, data)
                    # Remove duplicates added by orm when updating list items
                    if isinstance(value, list):
                        setattr(data, relationship.key, type(value)(set(value)))
                else:
                    if remote_value := getattr(value, remote.key):
                        setattr(data, local.key, remote_value)
                    self._update_relationship(value, data)

    def _set_defaults(self, data: ModelT) -> None:
        """Set fields with dynamic defaults.

        Args:
            data: Instance to be updated
        """
        for elem in object_mapper(data).c:
            default = getattr(elem, "default", MISSING)
            value = getattr(data, elem.key, MISSING)
            # If value is MISSING, it may be a declared_attr whose name can't be
            # determined from the column/relationship element returned
            if value is not MISSING and not value and not isinstance(default, _MISSING) and default is not None:
                if default.is_scalar:
                    default_value: Any = default.arg
                elif default.is_callable:
                    default_callable = default.arg.__func__ if isinstance(default.arg, staticmethod) else default.arg  # pyright: ignore[reportUnknownMemberType]
                    if (
                        # Eager test because inspect.signature() does not
                        # recognize builtins
                        hasattr(builtins, default_callable.__name__)
                        # If present, context contains information about the current
                        # statement and can be used to access values from other columns.
                        # As we can't reproduce such context in Pydantic, we don't want
                        # include a default_factory in that case.
                        or "context" not in signature(default_callable).parameters
                    ):
                        default_value = default.arg({})  # pyright: ignore[reportUnknownMemberType, reportCallIssue]
                    else:
                        continue
                else:
                    continue
                setattr(data, elem.key, default_value)

    def changed_attrs(self, data: ModelT) -> Iterable[str]:
        res: list[str] = []
        mapper = inspect(data)
        if mapper is None:
            msg = f"Cannot inspect {data.__class__} model"
            raise AdvancedAlchemyError(msg)
        attrs = class_mapper(data.__class__).column_attrs
        for attr in attrs:
            hist = getattr(mapper.attrs, attr.key).history
            if hist.has_changes():
                res.append(attr.key)
        return res

    def key(self, obj: ModelT) -> str:
        return str(getattr(obj, self.id_attribute))

    def add(self, obj: ModelT) -> ModelT:
        self._set_defaults(obj)
        self._update_fks(obj)
        return super().add(obj)

    def update(self, obj: ModelT) -> ModelT:
        existing = self.get(self.key(obj))
        for attr in self.changed_attrs(obj):
            setattr(existing, attr, getattr(obj, attr))
        self._update_fks(existing)
        return super().update(existing)


class SQLAlchemyMultiStore(MultiStore[ModelT]):
    def _new_instances(self, instance: ModelT) -> Iterable[ModelT]:
        session = Session()
        session.add(instance)
        relations = list(session.new)
        session.expunge_all()
        return relations

    def _set_relationships_for_fks(self, data: ModelT) -> None:
        """Set relationships matching newly added foreign keys on the instance.

        Example:
            ```python
                class Parent(Base):
                    id: Mapped[UUID]

                class Child(Base):
                    id: Mapped[UUID]
                    parent_id: Mapped[UUID] = mapped_column(ForeignKey("parent.id"))
                    parent: Mapped[Parent] = relationship(Parent)
            ```
            If `data` is a Child instance and `parent_id` is set, `parent` will be set
            to the matching Parent instance if found in the repository

        Args:
            data: The model to update
        """
        obj_mapper = object_mapper(data)
        mappers: dict[str, Mapper[Any]] = {}
        column_relationships: dict[ColumnElement[Any], RelationshipProperty[Any]] = {}

        for mapper in obj_mapper.registry.mappers:
            for table in mapper.tables:
                mappers[table.name] = mapper

        for relationship in obj_mapper.relationships:
            for column in relationship.local_columns:
                column_relationships[column] = relationship
        # sourcery skip: assign-if-exp
        if state := inspect(data):
            new_attrs: dict[str, Any] = state.dict
        else:
            new_attrs = {}

        for column in obj_mapper.columns:
            if column.key not in new_attrs or not column.foreign_keys:
                continue
            remote_mapper = mappers[next(iter(column.foreign_keys))._table_key()]  # noqa: SLF001 # pyright: ignore[reportPrivateUsage]
            try:
                obj = self.store(remote_mapper.class_).get(new_attrs.get(column.key, None))
            except KeyError:
                continue

            with contextlib.suppress(KeyError):
                setattr(data, column_relationships[column].key, obj)

    def add(self, identity: Any, obj: ModelT) -> ModelT:
        for relation in self._new_instances(obj):
            instance_type = self.identity(relation)
            self._set_relationships_for_fks(relation)
            if relation in self.store(instance_type):
                continue
            self.store(instance_type).add(relation)
        return obj
