import datetime
from collections import abc
from collections.abc import Iterable
from typing import Any, List, Literal, Optional, Union, cast, overload
from unittest.mock import create_autospec

from sqlalchemy import (
    ColumnElement,
    Dialect,
    Select,
    StatementLambdaElement,
    Update,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio.scoping import async_scoped_session
from sqlalchemy.orm import InstrumentedAttribute, Load
from sqlalchemy.sql.dml import ReturningUpdate
from sqlalchemy.sql.selectable import ForUpdateParameter
from typing_extensions import Self

from advanced_alchemy.exceptions import (
    ErrorMessages,
    ImproperConfigurationError,
    IntegrityError,
)
from advanced_alchemy.filters import StatementFilter
from advanced_alchemy.repository._async import (
    SQLAlchemyAsyncRepositoryProtocol,
    SQLAlchemyAsyncSlugRepositoryMixin,
    SQLAlchemyAsyncSlugRepositoryProtocol,
)
from advanced_alchemy.repository._util import (
    LoadSpec,
    ModelRepositoryMixin,
    compare_values,
    get_primary_key_info,
)
from advanced_alchemy.repository.memory.base import (
    AnyObject,
    InMemoryFilterEvaluator,
    InMemoryStore,
    SQLAlchemyInMemoryStore,
    SQLAlchemyMultiStore,
)
from advanced_alchemy.repository.typing import MISSING, ModelT, OrderingPair, PrimaryKeyType
from advanced_alchemy.utils.dataclass import Empty, EmptyType
from advanced_alchemy.utils.deprecation import warn_deprecation


class SQLAlchemyAsyncMockRepository(ModelRepositoryMixin[ModelT], SQLAlchemyAsyncRepositoryProtocol[ModelT]):
    """In memory repository."""

    __database__: SQLAlchemyMultiStore[ModelT] = SQLAlchemyMultiStore(SQLAlchemyInMemoryStore)
    __database_registry__: dict[type[Self], SQLAlchemyMultiStore[ModelT]] = {}
    loader_options: Optional[LoadSpec] = None
    """Default loader options for the repository."""
    execution_options: Optional[dict[str, Any]] = None
    """Default execution options for the repository."""
    model_type: type[ModelT]
    id_attribute: Any = "id"
    match_fields: Optional[Union[List[str], str]] = None
    uniquify: bool = False
    _exclude_kwargs: set[str] = {
        "statement",
        "session",
        "auto_expunge",
        "auto_refresh",
        "auto_commit",
        "attribute_names",
        "with_for_update",
        "count_with_window_function",
        "loader_options",
        "execution_options",
        "order_by",
        "load",
        "error_messages",
        "wrap_exceptions",
        "uniquify",
        "include_deleted",
        "bind_group",
    }

    def __init__(
        self,
        *,
        statement: Union[Select[tuple[ModelT]], StatementLambdaElement, None] = None,
        session: Union[AsyncSession, async_scoped_session[AsyncSession]],
        model_type: Optional[type[ModelT]] = None,
        auto_expunge: bool = False,
        auto_refresh: bool = True,
        auto_commit: bool = False,
        order_by: Optional[Union[List[OrderingPair], OrderingPair]] = None,
        error_messages: Optional[Union[ErrorMessages, EmptyType]] = Empty,
        wrap_exceptions: bool = True,
        load: Optional[LoadSpec] = None,
        execution_options: Optional[dict[str, Any]] = None,
        uniquify: Optional[bool] = None,
        include_deleted: Optional[bool] = None,
        **kwargs: Any,
    ) -> None:
        if model_type is not None:
            self.model_type = model_type
        if getattr(self, "model_type", None) is None:
            msg = (
                "Repository 'model_type' is not configured. Specify the model via "
                "generic type parameter (e.g. SQLAlchemyAsyncMockRepository[Model]), "
                "class attribute 'model_type = Model', or keyword argument 'model_type=Model'."
            )
            raise ImproperConfigurationError(msg)
        self.session = session
        self.statement = create_autospec("Select[Tuple[ModelT]]", instance=True)
        self.auto_expunge = auto_expunge
        self.auto_refresh = auto_refresh
        self.auto_commit = auto_commit
        self.error_messages = self._get_error_messages(
            error_messages=error_messages, default_messages=self.error_messages
        )
        self.wrap_exceptions = wrap_exceptions
        self.include_deleted = include_deleted if include_deleted is not None else self.include_deleted
        self.order_by = order_by
        self._dialect: Dialect = create_autospec(Dialect, instance=True)
        self._dialect.name = "mock"
        self.__filtered_store__: InMemoryStore[ModelT] = self.__database__.store_type()
        self._default_options: Any = []
        self._default_execution_options: Any = {}
        self._loader_options: Any = []
        self._loader_options_have_wildcards = False
        self.uniquify = bool(uniquify)
        self._pk_columns, self._pk_attr_names = get_primary_key_info(self.model_type)

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        cls.__database_registry__[cls] = cls.__database__  # type: ignore[index]

    def _get_store_key(self, pk_value: PrimaryKeyType) -> str:
        """Generate a store key from a primary key value.

        Args:
            pk_value: Primary key value (scalar, tuple, or dict).

        Returns:
            String key for the in-memory store.
        """
        pk_tuple = self._normalize_pk_to_tuple(pk_value)
        if len(pk_tuple) > 1:
            return str(pk_tuple)
        return str(pk_tuple[0]) if pk_tuple else ""

    def _get_store_key_from_instance(self, instance: ModelT) -> str:
        """Generate a store key from a model instance.

        Args:
            instance: Model instance to generate key from.

        Returns:
            String key for the in-memory store.
        """
        pk_value = self.get_primary_key_value(instance)
        return str(pk_value)

    @classmethod
    def __database_add__(cls, identity: Any, data: ModelT) -> ModelT:
        return cast("ModelT", cls.__database__.add(identity, data))  # type: ignore[redundant-cast]

    @classmethod
    def __database_clear__(cls) -> None:
        for database in cls.__database_registry__.values():  # pyright: ignore[reportGeneralTypeIssues,reportUnknownMemberType]
            database.remove_all()

    @overload
    def __collection__(self) -> InMemoryStore[ModelT]: ...

    @overload
    def __collection__(self, identity: type[AnyObject]) -> InMemoryStore[AnyObject]: ...

    def __collection__(
        self,
        identity: Optional[type[AnyObject]] = None,
    ) -> Union[InMemoryStore[AnyObject], InMemoryStore[ModelT]]:
        if identity:
            return self.__database__.store(identity)
        return self.__filtered_store__ or self.__database__.store(self.model_type)

    def _exclude_unused_kwargs(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in kwargs.items() if key not in self._exclude_kwargs}

    @staticmethod
    def _apply_limit_offset_pagination(result: List[ModelT], limit: int, offset: int) -> List[ModelT]:
        return InMemoryFilterEvaluator.apply_limit_offset_pagination(result, limit, offset)

    def _extract_field_name(self, field: "Union[str, ColumnElement[Any], InstrumentedAttribute[Any]]") -> str:
        """Extract string field name from various input types.

        Args:
            field: Field name, column element, or instrumented attribute

        Returns:
            str: String field name for use with getattr()

        Raises:
            RepositoryError: If a ColumnElement (func expression) is used with mock repository
        """
        return InMemoryFilterEvaluator.extract_field_name(field)

    def _filter_in_collection(
        self,
        result: List[ModelT],
        field_name: "Union[str, ColumnElement[Any], InstrumentedAttribute[Any]]",
        values: abc.Collection[Any],
    ) -> List[ModelT]:
        return InMemoryFilterEvaluator.filter_in_collection(result, field_name, values)

    def _filter_not_in_collection(
        self,
        result: List[ModelT],
        field_name: "Union[str, ColumnElement[Any], InstrumentedAttribute[Any]]",
        values: abc.Collection[Any],
    ) -> List[ModelT]:
        return InMemoryFilterEvaluator.filter_not_in_collection(result, field_name, values)

    def _filter_on_datetime_field(
        self,
        result: List[ModelT],
        field_name: "Union[str, ColumnElement[Any], InstrumentedAttribute[Any]]",
        before: Optional[datetime.datetime] = None,
        after: Optional[datetime.datetime] = None,
        on_or_before: Optional[datetime.datetime] = None,
        on_or_after: Optional[datetime.datetime] = None,
    ) -> List[ModelT]:
        return InMemoryFilterEvaluator.filter_on_datetime_field(
            result,
            field_name,
            before=before,
            after=after,
            on_or_before=on_or_before,
            on_or_after=on_or_after,
        )

    @staticmethod
    def _filter_by_like(
        result: List[ModelT],
        field_name: Union[str, set[str]],
        value: str,
        ignore_case: bool,
        escape_wildcards: bool = False,
    ) -> List[ModelT]:
        return InMemoryFilterEvaluator.filter_by_like(
            result,
            field_name,
            value=value,
            ignore_case=ignore_case,
            escape_wildcards=escape_wildcards,
        )

    @staticmethod
    def _filter_by_not_like(
        result: List[ModelT],
        field_name: Union[str, set[str]],
        value: str,
        ignore_case: bool,
        escape_wildcards: bool = False,
    ) -> List[ModelT]:
        return InMemoryFilterEvaluator.filter_by_not_like(
            result,
            field_name,
            value=value,
            ignore_case=ignore_case,
            escape_wildcards=escape_wildcards,
        )

    def _filter_result_by_kwargs(
        self,
        result: Iterable[ModelT],
        /,
        kwargs: Union[dict[Any, Any], Iterable[tuple[Any, Any]]],
    ) -> List[ModelT]:
        kwargs_: dict[Any, Any] = kwargs if isinstance(kwargs, dict) else dict(*kwargs)  # pyright: ignore
        kwargs_ = self._exclude_unused_kwargs(kwargs_)  # pyright: ignore
        return InMemoryFilterEvaluator.filter_by_kwargs(result, kwargs_)

    def _order_by(
        self,
        result: List[ModelT],
        field_name: "Union[str, ColumnElement[Any], InstrumentedAttribute[Any]]",
        sort_desc: bool = False,
        nulls: Optional[Literal["first", "last"]] = None,
    ) -> List[ModelT]:
        return InMemoryFilterEvaluator.order_by(result, field_name, sort_desc=sort_desc, nulls=nulls)

    def _apply_filters(
        self,
        result: List[ModelT],
        *filters: Union[StatementFilter, ColumnElement[bool]],
        apply_pagination: bool = True,
    ) -> List[ModelT]:
        return InMemoryFilterEvaluator.apply_filters(result, *filters, apply_pagination=apply_pagination)

    def _get_collection_items(self, include_deleted: Optional[bool] = None) -> List[ModelT]:
        items = list(self.__collection__().get_all())
        if self._should_filter_soft_deleted(include_deleted):
            return [item for item in items if getattr(item, "deleted_at", None) is None]
        return items

    async def _get_many_and_count_basic(
        self,
        *filters: Union[StatementFilter, ColumnElement[bool]],
        include_deleted: Optional[bool] = None,
        **kwargs: Any,
    ) -> tuple[List[ModelT], int]:
        filtered = self._filter_result_by_kwargs(self._get_collection_items(include_deleted), kwargs)
        filtered = self._apply_filters(filtered, *filters, apply_pagination=False)
        total_count = len(filtered)
        return InMemoryFilterEvaluator.paginate_items(filtered, *filters), total_count

    async def _get_many_and_count_window(
        self,
        *filters: Union[StatementFilter, ColumnElement[bool]],
        include_deleted: Optional[bool] = None,
        **kwargs: Any,
    ) -> tuple[List[ModelT], int]:
        return await self._get_many_and_count_basic(*filters, include_deleted=include_deleted, **kwargs)

    def _find_or_raise_not_found(
        self,
        id_: PrimaryKeyType,
        include_deleted: Optional[bool] = None,
    ) -> ModelT:
        """Find an item by primary key or raise NotFoundError.

        Args:
            id_: Primary key value (scalar, tuple, or dict).
            include_deleted: Whether to include soft-deleted records.

        Returns:
            The found model instance.

        Raises:
            NotFoundError: If no instance found with the given primary key.
        """
        store_key = self._get_store_key(id_)
        item = self.__collection__().get_or_none(store_key)
        if (
            item is not None
            and self._should_filter_soft_deleted(include_deleted)
            and getattr(item, "deleted_at", None) is not None
        ):
            item = None
        return self.check_not_found(item)

    def _find_many_by_ids(
        self,
        item_ids: List[PrimaryKeyType],
        *,
        id_attribute: Optional[Union[str, InstrumentedAttribute[Any]]] = None,
        include_deleted: Optional[bool] = None,
    ) -> List[ModelT]:
        resolved_attr = (
            id_attribute.key if isinstance(id_attribute, InstrumentedAttribute) else (id_attribute or self.id_attribute)
        )
        matched: List[ModelT] = []
        if self.has_composite_pk or resolved_attr == self.id_attribute:
            for id_ in item_ids:
                store_key = self._get_store_key(id_)
                obj = self.__collection__().get_or_none(store_key)
                if obj is None:
                    continue
                if self._should_filter_soft_deleted(include_deleted) and getattr(obj, "deleted_at", None) is not None:
                    continue
                matched.append(obj)
            return matched

        target_values = list(item_ids)
        matched.extend(
            obj
            for obj in self._get_collection_items(include_deleted=include_deleted)
            if getattr(obj, str(resolved_attr), MISSING) in target_values
        )
        return matched

    @staticmethod
    def _find_one_or_raise_error(result: List[ModelT]) -> ModelT:
        if not result:
            msg = "No item found when one was expected"
            raise IntegrityError(msg)
        if len(result) > 1:
            msg = "Multiple objects when one was expected"
            raise IntegrityError(msg)
        return result[0]  # pyright: ignore

    def _get_update_many_statement(
        self,
        model_type: type[ModelT],
        supports_returning: bool,
        loader_options: Optional[List[Load]],
        execution_options: Optional[dict[str, Any]],
    ) -> Union[Update, ReturningUpdate[tuple[ModelT]]]:
        return self.statement  # type: ignore[no-any-return] # pyright: ignore[reportReturnType]

    @classmethod
    async def check_health(cls, session: Union[AsyncSession, async_scoped_session[AsyncSession]]) -> bool:
        return True

    async def get(
        self,
        item_id: PrimaryKeyType,
        *,
        auto_expunge: Optional[bool] = None,
        statement: Union[Select[tuple[ModelT]], StatementLambdaElement, None] = None,
        id_attribute: Union[str, InstrumentedAttribute[Any], None] = None,
        error_messages: Optional[Union[ErrorMessages, EmptyType]] = Empty,
        load: Optional[LoadSpec] = None,
        execution_options: Optional[dict[str, Any]] = None,
        uniquify: Optional[bool] = None,
        with_for_update: ForUpdateParameter = None,
        use_cache: bool = True,
        include_deleted: Optional[bool] = None,
        bind_group: Optional[str] = None,
    ) -> ModelT:
        return self._find_or_raise_not_found(item_id, include_deleted=include_deleted)

    async def get_one(
        self,
        *filters: Union[StatementFilter, ColumnElement[bool]],
        auto_expunge: Optional[bool] = None,
        statement: Union[Select[tuple[ModelT]], StatementLambdaElement, None] = None,
        error_messages: Optional[Union[ErrorMessages, EmptyType]] = Empty,
        load: Optional[LoadSpec] = None,
        execution_options: Optional[dict[str, Any]] = None,
        uniquify: Optional[bool] = None,
        include_deleted: Optional[bool] = None,
        bind_group: Optional[str] = None,
        **kwargs: Any,
    ) -> ModelT:
        return self.check_not_found(await self.get_one_or_none(*filters, include_deleted=include_deleted, **kwargs))

    async def get_one_or_none(
        self,
        *filters: Union[StatementFilter, ColumnElement[bool]],
        auto_expunge: Optional[bool] = None,
        statement: Union[Select[tuple[ModelT]], StatementLambdaElement, None] = None,
        error_messages: Optional[Union[ErrorMessages, EmptyType]] = Empty,
        load: Optional[LoadSpec] = None,
        execution_options: Optional[dict[str, Any]] = None,
        uniquify: Optional[bool] = None,
        include_deleted: Optional[bool] = None,
        bind_group: Optional[str] = None,
        **kwargs: Any,
    ) -> Union[ModelT, None]:
        result = self._apply_filters(self._get_collection_items(include_deleted), *filters)
        result = self._filter_result_by_kwargs(result, kwargs)
        if len(result) > 1:
            msg = "Multiple objects when one was expected"
            raise IntegrityError(msg)
        return result[0] if result else None

    async def get_or_upsert(
        self,
        *filters: Union[StatementFilter, ColumnElement[bool]],
        match_fields: Union[List[str], str, None] = None,
        upsert: bool = True,
        attribute_names: Optional[Iterable[str]] = None,
        with_for_update: ForUpdateParameter = None,
        auto_commit: Optional[bool] = None,
        auto_expunge: Optional[bool] = None,
        auto_refresh: Optional[bool] = None,
        error_messages: Optional[Union[ErrorMessages, EmptyType]] = Empty,
        load: Optional[LoadSpec] = None,
        execution_options: Optional[dict[str, Any]] = None,
        uniquify: Optional[bool] = None,
        bind_group: Optional[str] = None,
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
        existing = await self.get_one_or_none(*filters, **match_filter)
        if not existing:
            return (await self.add(self.model_type(**kwargs_)), True)
        if upsert:
            for field_name, new_field_value in kwargs_.items():
                field = getattr(existing, field_name, MISSING)
                if field is not MISSING and not compare_values(field, new_field_value):  # pragma: no cover
                    setattr(existing, field_name, new_field_value)
            existing = await self.update(existing)
        return existing, False

    async def get_and_update(
        self,
        *filters: Union[StatementFilter, ColumnElement[bool]],
        match_fields: Union[List[str], str, None] = None,
        attribute_names: Optional[Iterable[str]] = None,
        with_for_update: ForUpdateParameter = None,
        auto_commit: Optional[bool] = None,
        auto_expunge: Optional[bool] = None,
        auto_refresh: Optional[bool] = None,
        error_messages: Optional[Union[ErrorMessages, EmptyType]] = Empty,
        load: Optional[LoadSpec] = None,
        execution_options: Optional[dict[str, Any]] = None,
        uniquify: Optional[bool] = None,
        bind_group: Optional[str] = None,
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
        existing = await self.get_one(*filters, **match_filter)
        updated = False
        for field_name, new_field_value in kwargs_.items():
            field = getattr(existing, field_name, MISSING)
            if field is not MISSING and not compare_values(field, new_field_value):  # pragma: no cover
                updated = True
                setattr(existing, field_name, new_field_value)
        existing = await self.update(existing)
        return existing, updated

    async def exists(
        self,
        *filters: "Union[StatementFilter, ColumnElement[bool]]",
        uniquify: Optional[bool] = None,
        include_deleted: Optional[bool] = None,
        bind_group: Optional[str] = None,
        **kwargs: Any,
    ) -> bool:
        existing = await self.count(*filters, include_deleted=include_deleted, **kwargs)
        return existing > 0

    async def count(
        self,
        *filters: "Union[StatementFilter, ColumnElement[bool]]",
        uniquify: Optional[bool] = None,
        include_deleted: Optional[bool] = None,
        bind_group: Optional[str] = None,
        **kwargs: Any,
    ) -> int:
        result = self._apply_filters(self._get_collection_items(include_deleted), *filters, apply_pagination=False)
        return len(self._filter_result_by_kwargs(result, kwargs))

    async def add(
        self,
        data: ModelT,
        *,
        auto_commit: Optional[bool] = None,
        auto_expunge: Optional[bool] = None,
        auto_refresh: Optional[bool] = None,
        error_messages: Optional[Union[ErrorMessages, EmptyType]] = Empty,
        bind_group: Optional[str] = None,
    ) -> ModelT:
        try:
            self.__database__.add(self.model_type, data)
        except KeyError as exc:
            msg = "Item already exist in collection"
            raise IntegrityError(msg) from exc
        return data

    async def add_many(
        self,
        data: List[ModelT],
        *,
        auto_commit: Optional[bool] = None,
        auto_expunge: Optional[bool] = None,
        error_messages: Optional[Union[ErrorMessages, EmptyType]] = Empty,
        bind_group: Optional[str] = None,
    ) -> List[ModelT]:
        for obj in data:
            await self.add(obj)  # pyright: ignore[reportCallIssue]
        return data

    async def update(
        self,
        data: ModelT,
        *,
        attribute_names: Optional[Iterable[str]] = None,
        with_for_update: ForUpdateParameter = None,
        auto_commit: Optional[bool] = None,
        auto_expunge: Optional[bool] = None,
        auto_refresh: Optional[bool] = None,
        id_attribute: Optional[Union[str, InstrumentedAttribute[Any]]] = None,
        error_messages: Optional[Union[ErrorMessages, EmptyType]] = Empty,
        load: Optional[LoadSpec] = None,
        execution_options: Optional[dict[str, Any]] = None,
        uniquify: Optional[bool] = None,
        bind_group: Optional[str] = None,
    ) -> ModelT:
        pk_value = self.get_primary_key_value(data)
        self._find_or_raise_not_found(pk_value)
        return self.__collection__().update(data)

    async def update_many(
        self,
        data: List[ModelT],
        *,
        auto_commit: Optional[bool] = None,
        auto_expunge: Optional[bool] = None,
        error_messages: Optional[Union[ErrorMessages, EmptyType]] = Empty,
        load: Optional[LoadSpec] = None,
        execution_options: Optional[dict[str, Any]] = None,
        uniquify: Optional[bool] = None,
        bind_group: Optional[str] = None,
    ) -> List[ModelT]:
        return [self.__collection__().update(obj) for obj in data if obj in self.__collection__()]

    async def delete(
        self,
        item_id: PrimaryKeyType,
        *,
        auto_commit: Optional[bool] = None,
        auto_expunge: Optional[bool] = None,
        id_attribute: Optional[Union[str, InstrumentedAttribute[Any]]] = None,
        error_messages: Optional[Union[ErrorMessages, EmptyType]] = Empty,
        load: Optional[LoadSpec] = None,
        execution_options: Optional[dict[str, Any]] = None,
        uniquify: Optional[bool] = None,
        include_deleted: bool = True,
        bind_group: Optional[str] = None,
    ) -> ModelT:
        store_key = self._get_store_key(item_id)
        item = self._find_or_raise_not_found(item_id, include_deleted=include_deleted)
        self.__collection__().remove(store_key)
        return item

    async def delete_many(
        self,
        item_ids: List[PrimaryKeyType],
        *,
        auto_commit: Optional[bool] = None,
        auto_expunge: Optional[bool] = None,
        id_attribute: Optional[Union[str, InstrumentedAttribute[Any]]] = None,
        chunk_size: Optional[int] = None,
        error_messages: Optional[Union[ErrorMessages, EmptyType]] = Empty,
        load: Optional[LoadSpec] = None,
        execution_options: Optional[dict[str, Any]] = None,
        uniquify: Optional[bool] = None,
        include_deleted: bool = True,
        bind_group: Optional[str] = None,
    ) -> List[ModelT]:
        deleted = self._find_many_by_ids(
            item_ids,
            id_attribute=id_attribute,
            include_deleted=include_deleted,
        )
        for obj in deleted:
            store_key = self._get_store_key_from_instance(obj)
            self.__collection__().remove(store_key)
        return deleted

    async def delete_where(
        self,
        *filters: Union[StatementFilter, ColumnElement[bool]],
        auto_commit: Optional[bool] = None,
        auto_expunge: Optional[bool] = None,
        error_messages: Optional[Union[ErrorMessages, EmptyType]] = Empty,
        sanity_check: bool = True,
        load: Optional[LoadSpec] = None,
        execution_options: Optional[dict[str, Any]] = None,
        uniquify: Optional[bool] = None,
        include_deleted: bool = True,
        bind_group: Optional[str] = None,
        **kwargs: Any,
    ) -> List[ModelT]:
        result = self._get_collection_items(include_deleted=include_deleted)
        result = self._apply_filters(result, *filters)
        models = self._filter_result_by_kwargs(result, kwargs)
        item_ids: list[PrimaryKeyType] = [self.get_primary_key_value(model) for model in models]
        return await self.delete_many(item_ids=item_ids, include_deleted=include_deleted)

    async def soft_delete(
        self,
        item_id: PrimaryKeyType,
        *,
        cascade: bool = True,
        auto_commit: Optional[bool] = None,
        auto_expunge: Optional[bool] = None,
        auto_refresh: Optional[bool] = None,
        id_attribute: Optional[Union[str, InstrumentedAttribute[Any]]] = None,
        error_messages: Optional[Union[ErrorMessages, EmptyType]] = Empty,
        load: Optional[LoadSpec] = None,
        execution_options: Optional[dict[str, Any]] = None,
        uniquify: Optional[bool] = None,
        with_for_update: ForUpdateParameter = None,
        bind_group: Optional[str] = None,
    ) -> ModelT:
        _ = with_for_update
        self._require_soft_delete("soft_delete")
        instance = await self.get(
            item_id,
            id_attribute=id_attribute,
            error_messages=error_messages,
            load=load,
            execution_options=execution_options,
            uniquify=uniquify,
            include_deleted=False,
            bind_group=bind_group,
        )
        self._apply_soft_delete_to_instance(instance, cascade=cascade)
        return self.__collection__().update(instance)

    async def soft_delete_many(
        self,
        item_ids: List[PrimaryKeyType],
        *,
        cascade: bool = True,
        auto_commit: Optional[bool] = None,
        auto_expunge: Optional[bool] = None,
        id_attribute: Optional[Union[str, InstrumentedAttribute[Any]]] = None,
        chunk_size: Optional[int] = None,
        error_messages: Optional[Union[ErrorMessages, EmptyType]] = Empty,
        load: Optional[LoadSpec] = None,
        execution_options: Optional[dict[str, Any]] = None,
        uniquify: Optional[bool] = None,
        bind_group: Optional[str] = None,
    ) -> List[ModelT]:
        _ = chunk_size
        self._require_soft_delete("soft_delete_many")
        if not item_ids:
            return []
        instances = self._find_many_by_ids(
            item_ids,
            id_attribute=id_attribute,
            include_deleted=False,
        )
        now = datetime.datetime.now(datetime.timezone.utc)
        visited: set[int] = set()
        for instance in instances:
            self._apply_soft_delete_to_instance(instance, now, cascade=cascade, visited=visited)
            self.__collection__().update(instance)
        return instances

    async def restore(
        self,
        item_id: PrimaryKeyType,
        *,
        cascade: bool = True,
        auto_commit: Optional[bool] = None,
        auto_expunge: Optional[bool] = None,
        auto_refresh: Optional[bool] = None,
        id_attribute: Optional[Union[str, InstrumentedAttribute[Any]]] = None,
        error_messages: Optional[Union[ErrorMessages, EmptyType]] = Empty,
        load: Optional[LoadSpec] = None,
        execution_options: Optional[dict[str, Any]] = None,
        uniquify: Optional[bool] = None,
        with_for_update: ForUpdateParameter = None,
        bind_group: Optional[str] = None,
    ) -> ModelT:
        _ = with_for_update
        self._require_soft_delete("restore")
        instance = await self.get(
            item_id,
            id_attribute=id_attribute,
            error_messages=error_messages,
            load=load,
            execution_options=execution_options,
            uniquify=uniquify,
            include_deleted=True,
            bind_group=bind_group,
        )
        self._apply_restore_to_instance(instance, cascade=cascade)
        return self.__collection__().update(instance)

    async def restore_many(
        self,
        item_ids: List[PrimaryKeyType],
        *,
        cascade: bool = True,
        auto_commit: Optional[bool] = None,
        auto_expunge: Optional[bool] = None,
        id_attribute: Optional[Union[str, InstrumentedAttribute[Any]]] = None,
        chunk_size: Optional[int] = None,
        error_messages: Optional[Union[ErrorMessages, EmptyType]] = Empty,
        load: Optional[LoadSpec] = None,
        execution_options: Optional[dict[str, Any]] = None,
        uniquify: Optional[bool] = None,
        bind_group: Optional[str] = None,
    ) -> List[ModelT]:
        _ = chunk_size
        self._require_soft_delete("restore_many")
        if not item_ids:
            return []
        instances = self._find_many_by_ids(
            item_ids,
            id_attribute=id_attribute,
            include_deleted=True,
        )
        visited: set[int] = set()
        for instance in instances:
            self._apply_restore_to_instance(instance, cascade=cascade, visited=visited)
            self.__collection__().update(instance)
        return instances

    async def upsert(
        self,
        data: ModelT,
        *,
        attribute_names: Optional[Iterable[str]] = None,
        with_for_update: ForUpdateParameter = None,
        auto_expunge: Optional[bool] = None,
        auto_commit: Optional[bool] = None,
        auto_refresh: Optional[bool] = None,
        match_fields: Optional[Union[List[str], str]] = None,
        error_messages: Optional[Union[ErrorMessages, EmptyType]] = Empty,
        load: Optional[LoadSpec] = None,
        execution_options: Optional[dict[str, Any]] = None,
        uniquify: Optional[bool] = None,
        bind_group: Optional[str] = None,
    ) -> ModelT:
        # sourcery skip: assign-if-exp, reintroduce-else
        if data in self.__collection__():
            return await self.update(data)
        return await self.add(data)

    async def upsert_many(
        self,
        data: List[ModelT],
        *,
        auto_expunge: Optional[bool] = None,
        auto_commit: Optional[bool] = None,
        no_merge: bool = False,
        match_fields: Optional[Union[List[str], str]] = None,
        error_messages: Optional[Union[ErrorMessages, EmptyType]] = Empty,
        load: Optional[LoadSpec] = None,
        execution_options: Optional[dict[str, Any]] = None,
        uniquify: Optional[bool] = None,
        bind_group: Optional[str] = None,
        chunk_size: Optional[int] = None,
    ) -> List[ModelT]:
        _ = chunk_size
        return [await self.upsert(item) for item in data]

    async def get_many_and_count(
        self,
        *filters: Union[StatementFilter, ColumnElement[bool]],
        statement: Union[Select[tuple[ModelT]], StatementLambdaElement, None] = None,
        auto_expunge: Optional[bool] = None,
        count_with_window_function: Optional[bool] = None,
        order_by: Optional[Union[List[OrderingPair], OrderingPair]] = None,
        error_messages: Optional[Union[ErrorMessages, EmptyType]] = Empty,
        load: Optional[LoadSpec] = None,
        execution_options: Optional[dict[str, Any]] = None,
        uniquify: Optional[bool] = None,
        use_cache: bool = True,
        include_deleted: Optional[bool] = None,
        bind_group: Optional[str] = None,
        **kwargs: Any,
    ) -> tuple[List[ModelT], int]:
        return await self._get_many_and_count_basic(*filters, include_deleted=include_deleted, **kwargs)

    async def list_and_count(
        self,
        *filters: Union[StatementFilter, ColumnElement[bool]],
        statement: Union[Select[tuple[ModelT]], StatementLambdaElement, None] = None,
        auto_expunge: Optional[bool] = None,
        count_with_window_function: Optional[bool] = None,
        order_by: Optional[Union[List[OrderingPair], OrderingPair]] = None,
        error_messages: Optional[Union[ErrorMessages, EmptyType]] = Empty,
        load: Optional[LoadSpec] = None,
        execution_options: Optional[dict[str, Any]] = None,
        uniquify: Optional[bool] = None,
        use_cache: bool = True,
        include_deleted: Optional[bool] = None,
        bind_group: Optional[str] = None,
        **kwargs: Any,
    ) -> tuple[List[ModelT], int]:
        """List of records and total count returned by query.

        .. deprecated:: 1.10.0
            Use :meth:`get_many_and_count` instead.
        """
        warn_deprecation(
            version="1.10.0",
            deprecated_name="list_and_count",
            kind="method",
            removal_in="2.0.0",
            alternative="get_many_and_count",
        )
        return await self.get_many_and_count(*filters, include_deleted=include_deleted, **kwargs)

    async def get_many(
        self,
        *filters: Union[StatementFilter, ColumnElement[bool]],
        uniquify: Optional[bool] = None,
        use_cache: bool = True,
        include_deleted: Optional[bool] = None,
        bind_group: Optional[str] = None,
        **kwargs: Any,
    ) -> List[ModelT]:
        result = self._filter_result_by_kwargs(self._get_collection_items(include_deleted), kwargs)
        return self._apply_filters(result, *filters)

    async def list(
        self,
        *filters: Union[StatementFilter, ColumnElement[bool]],
        uniquify: Optional[bool] = None,
        use_cache: bool = True,
        include_deleted: Optional[bool] = None,
        bind_group: Optional[str] = None,
        **kwargs: Any,
    ) -> List[ModelT]:
        """List of records returned by query.

        .. deprecated:: 1.10.0
            Use :meth:`get_many` instead.
        """
        warn_deprecation(
            version="1.10.0",
            deprecated_name="list",
            kind="method",
            removal_in="2.0.0",
            alternative="get_many",
        )
        return await self.get_many(*filters, include_deleted=include_deleted, **kwargs)


class SQLAlchemyAsyncMockSlugRepository(
    SQLAlchemyAsyncMockRepository[ModelT],
    SQLAlchemyAsyncSlugRepositoryMixin[ModelT],
    SQLAlchemyAsyncSlugRepositoryProtocol[ModelT],
):
    """In-memory repository supporting slug operations."""
