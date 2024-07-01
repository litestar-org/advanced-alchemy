from __future__ import annotations

import random
import re
import string
from typing import TYPE_CHECKING, Any, Iterable, List, cast, overload
from unittest.mock import create_autospec

from sqlalchemy import (
    ColumnElement,
    Dialect,
    Select,
    StatementLambdaElement,
)
from sqlalchemy.orm import InstrumentedAttribute

from advanced_alchemy.exceptions import IntegrityError, NotFoundError, RepositoryError
from advanced_alchemy.filters import (
    BeforeAfter,
    CollectionFilter,
    LimitOffset,
    NotInCollectionFilter,
    NotInSearchFilter,
    OnBeforeAfter,
    OrderBy,
    SearchFilter,
    StatementFilter,
)
from advanced_alchemy.repository._async import SQLAlchemyAsyncRepositoryProtocol, SQLAlchemyAsyncSlugRepositoryProtocol
from advanced_alchemy.repository.memory.base import (
    AnyObject,
    CollectionT,
    InMemoryStore,
    SQLAlchemyInMemoryStore,
    SQLAlchemyMultiStore,
)
from advanced_alchemy.repository.typing import MISSING, ModelT, OrderingPair
from advanced_alchemy.utils.text import slugify

if TYPE_CHECKING:
    from collections import abc
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.ext.asyncio.scoping import async_scoped_session
    from sqlalchemy.orm.strategy_options import _AbstractLoad  # pyright: ignore[reportPrivateUsage]

    from advanced_alchemy.repository._util import (
        LoadSpec,
    )


