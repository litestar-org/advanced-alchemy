# ruff: noqa: PD011

from __future__ import annotations

import builtins
import contextlib
import re
from collections import abc, defaultdict
from inspect import isclass, signature
from random import sample
from typing import TYPE_CHECKING, Any, Generic, TypeVar, cast, overload
from unittest.mock import create_autospec

from sqlalchemy import ColumnElement, Dialect, Select, inspect
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import RelationshipProperty, Session, class_mapper, object_mapper

from advanced_alchemy.exceptions import AdvancedAlchemyError, ConflictError, NotFoundError, RepositoryError
from advanced_alchemy.filters import (
    BeforeAfter,
    CollectionFilter,
    FilterTypes,
    LimitOffset,
    NotInCollectionFilter,
    NotInSearchFilter,
    OnBeforeAfter,
    OrderBy,
    SearchFilter,
)
from advanced_alchemy.repository.abc import AbstractRepository, R
from advanced_alchemy.repository.typing import ModelT
from advanced_alchemy.utils.deprecation import deprecated

if TYPE_CHECKING:
    from collections.abc import Iterable
    from datetime import datetime

    from sqlalchemy.ext.asyncio import async_scoped_session
    from sqlalchemy.orm import Mapper


CollectionT = TypeVar("CollectionT")
T = TypeVar("T")
AnyObject = TypeVar("AnyObject", bound="Any")
DatabaseRegistry = dict[type["BaseInMemoryRepository[T]"], "MultiStore[T]"]

__all__ = ["SQLAlchemyAsyncMockRepository"]


class _NotSet:
    pass


class _MISSING:
    pass


MISSING = _MISSING()


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
    def get(self, key: Any, default: type[_NotSet] = _NotSet) -> T:
        ...

    @overload
    def get(self, key: Any, default: AnyObject) -> T | AnyObject:
        ...

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
            if isclass(default) and not issubclass(default, _NotSet):
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


class BaseInMemoryRepository(AbstractRepository[T]):
    """In memory repository."""

    __database__: MultiStore[T]
    __database_registry__: DatabaseRegistry[T] = {}

    match_fields: list[str] | str | None = None
    _exclude_kwargs: set[str] = {
        "statement",
        "session",
        "auto_expunge",
        "auto_refresh",
        "auto_commit",
        "attribute_names",
        "with_for_update",
        "force_basic_query_mode",
    }

    def __init__(self, **kwargs: Any) -> None:
        self.__filtered_store__: InMemoryStore[T] = self.__database__.store_type()

    def __init_subclass__(cls) -> None:
        cls.__database_registry__[cls] = cls.__database__

    @classmethod
    def __database_clear__(cls) -> None:
        for database in cls.__database_registry__.values():
            database.remove_all()

    @overload
    def __collection__(self) -> InMemoryStore[T]:
        ...

    @overload
    def __collection__(self, identity: type[AnyObject]) -> InMemoryStore[AnyObject]:
        ...

    def __collection__(self, identity: type[AnyObject] | None = None) -> InMemoryStore[AnyObject] | InMemoryStore[T]:
        if identity:
            return self.__database__.store(identity)
        return self.__filtered_store__ or self.__database__.store(self.model_type)

    @staticmethod
    def check_not_found(item_or_none: T | None) -> T:
        if item_or_none is None:
            msg = "No item found when one was expected"
            raise NotFoundError(msg)
        return item_or_none

    def fork(self, repository_type: type[R], **kwargs: Any) -> R:
        return cast(R, repository_type(**kwargs))

    def _exclude_unused_kwargs(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in kwargs.items() if key not in self._exclude_kwargs}

    def _apply_limit_offset_pagination(self, result: list[T], limit: int, offset: int) -> list[T]:
        return result[offset:limit]

    def _filter_in_collection(self, result: list[T], field_name: str, values: abc.Collection[Any]) -> list[T]:
        return [item for item in result if getattr(item, field_name) in values]

    def _filter_not_in_collection(self, result: list[T], field_name: str, values: abc.Collection[Any]) -> list[T]:
        if not values:
            return result
        return [item for item in result if getattr(item, field_name) not in values]

    def _filter_on_datetime_field(
        self,
        result: list[T],
        field_name: str,
        before: datetime | None = None,
        after: datetime | None = None,
        on_or_before: datetime | None = None,
        on_or_after: datetime | None = None,
    ) -> list[T]:
        result_: list[T] = []
        for item in result:
            attr: datetime = getattr(item, field_name)
            if before is not None and attr < before:
                result_.append(item)
            if after is not None and attr > after:
                result_.append(item)
            if on_or_before is not None and attr <= on_or_before:
                result_.append(item)
            if on_or_after is not None and attr >= on_or_after:
                result_.append(item)
        return result_

    def _filter_by_like(self, result: list[T], field_name: str, value: str, ignore_case: bool) -> list[T]:
        pattern = re.compile(rf".*{value}.*", re.IGNORECASE) if ignore_case else re.compile(rf".*{value}.*")
        return [
            item
            for item in result
            if isinstance(getattr(item, field_name), str) and pattern.match(getattr(item, field_name))
        ]

    def _filter_by_not_like(self, result: list[T], field_name: str, value: str, ignore_case: bool) -> list[T]:
        pattern = re.compile(rf".*{value}.*", re.IGNORECASE) if ignore_case else re.compile(rf".*{value}.*")
        return [
            item
            for item in result
            if isinstance(getattr(item, field_name), str) and not pattern.match(getattr(item, field_name))
        ]

    def _filter_result_by_kwargs(
        self,
        result: Iterable[T],
        /,
        kwargs: dict[Any, Any] | Iterable[tuple[Any, Any]],
    ) -> list[T]:
        kwargs_: dict[Any, Any] = kwargs if isinstance(kwargs, dict) else dict(*kwargs)
        kwargs_ = self._exclude_unused_kwargs(kwargs_)
        try:
            return [item for item in result if all(getattr(item, field) == value for field, value in kwargs_.items())]
        except AttributeError as error:
            raise RepositoryError from error

    def _order_by(self, result: list[T], field_name: str, sort_desc: bool = False) -> list[T]:
        return sorted(result, key=lambda item: getattr(item, field_name), reverse=sort_desc)

    def _apply_filters(
        self,
        result: list[T],
        *filters: FilterTypes | ColumnElement[bool],
        apply_pagination: bool = True,
    ) -> list[T]:
        for filter_ in filters:
            if isinstance(filter_, LimitOffset):
                if apply_pagination:
                    result = self._apply_limit_offset_pagination(result, filter_.limit, filter_.offset)
            elif isinstance(filter_, BeforeAfter):
                result = self._filter_on_datetime_field(
                    result,
                    field_name=filter_.field_name,
                    before=filter_.before,
                    after=filter_.after,
                )
            elif isinstance(filter_, OnBeforeAfter):
                result = self._filter_on_datetime_field(
                    result,
                    field_name=filter_.field_name,
                    on_or_before=filter_.on_or_before,
                    on_or_after=filter_.on_or_after,
                )

            elif isinstance(filter_, NotInCollectionFilter):
                if filter_.values is not None:
                    result = self._filter_not_in_collection(result, filter_.field_name, filter_.values)
            elif isinstance(filter_, CollectionFilter):
                if filter_.values is not None:
                    result = self._filter_in_collection(result, filter_.field_name, filter_.values)
            elif isinstance(filter_, OrderBy):
                result = self._order_by(
                    result,
                    filter_.field_name,
                    sort_desc=filter_.sort_order == "desc",
                )
            elif isinstance(filter_, SearchFilter):
                result = self._filter_by_like(
                    result,
                    filter_.field_name,
                    value=filter_.value,
                    ignore_case=bool(filter_.ignore_case),
                )
            elif isinstance(filter_, NotInSearchFilter):
                result = self._filter_by_not_like(
                    result,
                    filter_.field_name,
                    value=filter_.value,
                    ignore_case=bool(filter_.ignore_case),
                )
            elif not isinstance(filter_, ColumnElement):
                msg = f"Unexpected filter: {filter_}"  # type: ignore[unreachable]
                raise RepositoryError(msg)
        return result

    def _get_match_fields(
        self,
        match_fields: list[str] | str | None = None,
        id_attribute: str | None = None,
    ) -> list[str] | None:
        id_attribute = id_attribute or self.id_attribute
        match_fields = match_fields or self.match_fields
        if isinstance(match_fields, str):
            match_fields = [match_fields]
        return match_fields

    async def _list_and_count_basic(self, *filters: FilterTypes, **kwargs: Any) -> tuple[list[T], int]:
        result = await self.list(*filters, **kwargs)
        return result, len(result)

    async def _list_and_count_window(self, *filters: FilterTypes, **kwargs: Any) -> tuple[list[T], int]:
        return await self._list_and_count_basic(*filters, **kwargs)

    def _find_or_raise_not_found(self, id_: Any) -> T:
        return self.check_not_found(self.__collection__().get_or_none(id_))

    def _find_one_or_raise_conflict(self, result: list[T]) -> T:
        if not result:
            msg = "No item found when one was expected"
            raise ConflictError(msg)
        if len(result) > 1:
            msg = "Multiple objects when one was expected"
            raise ConflictError(msg)
        return result[0]

    @classmethod
    async def check_health(cls, session: AsyncSession | async_scoped_session[AsyncSession]) -> bool:  # noqa: ARG003
        return True

    async def get(self, item_id: Any, **_: Any) -> T:
        return self._find_or_raise_not_found(item_id)

    async def get_one(self, **kwargs: Any) -> T:
        return self.check_not_found(await self.get_one_or_none(**kwargs))

    async def get_one_or_none(self, **kwargs: Any) -> T | None:
        result = self._filter_result_by_kwargs(self.__collection__().list(), kwargs)
        if len(result) > 1:
            msg = "Multiple objects when one was expected"
            raise ConflictError(msg)
        return result[0] if result else None

    @deprecated(version="0.3.5", alternative="SQLAlchemyAsyncRepository.get_or_upsert", kind="method")
    async def get_or_create(
        self,
        match_fields: list[str] | str | None = None,
        upsert: bool = True,
        **kwargs: Any,
    ) -> tuple[T, bool]:
        return await self.get_or_upsert(match_fields, upsert, **kwargs)

    async def get_or_upsert(
        self,
        match_fields: list[str] | str | None = None,
        upsert: bool = True,
        **kwargs: Any,
    ) -> tuple[T, bool]:
        kwargs_ = self._exclude_unused_kwargs(kwargs)
        if match_fields := self._get_match_fields(match_fields=match_fields):
            match_filter = {
                field_name: kwargs_.get(field_name, None)
                for field_name in match_fields
                if kwargs_.get(field_name, None) is not None
            }
        else:
            match_filter = kwargs_
        existing = await self.get_one_or_none(**match_filter)
        if not existing:
            return (await self.add(self.model_type(**kwargs_)), True)
        if upsert:
            for field_name, new_field_value in kwargs_.items():
                field = getattr(existing, field_name, None)
                if field and field != new_field_value:
                    setattr(existing, field_name, new_field_value)
            existing = await self.update(existing)
        return existing, False

    async def get_and_update(self, match_fields: list[str] | str | None = None, **kwargs: Any) -> tuple[T, bool]:
        kwargs_ = self._exclude_unused_kwargs(kwargs)
        if match_fields := self._get_match_fields(match_fields=match_fields):
            match_filter = {
                field_name: kwargs_.get(field_name, None)
                for field_name in match_fields
                if kwargs_.get(field_name, None) is not None
            }
        else:
            match_filter = kwargs_
        existing = await self.get_one(**match_filter)
        updated = False
        for field_name, new_field_value in kwargs_.items():
            field = getattr(existing, field_name, None)
            if field and field != new_field_value:
                updated = True
                setattr(existing, field_name, new_field_value)
        existing = await self.update(existing)
        return existing, updated

    async def exists(self, *filters: FilterTypes, **kwargs: Any) -> bool:
        existing = await self.count(*filters, **kwargs)
        return existing > 0

    async def count(self, *filters: FilterTypes, **kwargs: Any) -> int:
        result = self._apply_filters(self.__collection__().list(), *filters)
        return len(self._filter_result_by_kwargs(result, kwargs))

    async def add(self, data: T, **_: Any) -> T:
        try:
            self.__database__.add(self.model_type, data)
        except KeyError as exc:
            msg = "Item already exist in collection"
            raise ConflictError(msg) from exc
        return data

    async def add_many(self, data: list[T], **_: Any) -> list[T]:
        for obj in data:
            await self.add(obj)
        return data

    async def update(self, data: T, **_: Any) -> T:
        self._find_or_raise_not_found(self.__collection__().key(data))
        self.__collection__().update(data)
        return data

    async def update_many(self, data: list[T], **_: Any) -> list[T]:
        for obj in data:
            if obj in self.__collection__():
                self.__collection__().update(obj)
        return data

    async def delete(self, item_id: Any, **_: Any) -> T:
        try:
            return self._find_or_raise_not_found(item_id)
        finally:
            self.__collection__().remove(item_id)

    async def delete_many(self, item_ids: list[Any], **_: Any) -> list[T]:
        deleted: list[T] = []
        for id_ in item_ids:
            if obj := self.__collection__().get_or_none(id_):
                deleted.append(obj)
                self.__collection__().remove(id_)
        return deleted

    async def upsert(self, data: T, **_: Any) -> T:
        if data in self.__collection__():
            return await self.update(data)
        return await self.add(data)

    async def upsert_many(self, data: list[T], **_: Any) -> list[T]:
        return [await self.upsert(item) for item in data]

    async def list_and_count(self, *filters: FilterTypes, **kwargs: Any) -> tuple[list[T], int]:
        return await self._list_and_count_basic(*filters, **kwargs)

    async def first(self) -> T | None:
        collection = self.__collection__().list()
        return collection[0] if collection else None

    async def random(self, size: int = 1, **_: Any) -> list[T]:
        return sample(self.__collection__().list(), size)

    def filter_collection_by_kwargs(self, collection: CollectionT, /, **kwargs: Any) -> CollectionT:
        for value in self._filter_result_by_kwargs(cast(list[T], collection), kwargs):
            self.__filtered_store__.add(value)
        return collection

    async def list(self, *filters: FilterTypes, **kwargs: Any) -> list[T]:
        result = self.__collection__().list()
        result = self._apply_filters(result, *filters)
        return self._filter_result_by_kwargs(result, kwargs)


class AsyncInMemoryRepository(BaseInMemoryRepository[T]):
    """Async in memory repository."""

    __database__: MultiStore[T] = MultiStore(InMemoryStore)


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
                    default_callable = default.arg.__func__ if isinstance(default.arg, staticmethod) else default.arg
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
                        default_value = default.arg({})
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

        if state := inspect(data):
            new_attrs: dict[str, Any] = state.dict
        else:
            new_attrs = {}

        for column in obj_mapper.columns:
            if column.key not in new_attrs or not column.foreign_keys:
                continue
            remote_mapper = mappers[next(iter(column.foreign_keys))._table_key()]  # noqa: SLF001
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


class SQLAlchemyAsyncMockRepository(AsyncInMemoryRepository[ModelT]):
    """In memory repository storing SQLAlchemy ORM mapper objects."""

    __database__: SQLAlchemyMultiStore[ModelT] = SQLAlchemyMultiStore(SQLAlchemyInMemoryStore)

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.session = create_autospec(AsyncSession, instance=True)
        self.session.bind = create_autospec(AsyncEngine, instance=True)
        self.statement: Select[Any] = create_autospec(Select, instance=True)
        self._dialect: Dialect = create_autospec(Dialect, instance=True)
        self._dialect.name = "mock"