class SQLAlchemyAsyncMockRepository(SQLAlchemyAsyncRepositoryProtocol[ModelT]):
    """In memory repository."""

    __database__: SQLAlchemyMultiStore[ModelT] = SQLAlchemyMultiStore(SQLAlchemyInMemoryStore)
    __database_registry__: dict[type[SQLAlchemyAsyncMockRepository[ModelT]], SQLAlchemyMultiStore[ModelT]] = {}

    model_type: type[ModelT]
    id_attribute: Any = "id"
    match_fields: list[str] | str | None = None
    _uniquify_results: bool = False
    _exclude_kwargs: set[str] = {
        "statement",
        "session",
        "auto_expunge",
        "auto_refresh",
        "auto_commit",
        "attribute_names",
        "with_for_update",
        "force_basic_query_mode",
        "order_by",
        "load",
        "execution_options",
    }

    def __init__(
        self,
        *,
        statement: Select[tuple[ModelT]] | StatementLambdaElement | None = None,
        session: AsyncSession | async_scoped_session[AsyncSession],
        auto_expunge: bool = False,
        auto_refresh: bool = True,
        auto_commit: bool = False,
        order_by: list[OrderingPair] | OrderingPair | None = None,
        load: LoadSpec | None = None,
        execution_options: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        self.session = session
        self.statement = create_autospec("Select[tuple[ModelT]]", instance=True)
        self.auto_expunge = auto_expunge
        self.auto_refresh = auto_refresh
        self.auto_commit = auto_commit
        self.order_by = order_by
        self._dialect: Dialect = create_autospec(Dialect, instance=True)
        self._dialect.name = "mock"
        self.__filtered_store__: InMemoryStore[ModelT] = self.__database__.store_type()
        self._default_options: Any = []
        self._default_execution_options: Any = {}
        self._loader_options: Any = []
        self._loader_options_have_wildcards = False

    def __init_subclass__(cls) -> None:
        cls.__database_registry__[cls] = cls.__database__  # pyright: ignore[reportGeneralTypeIssues]

    @classmethod
    def __database_add__(cls, identity: Any, data: ModelT) -> ModelT:
        return cast("ModelT", cls.__database__.add(identity, data))  # pyright: ignore[reportUnnecessaryCast,reportGeneralTypeIssues]

    @classmethod
    def __database_clear__(cls) -> None:
        for database in cls.__database_registry__.values():  # pyright: ignore[reportGeneralTypeIssues]
            database.remove_all()

    @overload
    def __collection__(self) -> InMemoryStore[ModelT]: ...

    @overload
    def __collection__(self, identity: type[AnyObject]) -> InMemoryStore[AnyObject]: ...

    def __collection__(
        self,
        identity: type[AnyObject] | None = None,
    ) -> InMemoryStore[AnyObject] | InMemoryStore[ModelT]:
        if identity:
            return self.__database__.store(identity)
        return self.__filtered_store__ or self.__database__.store(self.model_type)

    @staticmethod
    def check_not_found(item_or_none: ModelT | None) -> ModelT:
        if item_or_none is None:
            msg = "No item found when one was expected"
            raise NotFoundError(msg)
        return item_or_none

    @classmethod
    def get_id_attribute_value(
        cls,
        item: ModelT | type[ModelT],
        id_attribute: str | InstrumentedAttribute[Any] | None = None,
    ) -> Any:
        """Get value of attribute named as :attr:`id_attribute <AbstractAsyncRepository.id_attribute>` on ``item``.

        Args:
            item: Anything that should have an attribute named as :attr:`id_attribute <AbstractAsyncRepository.id_attribute>` value.
            id_attribute: Allows customization of the unique identifier to use for model fetching.
                Defaults to `None`, but can reference any surrogate or candidate key for the table.

        Returns:
            The value of attribute on ``item`` named as :attr:`id_attribute <AbstractAsyncRepository.id_attribute>`.
        """
        if isinstance(id_attribute, InstrumentedAttribute):
            id_attribute = id_attribute.key
        return getattr(item, id_attribute if id_attribute is not None else cls.id_attribute)

    @classmethod
    def set_id_attribute_value(
        cls,
        item_id: Any,
        item: ModelT,
        id_attribute: str | InstrumentedAttribute[Any] | None = None,
    ) -> ModelT:
        """Return the ``item`` after the ID is set to the appropriate attribute.

        Args:
            item_id: Value of ID to be set on instance
            item: Anything that should have an attribute named as :attr:`id_attribute <AbstractAsyncRepository.id_attribute>` value.
            id_attribute: Allows customization of the unique identifier to use for model fetching.
                Defaults to `None`, but can reference any surrogate or candidate key for the table.

        Returns:
            Item with ``item_id`` set to :attr:`id_attribute <AbstractAsyncRepository.id_attribute>`
        """
        if isinstance(id_attribute, InstrumentedAttribute):
            id_attribute = id_attribute.key
        setattr(item, id_attribute if id_attribute is not None else cls.id_attribute, item_id)
        return item

    def _exclude_unused_kwargs(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in kwargs.items() if key not in self._exclude_kwargs}

    def _apply_limit_offset_pagination(self, result: list[ModelT], limit: int, offset: int) -> list[ModelT]:
        return result[offset:limit]

    def _filter_in_collection(
        self,
        result: list[ModelT],
        field_name: str,
        values: abc.Collection[Any],
    ) -> list[ModelT]:
        return [item for item in result if getattr(item, field_name) in values]

    def _filter_not_in_collection(
        self,
        result: list[ModelT],
        field_name: str,
        values: abc.Collection[Any],
    ) -> list[ModelT]:
        if not values:
            return result
        return [item for item in result if getattr(item, field_name) not in values]

    def _filter_on_datetime_field(
        self,
        result: list[ModelT],
        field_name: str,
        before: datetime | None = None,
        after: datetime | None = None,
        on_or_before: datetime | None = None,
        on_or_after: datetime | None = None,
    ) -> list[ModelT]:
        result_: list[ModelT] = []
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

    def _filter_by_like(
        self,
        result: list[ModelT],
        field_name: str | set[str],
        value: str,
        ignore_case: bool,
    ) -> list[ModelT]:
        pattern = re.compile(rf".*{value}.*", re.IGNORECASE) if ignore_case else re.compile(rf".*{value}.*")
        fields = {field_name} if isinstance(field_name, str) else field_name
        items: list[ModelT] = []
        for field in fields:
            items.extend(
                [
                    item
                    for item in result
                    if isinstance(getattr(item, field), str) and pattern.match(getattr(item, field))
                ],
            )
        return list(set(items))

    def _filter_by_not_like(
        self,
        result: list[ModelT],
        field_name: str | set[str],
        value: str,
        ignore_case: bool,
    ) -> list[ModelT]:
        pattern = re.compile(rf".*{value}.*", re.IGNORECASE) if ignore_case else re.compile(rf".*{value}.*")
        fields = {field_name} if isinstance(field_name, str) else field_name
        items: list[ModelT] = []
        for field in fields:
            items.extend(
                [
                    item
                    for item in result
                    if isinstance(getattr(item, field), str) and pattern.match(getattr(item, field))
                ],
            )
        return list(set(result).difference(set(items)))

    def _filter_result_by_kwargs(
        self,
        result: Iterable[ModelT],
        /,
        kwargs: dict[Any, Any] | Iterable[tuple[Any, Any]],
    ) -> list[ModelT]:
        kwargs_: dict[Any, Any] = kwargs if isinstance(kwargs, dict) else dict(*kwargs)
        kwargs_ = self._exclude_unused_kwargs(kwargs_)
        try:
            return [item for item in result if all(getattr(item, field) == value for field, value in kwargs_.items())]
        except AttributeError as error:
            raise RepositoryError from error

    def _order_by(self, result: list[ModelT], field_name: str, sort_desc: bool = False) -> list[ModelT]:
        return sorted(result, key=lambda item: getattr(item, field_name), reverse=sort_desc)

    def _apply_filters(
        self,
        result: list[ModelT],
        *filters: StatementFilter | ColumnElement[bool],
        apply_pagination: bool = True,
    ) -> list[ModelT]:
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
                if filter_.values is not None:  # pyright: ignore  # noqa: PGH003
                    result = self._filter_not_in_collection(result, filter_.field_name, filter_.values)  # pyright: ignore  # noqa: PGH003
            elif isinstance(filter_, CollectionFilter):
                if filter_.values is not None:  # pyright: ignore  # noqa: PGH003
                    result = self._filter_in_collection(result, filter_.field_name, filter_.values)  # pyright: ignore  # noqa: PGH003
            elif isinstance(filter_, OrderBy):
                result = self._order_by(
                    result,
                    filter_.field_name,
                    sort_desc=filter_.sort_order == "desc",
                )
            elif isinstance(filter_, NotInSearchFilter):
                result = self._filter_by_not_like(
                    result,
                    filter_.field_name,
                    value=filter_.value,
                    ignore_case=bool(filter_.ignore_case),
                )
            elif isinstance(filter_, SearchFilter):
                result = self._filter_by_like(
                    result,
                    filter_.field_name,
                    value=filter_.value,
                    ignore_case=bool(filter_.ignore_case),
                )
            elif not isinstance(filter_, ColumnElement):
                msg = f"Unexpected filter: {filter_}"
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

    async def _list_and_count_basic(
        self,
        *filters: StatementFilter | ColumnElement[bool],
        **kwargs: Any,
    ) -> tuple[list[ModelT], int]:
        result = await self.list(*filters, **kwargs)
        return result, len(result)

    async def _list_and_count_window(
        self,
        *filters: StatementFilter | ColumnElement[bool],
        **kwargs: Any,
    ) -> tuple[list[ModelT], int]:
        return await self._list_and_count_basic(*filters, **kwargs)

    def _find_or_raise_not_found(self, id_: Any) -> ModelT:
        return self.check_not_found(self.__collection__().get_or_none(id_))

    def _find_one_or_raise_error(self, result: list[ModelT]) -> ModelT:
        if not result:
            msg = "No item found when one was expected"
            raise IntegrityError(msg)
        if len(result) > 1:
            msg = "Multiple objects when one was expected"
            raise IntegrityError(msg)
        return result[0]

    def _get_update_many_statement(
        self,
        model_type: type[ModelT],
        supports_returning: bool,
        loader_options: list[_AbstractLoad] | None,
        execution_options: dict[str, Any] | None,
    ) -> StatementLambdaElement:
        return cast("StatementLambdaElement", self.statement)

    @classmethod
    async def check_health(cls, session: AsyncSession | async_scoped_session[AsyncSession]) -> bool:  # noqa: ARG003
        return True

    async def get(
        self,
        item_id: Any,
        *,
        auto_expunge: bool | None = None,
        statement: Select[tuple[ModelT]] | StatementLambdaElement | None = None,
        id_attribute: str | InstrumentedAttribute[Any] | None = None,
        load: LoadSpec | None = None,
        execution_options: dict[str, Any] | None = None,
    ) -> ModelT:
        return self._find_or_raise_not_found(item_id)

    async def get_one(
        self,
        *filters: StatementFilter | ColumnElement[bool],
        auto_expunge: bool | None = None,
        statement: Select[tuple[ModelT]] | StatementLambdaElement | None = None,
        load: LoadSpec | None = None,
        execution_options: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ModelT:
        return self.check_not_found(await self.get_one_or_none(**kwargs))

    async def get_one_or_none(
        self,
        *filters: StatementFilter | ColumnElement[bool],
        auto_expunge: bool | None = None,
        statement: Select[tuple[ModelT]] | StatementLambdaElement | None = None,
        load: LoadSpec | None = None,
        execution_options: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ModelT | None:
        result = self._filter_result_by_kwargs(self.__collection__().list(), kwargs)
        if len(result) > 1:
            msg = "Multiple objects when one was expected"
            raise IntegrityError(msg)
        return result[0] if result else None

    async def get_or_upsert(
        self,
        *filters: StatementFilter | ColumnElement[bool],
        match_fields: list[str] | str | None = None,
        upsert: bool = True,
        attribute_names: Iterable[str] | None = None,
        with_for_update: bool | None = None,
        auto_commit: bool | None = None,
        auto_expunge: bool | None = None,
        auto_refresh: bool | None = None,
        load: LoadSpec | None = None,
        execution_options: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> tuple[ModelT, bool]:
        kwargs_ = self._exclude_unused_kwargs(kwargs)
        if match_fields := self._get_match_fields(match_fields=match_fields):
            match_filter = {
                # sourcery skip: remove-none-from-default-get
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
                field = getattr(existing, field_name, MISSING)
                if field is not MISSING and field != new_field_value:
                    setattr(existing, field_name, new_field_value)
            existing = await self.update(existing)
        return existing, False

    async def get_and_update(
        self,
        *filters: StatementFilter | ColumnElement[bool],
        match_fields: list[str] | str | None = None,
        attribute_names: Iterable[str] | None = None,
        with_for_update: bool | None = None,
        auto_commit: bool | None = None,
        auto_expunge: bool | None = None,
        auto_refresh: bool | None = None,
        load: LoadSpec | None = None,
        execution_options: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> tuple[ModelT, bool]:
        kwargs_ = self._exclude_unused_kwargs(kwargs)
        if match_fields := self._get_match_fields(match_fields=match_fields):
            match_filter = {
                # sourcery skip: remove-none-from-default-get
                field_name: kwargs_.get(field_name, None)
                for field_name in match_fields
                if kwargs_.get(field_name, None) is not None
            }
        else:
            match_filter = kwargs_
        existing = await self.get_one(**match_filter)
        updated = False
        for field_name, new_field_value in kwargs_.items():
            field = getattr(existing, field_name, MISSING)
            if field is not MISSING and field != new_field_value:
                updated = True
                setattr(existing, field_name, new_field_value)
        existing = await self.update(existing)
        return existing, updated

    async def exists(self, *filters: StatementFilter | ColumnElement[bool], **kwargs: Any) -> bool:
        existing = await self.count(*filters, **kwargs)
        return existing > 0

    async def count(self, *filters: StatementFilter | ColumnElement[bool], **kwargs: Any) -> int:
        result = self._apply_filters(self.__collection__().list(), *filters)
        return len(self._filter_result_by_kwargs(result, kwargs))

    async def add(
        self,
        data: ModelT,
        *,
        auto_commit: bool | None = None,
        auto_expunge: bool | None = None,
        auto_refresh: bool | None = None,
    ) -> ModelT:
        try:
            self.__database__.add(self.model_type, data)
        except KeyError as exc:
            msg = "Item already exist in collection"
            raise IntegrityError(msg) from exc
        return data

    async def add_many(
        self,
        data: list[ModelT],
        *,
        auto_commit: bool | None = None,
        auto_expunge: bool | None = None,
    ) -> list[ModelT]:
        for obj in data:
            await self.add(obj)
        return data

    async def update(
        self,
        data: ModelT,
        *,
        attribute_names: Iterable[str] | None = None,
        with_for_update: bool | None = None,
        auto_commit: bool | None = None,
        auto_expunge: bool | None = None,
        auto_refresh: bool | None = None,
        id_attribute: str | InstrumentedAttribute[Any] | None = None,
        load: LoadSpec | None = None,
        execution_options: dict[str, Any] | None = None,
    ) -> ModelT:
        self._find_or_raise_not_found(self.__collection__().key(data))
        return self.__collection__().update(data)

    async def update_many(
        self,
        data: list[ModelT],
        *,
        auto_commit: bool | None = None,
        auto_expunge: bool | None = None,
        load: LoadSpec | None = None,
        execution_options: dict[str, Any] | None = None,
    ) -> list[ModelT]:
        return [self.__collection__().update(obj) for obj in data if obj in self.__collection__()]

    async def delete(
        self,
        item_id: Any,
        *,
        auto_commit: bool | None = None,
        auto_expunge: bool | None = None,
        id_attribute: str | InstrumentedAttribute[Any] | None = None,
        load: LoadSpec | None = None,
        execution_options: dict[str, Any] | None = None,
    ) -> ModelT:
        try:
            return self._find_or_raise_not_found(item_id)
        finally:
            self.__collection__().remove(item_id)

    async def delete_many(
        self,
        item_ids: list[Any],
        *,
        auto_commit: bool | None = None,
        auto_expunge: bool | None = None,
        id_attribute: str | InstrumentedAttribute[Any] | None = None,
        chunk_size: int | None = None,
        load: LoadSpec | None = None,
        execution_options: dict[str, Any] | None = None,
    ) -> list[ModelT]:
        deleted: list[ModelT] = []
        for id_ in item_ids:
            if obj := self.__collection__().get_or_none(id_):
                deleted.append(obj)
                self.__collection__().remove(id_)
        return deleted

    async def delete_where(
        self,
        *filters: StatementFilter | ColumnElement[bool],
        auto_commit: bool | None = None,
        auto_expunge: bool | None = None,
        load: LoadSpec | None = None,
        execution_options: dict[str, Any] | None = None,
        sanity_check: bool = True,
        **kwargs: Any,
    ) -> list[ModelT]:
        result = self.__collection__().list()
        result = self._apply_filters(result, *filters)
        models = self._filter_result_by_kwargs(result, kwargs)
        item_ids = [getattr(model, self.id_attribute) for model in models]
        return await self.delete_many(item_ids=item_ids)

    async def upsert(
        self,
        data: ModelT,
        *,
        attribute_names: Iterable[str] | None = None,
        with_for_update: bool | None = None,
        auto_expunge: bool | None = None,
        auto_commit: bool | None = None,
        auto_refresh: bool | None = None,
        match_fields: list[str] | str | None = None,
        load: LoadSpec | None = None,
        execution_options: dict[str, Any] | None = None,
    ) -> ModelT:
        # sourcery skip: assign-if-exp, reintroduce-else
        if data in self.__collection__():
            return await self.update(data)
        return await self.add(data)

    async def upsert_many(
        self,
        data: list[ModelT],
        *,
        auto_expunge: bool | None = None,
        auto_commit: bool | None = None,
        no_merge: bool = False,
        match_fields: list[str] | str | None = None,
        load: LoadSpec | None = None,
        execution_options: dict[str, Any] | None = None,
    ) -> list[ModelT]:
        return [await self.upsert(item) for item in data]

    async def list_and_count(
        self,
        *filters: StatementFilter | ColumnElement[bool],
        statement: Select[tuple[ModelT]] | StatementLambdaElement | None = None,
        auto_expunge: bool | None = None,
        force_basic_query_mode: bool | None = None,
        order_by: list[OrderingPair] | OrderingPair | None = None,
        load: LoadSpec | None = None,
        execution_options: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> tuple[list[ModelT], int]:
        return await self._list_and_count_basic(*filters, **kwargs)

    def filter_collection_by_kwargs(self, collection: CollectionT, /, **kwargs: Any) -> CollectionT:
        for value in self._filter_result_by_kwargs(cast("List[ModelT]", collection), kwargs):
            self.__filtered_store__.add(value)
        return collection

    async def list(self, *filters: StatementFilter | ColumnElement[bool], **kwargs: Any) -> list[ModelT]:
        result = self.__collection__().list()
        result = self._apply_filters(result, *filters)
        return self._filter_result_by_kwargs(result, kwargs)


class SQLAlchemyAsyncMockSlugRepository(
    SQLAlchemyAsyncMockRepository[ModelT],
    SQLAlchemyAsyncSlugRepositoryProtocol[ModelT],
):
    async def get_by_slug(
        self,
        slug: str,
        load: LoadSpec | None = None,
        execution_options: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ModelT | None:
        """Select record by slug value."""
        return await self.get_one_or_none(slug=slug)

    async def get_available_slug(
        self,
        value_to_slugify: str,
        **kwargs: Any,
    ) -> str:
        """Get a unique slug for the supplied value.

        If the value is found to exist, a random 4 digit character is appended to the end.

        Override this method to change the default behavior

        Args:
            value_to_slugify (str): A string that should be converted to a unique slug.
            **kwargs: stuff

        Returns:
            str: a unique slug for the supplied value.  This is safe for URLs and other unique identifiers.
        """
        slug = slugify(value_to_slugify)
        if await self._is_slug_unique(slug):
            return slug
        random_string = "".join(random.choices(string.ascii_lowercase + string.digits, k=4))  # noqa: S311
        return f"{slug}-{random_string}"

    async def _is_slug_unique(
        self,
        slug: str,
        **kwargs: Any,
    ) -> bool:
        return await self.exists(slug=slug) is False
