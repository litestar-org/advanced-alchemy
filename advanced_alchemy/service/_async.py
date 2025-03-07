"""Service object implementation for SQLAlchemy.

RepositoryService object is generic on the domain model type which
should be a SQLAlchemy model.
"""

from collections.abc import AsyncIterator, Iterable, Sequence
from contextlib import asynccontextmanager
from functools import cached_property
from typing import Any, ClassVar, Generic, Optional, Union, cast

from sqlalchemy import Select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio.scoping import async_scoped_session
from sqlalchemy.orm import InstrumentedAttribute
from sqlalchemy.sql import ColumnElement
from typing_extensions import Self

from advanced_alchemy.config.asyncio import SQLAlchemyAsyncConfig
from advanced_alchemy.exceptions import AdvancedAlchemyError, ErrorMessages, ImproperConfigurationError, RepositoryError
from advanced_alchemy.filters import StatementFilter
from advanced_alchemy.repository import (
    SQLAlchemyAsyncQueryRepository,
)
from advanced_alchemy.repository._util import LoadSpec, model_from_dict
from advanced_alchemy.repository.typing import ModelT, OrderingPair, SQLAlchemyAsyncRepositoryT
from advanced_alchemy.service._util import ResultConverter
from advanced_alchemy.service.typing import (
    BulkModelDictT,
    ModelDictListT,
    ModelDictT,
    is_dict,
    is_dto_data,
    is_msgspec_struct,
    is_pydantic_model,
)
from advanced_alchemy.utils.dataclass import Empty, EmptyType


class SQLAlchemyAsyncQueryService(ResultConverter):
    """Simple service to execute the basic Query repository.."""

    def __init__(
        self,
        session: Union[AsyncSession, async_scoped_session[AsyncSession]],
        **repo_kwargs: Any,
    ) -> None:
        """Configure the service object.

        Args:
            session: Session managing the unit-of-work for the operation.
            **repo_kwargs: Optional configuration values to pass into the repository
        """
        self.repository = SQLAlchemyAsyncQueryRepository(
            session=session,
            **repo_kwargs,
        )

    @classmethod
    @asynccontextmanager
    async def new(
        cls,
        session: Optional[Union[AsyncSession, async_scoped_session[AsyncSession]]] = None,
        config: Optional[SQLAlchemyAsyncConfig] = None,
    ) -> AsyncIterator[Self]:
        """Context manager that returns instance of service object.

        Handles construction of the database session._create_select_for_model

        Returns:
            The service object instance.
        """
        if not config and not session:
            raise AdvancedAlchemyError(detail="Please supply an optional configuration or session to use.")

        if session:
            yield cls(session=session)
        elif config:
            async with config.get_session() as db_session:
                yield cls(session=db_session)


class SQLAlchemyAsyncRepositoryReadService(ResultConverter, Generic[ModelT, SQLAlchemyAsyncRepositoryT]):
    """Service object that operates on a repository object."""

    repository_type: type[SQLAlchemyAsyncRepositoryT]
    """Type of the repository to use."""
    loader_options: ClassVar[Optional[LoadSpec]] = None
    """Default loader options for the repository."""
    execution_options: ClassVar[Optional[dict[str, Any]]] = None
    """Default execution options for the repository."""
    match_fields: ClassVar[Optional[Union[list[str], str]]] = None
    """List of dialects that prefer to use ``field.id = ANY(:1)`` instead of ``field.id IN (...)``."""
    uniquify: ClassVar[bool] = False
    """Optionally apply the ``unique()`` method to results before returning."""
    count_with_window_function: ClassVar[bool] = True
    """Use an analytical window function to count results.  This allows the count to be performed in a single query."""
    _repository_instance: SQLAlchemyAsyncRepositoryT

    def __init__(
        self,
        session: Union[AsyncSession, async_scoped_session[AsyncSession]],
        *,
        statement: Optional[Select[Any]] = None,
        auto_expunge: bool = False,
        auto_refresh: bool = True,
        auto_commit: bool = False,
        order_by: Optional[Union[list[OrderingPair], OrderingPair]] = None,
        error_messages: Union[ErrorMessages, None, EmptyType] = Empty,
        wrap_exceptions: bool = True,
        load: Optional[LoadSpec] = None,
        execution_options: Optional[dict[str, Any]] = None,
        uniquify: Optional[bool] = None,
        count_with_window_function: Optional[bool] = None,
        **repo_kwargs: Any,
    ) -> None:
        """Configure the service object.

        Args:
            session: Session managing the unit-of-work for the operation.
            statement: To facilitate customization of the underlying select query.
            auto_expunge: Remove object from session before returning.
            auto_refresh: Refresh object from session before returning.
            auto_commit: Commit objects before returning.
            order_by: Set default order options for queries.
            error_messages: A set of custom error messages to use for operations
            wrap_exceptions: Wrap exceptions in a RepositoryError
            load: Set default relationships to be loaded
            execution_options: Set default execution options
            uniquify: Optionally apply the ``unique()`` method to results before returning.
            count_with_window_function: When false, list and count will use two queries instead of an analytical window function.
            **repo_kwargs: passed as keyword args to repo instantiation.
        """
        load = load if load is not None else self.loader_options
        execution_options = execution_options if execution_options is not None else self.execution_options
        count_with_window_function = (
            count_with_window_function if count_with_window_function is not None else self.count_with_window_function
        )
        self._repository_instance: SQLAlchemyAsyncRepositoryT = self.repository_type(  # type: ignore[assignment]
            session=session,
            statement=statement,
            auto_expunge=auto_expunge,
            auto_refresh=auto_refresh,
            auto_commit=auto_commit,
            order_by=order_by,
            error_messages=error_messages,
            wrap_exceptions=wrap_exceptions,
            load=load,
            execution_options=execution_options,
            uniquify=self._get_uniquify(uniquify),
            count_with_window_function=count_with_window_function,
            **repo_kwargs,
        )

    def _get_uniquify(self, uniquify: Optional[bool] = None) -> bool:
        return bool(uniquify or self.uniquify)

    @property
    def repository(self) -> SQLAlchemyAsyncRepositoryT:
        """Return the repository instance."""
        if not self._repository_instance:
            msg = "Repository not initialized"
            raise ImproperConfigurationError(msg)
        return self._repository_instance

    @cached_property
    def model_type(self) -> type[ModelT]:
        """Return the model type."""
        return cast("type[ModelT]", self.repository.model_type)

    async def count(
        self,
        *filters: Union[StatementFilter, ColumnElement[bool]],
        statement: Optional[Select[tuple[ModelT]]] = None,
        error_messages: Union[ErrorMessages, None, EmptyType] = Empty,
        load: Optional[LoadSpec] = None,
        execution_options: Optional[dict[str, Any]] = None,
        uniquify: Optional[bool] = None,
        **kwargs: Any,
    ) -> int:
        """Count of records returned by query.

        Args:
            *filters: arguments for filtering.
            statement: To facilitate customization of the underlying select query.
            error_messages: An optional dictionary of templates to use
                for friendlier error messages to clients
            load: Set relationships to be loaded
            execution_options: Set default execution options
            uniquify: Optionally apply the ``unique()`` method to results before returning.
            **kwargs: key value pairs of filter types.

        Returns:
           A count of the collection, filtered, but ignoring pagination.
        """
        return await self.repository.count(
            *filters,
            statement=statement,
            error_messages=error_messages,
            load=load,
            execution_options=execution_options,
            uniquify=self._get_uniquify(uniquify),
            **kwargs,
        )

    async def exists(
        self,
        *filters: Union[StatementFilter, ColumnElement[bool]],
        error_messages: Union[ErrorMessages, None, EmptyType] = Empty,
        load: Optional[LoadSpec] = None,
        execution_options: Optional[dict[str, Any]] = None,
        uniquify: Optional[bool] = None,
        **kwargs: Any,
    ) -> bool:
        """Wrap repository exists operation.

        Args:
            *filters: Types for specific filtering operations.
            error_messages: An optional dictionary of templates to use
                for friendlier error messages to clients
            load: Set relationships to be loaded
            execution_options: Set default execution options
            uniquify: Optionally apply the ``unique()`` method to results before returning.
            **kwargs: Keyword arguments for attribute based filtering.

        Returns:
            Representation of instance with identifier `item_id`.
        """
        return await self.repository.exists(
            *filters,
            error_messages=error_messages,
            load=load,
            execution_options=execution_options,
            uniquify=self._get_uniquify(uniquify),
            **kwargs,
        )

    async def get(
        self,
        item_id: Any,
        *,
        statement: Optional[Select[tuple[ModelT]]] = None,
        id_attribute: Optional[Union[str, InstrumentedAttribute[Any]]] = None,
        auto_expunge: Optional[bool] = None,
        error_messages: Union[ErrorMessages, None, EmptyType] = Empty,
        load: Optional[LoadSpec] = None,
        execution_options: Optional[dict[str, Any]] = None,
        uniquify: Optional[bool] = None,
    ) -> ModelT:
        """Wrap repository scalar operation.

        Args:
            item_id: Identifier of instance to be retrieved.
            auto_expunge: Remove object from session before returning.
            statement: To facilitate customization of the underlying select query.
            id_attribute: Allows customization of the unique identifier to use for model fetching.
                Defaults to `id`, but can reference any surrogate or candidate key for the table.
            error_messages: An optional dictionary of templates to use
                for friendlier error messages to clients
            load: Set relationships to be loaded
            execution_options: Set default execution options
            uniquify: Optionally apply the ``unique()`` method to results before returning.

        Returns:
            Representation of instance with identifier `item_id`.
        """
        return cast(
            "ModelT",
            await self.repository.get(
                item_id=item_id,
                auto_expunge=auto_expunge,
                statement=statement,
                id_attribute=id_attribute,
                error_messages=error_messages,
                load=load,
                execution_options=execution_options,
                uniquify=self._get_uniquify(uniquify),
            ),
        )

    async def get_one(
        self,
        *filters: Union[StatementFilter, ColumnElement[bool]],
        statement: Optional[Select[tuple[ModelT]]] = None,
        auto_expunge: Optional[bool] = None,
        load: Optional[LoadSpec] = None,
        error_messages: Union[ErrorMessages, None, EmptyType] = Empty,
        execution_options: Optional[dict[str, Any]] = None,
        uniquify: Optional[bool] = None,
        **kwargs: Any,
    ) -> ModelT:
        """Wrap repository scalar operation.

        Args:
            *filters: Types for specific filtering operations.
            auto_expunge: Remove object from session before returning.
            statement: To facilitate customization of the underlying select query.
            error_messages: An optional dictionary of templates to use
                for friendlier error messages to clients
            load: Set default relationships to be loaded
            execution_options: Set default execution options
            uniquify: Optionally apply the ``unique()`` method to results before returning.
            **kwargs: Identifier of the instance to be retrieved.

        Returns:
            Representation of instance with identifier `item_id`.
        """
        return cast(
            "ModelT",
            await self.repository.get_one(
                *filters,
                auto_expunge=auto_expunge,
                statement=statement,
                error_messages=error_messages,
                load=load,
                execution_options=execution_options,
                uniquify=self._get_uniquify(uniquify),
                **kwargs,
            ),
        )

    async def get_one_or_none(
        self,
        *filters: Union[StatementFilter, ColumnElement[bool]],
        statement: Optional[Select[tuple[ModelT]]] = None,
        auto_expunge: Optional[bool] = None,
        error_messages: Union[ErrorMessages, None, EmptyType] = Empty,
        load: Optional[LoadSpec] = None,
        execution_options: Optional[dict[str, Any]] = None,
        uniquify: Optional[bool] = None,
        **kwargs: Any,
    ) -> Optional[ModelT]:
        """Wrap repository scalar operation.

        Args:
            *filters: Types for specific filtering operations.
            auto_expunge: Remove object from session before returning.
            statement: To facilitate customization of the underlying select query.
            error_messages: An optional dictionary of templates to use
                for friendlier error messages to clients
            load: Set default relationships to be loaded
            execution_options: Set default execution options
            uniquify: Optionally apply the ``unique()`` method to results before returning.
            **kwargs: Identifier of the instance to be retrieved.

        Returns:
            Representation of instance with identifier `item_id`.
        """
        return cast(
            "Optional[ModelT]",
            await self.repository.get_one_or_none(
                *filters,
                auto_expunge=auto_expunge,
                statement=statement,
                error_messages=error_messages,
                load=load,
                execution_options=execution_options,
                uniquify=self._get_uniquify(uniquify),
                **kwargs,
            ),
        )

    async def to_model_on_create(self, data: "ModelDictT[ModelT]") -> "ModelDictT[ModelT]":
        """Convenience method to allow for custom behavior on create.

        Args:
            data: The data to be converted to a model.

        Returns:
            The data to be converted to a model.
        """
        return data

    async def to_model_on_update(self, data: "ModelDictT[ModelT]") -> "ModelDictT[ModelT]":
        """Convenience method to allow for custom behavior on update.

        Args:
            data: The data to be converted to a model.

        Returns:
            The data to be converted to a model.
        """
        return data

    async def to_model_on_delete(self, data: "ModelDictT[ModelT]") -> "ModelDictT[ModelT]":
        """Convenience method to allow for custom behavior on delete.

        Args:
            data: The data to be converted to a model.

        Returns:
            The data to be converted to a model.
        """
        return data

    async def to_model_on_upsert(self, data: "ModelDictT[ModelT]") -> "ModelDictT[ModelT]":
        """Convenience method to allow for custom behavior on upsert.

        Args:
            data: The data to be converted to a model.

        Returns:
            The data to be converted to a model.
        """
        return data

    async def to_model(
        self,
        data: "ModelDictT[ModelT]",
        operation: Optional[str] = None,
    ) -> ModelT:
        """Parse and Convert input into a model.

        Args:
            data: Representations to be created.
            operation: Optional operation flag so that you can provide behavior based on CRUD operation
        Returns:
            Representation of created instances.
        """
        operation_map = {
            "create": self.to_model_on_create,
            "update": self.to_model_on_update,
            "delete": self.to_model_on_delete,
            "upsert": self.to_model_on_upsert,
        }
        if operation and (op := operation_map.get(operation)):
            data = await op(data)
        if is_dict(data):
            return model_from_dict(model=self.model_type, **data)
        if is_pydantic_model(data):
            return model_from_dict(
                model=self.model_type,
                **data.model_dump(exclude_unset=True),
            )

        if is_msgspec_struct(data):
            from msgspec import UNSET

            return model_from_dict(
                model=self.model_type,
                **{f: val for f in data.__struct_fields__ if (val := getattr(data, f, None)) != UNSET},
            )

        if is_dto_data(data):
            return cast("ModelT", data.create_instance())
        return cast("ModelT", data)

    async def list_and_count(
        self,
        *filters: Union[StatementFilter, ColumnElement[bool]],
        statement: Optional[Select[tuple[ModelT]]] = None,
        auto_expunge: Optional[bool] = None,
        count_with_window_function: Optional[bool] = None,
        order_by: Optional[Union[list[OrderingPair], OrderingPair]] = None,
        error_messages: Union[ErrorMessages, None, EmptyType] = Empty,
        load: Optional[LoadSpec] = None,
        execution_options: Optional[dict[str, Any]] = None,
        uniquify: Optional[bool] = None,
        **kwargs: Any,
    ) -> tuple[Sequence[ModelT], int]:
        """List of records and total count returned by query.

        Args:
            *filters: Types for specific filtering operations.
            statement: To facilitate customization of the underlying select query.
            auto_expunge: Remove object from session before returning.
            count_with_window_function: When false, list and count will use two queries instead of an analytical window function.
            order_by: Set default order options for queries.
            error_messages: An optional dictionary of templates to use
                for friendlier error messages to clients
            load: Set relationships to be loaded
            execution_options: Set default execution options
            uniquify: Optionally apply the ``unique()`` method to results before returning.
            **kwargs: Instance attribute value filters.

        Returns:
            List of instances and count of total collection, ignoring pagination.
        """
        return cast(
            "tuple[Sequence[ModelT], int]",
            await self.repository.list_and_count(
                *filters,
                statement=statement,
                auto_expunge=auto_expunge,
                count_with_window_function=count_with_window_function,
                order_by=order_by,
                error_messages=error_messages,
                load=load,
                execution_options=execution_options,
                uniquify=self._get_uniquify(uniquify),
                **kwargs,
            ),
        )

    @classmethod
    @asynccontextmanager
    async def new(
        cls,
        session: Optional[Union[AsyncSession, async_scoped_session[AsyncSession]]] = None,
        statement: Optional[Select[tuple[ModelT]]] = None,
        config: Optional[SQLAlchemyAsyncConfig] = None,
        error_messages: Union[ErrorMessages, None, EmptyType] = Empty,
        load: Optional[LoadSpec] = None,
        execution_options: Optional[dict[str, Any]] = None,
        uniquify: Optional[bool] = None,
        count_with_window_function: Optional[bool] = None,
    ) -> AsyncIterator[Self]:
        """Context manager that returns instance of service object.

        Handles construction of the database session._create_select_for_model

        Returns:
            The service object instance.
        """
        if not config and not session:
            raise AdvancedAlchemyError(detail="Please supply an optional configuration or session to use.")

        if session:
            yield cls(
                statement=statement,
                session=session,
                error_messages=error_messages,
                load=load,
                execution_options=execution_options,
                uniquify=uniquify,
                count_with_window_function=count_with_window_function,
            )
        elif config:
            async with config.get_session() as db_session:
                yield cls(
                    statement=statement,
                    session=db_session,
                    error_messages=error_messages,
                    load=load,
                    execution_options=execution_options,
                    uniquify=uniquify,
                    count_with_window_function=count_with_window_function,
                )

    async def list(
        self,
        *filters: Union[StatementFilter, ColumnElement[bool]],
        statement: Optional[Select[tuple[ModelT]]] = None,
        auto_expunge: Optional[bool] = None,
        order_by: Optional[Union[list[OrderingPair], OrderingPair]] = None,
        error_messages: Union[ErrorMessages, None, EmptyType] = Empty,
        load: Optional[LoadSpec] = None,
        execution_options: Optional[dict[str, Any]] = None,
        uniquify: Optional[bool] = None,
        **kwargs: Any,
    ) -> Sequence[ModelT]:
        """Wrap repository scalars operation.

        Args:
            *filters: Types for specific filtering operations.
            auto_expunge: Remove object from session before returning.
            statement: To facilitate customization of the underlying select query.
            order_by: Set default order options for queries.
            error_messages: An optional dictionary of templates to use
                for friendlier error messages to clients
            load: Set default relationships to be loaded
            execution_options: Set default execution options
            uniquify: Optionally apply the ``unique()`` method to results before returning.
            **kwargs: Instance attribute value filters.

        Returns:
            The list of instances retrieved from the repository.
        """
        return cast(
            "Sequence[ModelT]",
            await self.repository.list(
                *filters,
                statement=statement,
                auto_expunge=auto_expunge,
                order_by=order_by,
                error_messages=error_messages,
                load=load,
                execution_options=execution_options,
                uniquify=self._get_uniquify(uniquify),
                **kwargs,
            ),
        )


class SQLAlchemyAsyncRepositoryService(
    SQLAlchemyAsyncRepositoryReadService[ModelT, SQLAlchemyAsyncRepositoryT],
    Generic[ModelT, SQLAlchemyAsyncRepositoryT],
):
    """Service object that operates on a repository object."""

    async def create(
        self,
        data: "ModelDictT[ModelT]",
        *,
        auto_commit: Optional[bool] = None,
        auto_expunge: Optional[bool] = None,
        auto_refresh: Optional[bool] = None,
        error_messages: Union[ErrorMessages, None, EmptyType] = Empty,
    ) -> "ModelT":
        """Wrap repository instance creation.

        Args:
            data: Representation to be created.
            auto_expunge: Remove object from session before returning.
            auto_refresh: Refresh object from session before returning.
            auto_commit: Commit objects before returning.
            error_messages: An optional dictionary of templates to use
                for friendlier error messages to clients

        Returns:
            Representation of created instance.
        """
        data = await self.to_model(data, "create")
        return cast(
            "ModelT",
            await self.repository.add(
                data=data,
                auto_commit=auto_commit,
                auto_expunge=auto_expunge,
                auto_refresh=auto_refresh,
                error_messages=error_messages,
            ),
        )

    async def create_many(
        self,
        data: "BulkModelDictT[ModelT]",
        *,
        auto_commit: Optional[bool] = None,
        auto_expunge: Optional[bool] = None,
        error_messages: Union[ErrorMessages, None, EmptyType] = Empty,
    ) -> Sequence[ModelT]:
        """Wrap repository bulk instance creation.

        Args:
            data: Representations to be created.
            auto_expunge: Remove object from session before returning.
            auto_commit: Commit objects before returning.
            error_messages: An optional dictionary of templates to use
                for friendlier error messages to clients
            uniquify: Optionally apply the ``unique()`` method to results before returning.

        Returns:
            Representation of created instances.
        """
        if is_dto_data(data):
            data = data.create_instance()
        data = [(await self.to_model(datum, "create")) for datum in cast("ModelDictListT[ModelT]", data)]
        return cast(
            "Sequence[ModelT]",
            await self.repository.add_many(
                data=cast("list[ModelT]", data),  # pyright: ignore[reportUnnecessaryCast]
                auto_commit=auto_commit,
                auto_expunge=auto_expunge,
                error_messages=error_messages,
            ),
        )

    async def update(
        self,
        data: "ModelDictT[ModelT]",
        item_id: Optional[Any] = None,
        *,
        attribute_names: Optional[Iterable[str]] = None,
        with_for_update: Optional[bool] = None,
        auto_commit: Optional[bool] = None,
        auto_expunge: Optional[bool] = None,
        auto_refresh: Optional[bool] = None,
        id_attribute: Optional[Union[str, InstrumentedAttribute[Any]]] = None,
        error_messages: Union[ErrorMessages, None, EmptyType] = Empty,
        load: Optional[LoadSpec] = None,
        execution_options: Optional[dict[str, Any]] = None,
        uniquify: Optional[bool] = None,
    ) -> "ModelT":
        """Wrap repository update operation.

        Args:
            data: Representation to be updated.
            item_id: Identifier of item to be updated.
            attribute_names: an iterable of attribute names to pass into the ``update``
                method.
            with_for_update: indicating FOR UPDATE should be used, or may be a
                dictionary containing flags to indicate a more specific set of
                FOR UPDATE flags for the SELECT
            auto_expunge: Remove object from session before returning.
            auto_refresh: Refresh object from session before returning.
            auto_commit: Commit objects before returning.
            id_attribute: Allows customization of the unique identifier to use for model fetching.
                Defaults to `id`, but can reference any surrogate or candidate key for the table.
            error_messages: An optional dictionary of templates to use
                for friendlier error messages to clients
            load: Set default relationships to be loaded
            execution_options: Set default execution options
            uniquify: Optionally apply the ``unique()`` method to results before returning.

        Returns:
            Updated representation.
        """
        data = await self.to_model(data, "update")
        if (
            item_id is None
            and self.repository.get_id_attribute_value(  # pyright: ignore[reportUnknownMemberType]
                item=data,
                id_attribute=id_attribute,
            )
            is None
        ):
            msg = (
                "Could not identify ID attribute value.  One of the following is required: "
                f"``item_id`` or ``data.{id_attribute or self.repository.id_attribute}``"
            )
            raise RepositoryError(msg)
        if item_id is not None:
            data = self.repository.set_id_attribute_value(item_id=item_id, item=data, id_attribute=id_attribute)  # pyright: ignore[reportUnknownMemberType]
        return cast(
            "ModelT",
            await self.repository.update(
                data=data,
                attribute_names=attribute_names,
                with_for_update=with_for_update,
                auto_commit=auto_commit,
                auto_expunge=auto_expunge,
                auto_refresh=auto_refresh,
                id_attribute=id_attribute,
                error_messages=error_messages,
                load=load,
                execution_options=execution_options,
                uniquify=self._get_uniquify(uniquify),
            ),
        )

    async def update_many(
        self,
        data: "BulkModelDictT[ModelT]",
        *,
        auto_commit: Optional[bool] = None,
        auto_expunge: Optional[bool] = None,
        error_messages: Union[ErrorMessages, None, EmptyType] = Empty,
        load: Optional[LoadSpec] = None,
        execution_options: Optional[dict[str, Any]] = None,
        uniquify: Optional[bool] = None,
    ) -> Sequence[ModelT]:
        """Wrap repository bulk instance update.

        Args:
            data: Representations to be updated.
            auto_expunge: Remove object from session before returning.
            auto_commit: Commit objects before returning.
            error_messages: An optional dictionary of templates to use
                for friendlier error messages to clients
            load: Set default relationships to be loaded
            execution_options: Set default execution options
            uniquify: Optionally apply the ``unique()`` method to results before returning.

        Returns:
            Representation of updated instances.
        """
        if is_dto_data(data):
            data = data.create_instance()
        data = [(await self.to_model(datum, "update")) for datum in cast("ModelDictListT[ModelT]", data)]
        return cast(
            "Sequence[ModelT]",
            await self.repository.update_many(
                cast("list[ModelT]", data),  # pyright: ignore[reportUnnecessaryCast]
                auto_commit=auto_commit,
                auto_expunge=auto_expunge,
                error_messages=error_messages,
                load=load,
                execution_options=execution_options,
                uniquify=self._get_uniquify(uniquify),
            ),
        )

    async def upsert(
        self,
        data: "ModelDictT[ModelT]",
        item_id: Optional[Any] = None,
        *,
        attribute_names: Optional[Iterable[str]] = None,
        with_for_update: Optional[bool] = None,
        auto_expunge: Optional[bool] = None,
        auto_commit: Optional[bool] = None,
        auto_refresh: Optional[bool] = None,
        match_fields: Optional[Union[list[str], str]] = None,
        error_messages: Union[ErrorMessages, None, EmptyType] = Empty,
        load: Optional[LoadSpec] = None,
        execution_options: Optional[dict[str, Any]] = None,
        uniquify: Optional[bool] = None,
    ) -> ModelT:
        """Wrap repository upsert operation.

        Args:
            data: Instance to update existing, or be created. Identifier used to determine if an
                existing instance exists is the value of an attribute on `data` named as value of
                `self.id_attribute`.
            item_id: Identifier of the object for upsert.
            attribute_names: an iterable of attribute names to pass into the ``update`` method.
            with_for_update: indicating FOR UPDATE should be used, or may be a
                dictionary containing flags to indicate a more specific set of
                FOR UPDATE flags for the SELECT
            auto_expunge: Remove object from session before returning.
            auto_refresh: Refresh object from session before returning.
            auto_commit: Commit objects before returning.
            match_fields: a list of keys to use to match the existing model.  When
                empty, all fields are matched.
            error_messages: An optional dictionary of templates to use
                for friendlier error messages to clients
            load: Set default relationships to be loaded
            execution_options: Set default execution options
            uniquify: Optionally apply the ``unique()`` method to results before returning.

        Returns:
            Updated or created representation.
        """
        data = await self.to_model(data, "upsert")
        item_id = item_id if item_id is not None else self.repository.get_id_attribute_value(item=data)  # pyright: ignore[reportUnknownMemberType]
        if item_id is not None:
            self.repository.set_id_attribute_value(item_id, data)  # pyright: ignore[reportUnknownMemberType]
        return cast(
            "ModelT",
            await self.repository.upsert(
                data=data,
                attribute_names=attribute_names,
                with_for_update=with_for_update,
                auto_expunge=auto_expunge,
                auto_commit=auto_commit,
                auto_refresh=auto_refresh,
                match_fields=match_fields,
                error_messages=error_messages,
                load=load,
                execution_options=execution_options,
                uniquify=self._get_uniquify(uniquify),
            ),
        )

    async def upsert_many(
        self,
        data: "BulkModelDictT[ModelT]",
        *,
        auto_expunge: Optional[bool] = None,
        auto_commit: Optional[bool] = None,
        no_merge: bool = False,
        match_fields: Optional[Union[list[str], str]] = None,
        error_messages: Union[ErrorMessages, None, EmptyType] = Empty,
        load: Optional[LoadSpec] = None,
        execution_options: Optional[dict[str, Any]] = None,
        uniquify: Optional[bool] = None,
    ) -> Sequence[ModelT]:
        """Wrap repository upsert operation.

        Args:
            data: Instance to update existing, or be created.
            auto_expunge: Remove object from session before returning.
            auto_commit: Commit objects before returning.
            no_merge: Skip the usage of optimized Merge statements (**reserved for future use**)
            match_fields: a list of keys to use to match the existing model.  When
                empty, all fields are matched.
            error_messages: An optional dictionary of templates to use
                for friendlier error messages to clients
            load: Set default relationships to be loaded
            execution_options: Set default execution options
            uniquify: Optionally apply the ``unique()`` method to results before returning.

        Returns:
            Updated or created representation.
        """
        if is_dto_data(data):
            data = data.create_instance()
        data = [(await self.to_model(datum, "upsert")) for datum in cast("ModelDictListT[ModelT]", data)]
        return cast(
            "Sequence[ModelT]",
            await self.repository.upsert_many(
                data=cast("list[ModelT]", data),  # pyright: ignore[reportUnnecessaryCast]
                auto_expunge=auto_expunge,
                auto_commit=auto_commit,
                no_merge=no_merge,
                match_fields=match_fields,
                error_messages=error_messages,
                load=load,
                execution_options=execution_options,
                uniquify=self._get_uniquify(uniquify),
            ),
        )

    async def get_or_upsert(
        self,
        *filters: Union[StatementFilter, ColumnElement[bool]],
        match_fields: Optional[Union[list[str], str]] = None,
        upsert: bool = True,
        attribute_names: Optional[Iterable[str]] = None,
        with_for_update: Optional[bool] = None,
        auto_commit: Optional[bool] = None,
        auto_expunge: Optional[bool] = None,
        auto_refresh: Optional[bool] = None,
        error_messages: Union[ErrorMessages, None, EmptyType] = Empty,
        load: Optional[LoadSpec] = None,
        execution_options: Optional[dict[str, Any]] = None,
        uniquify: Optional[bool] = None,
        **kwargs: Any,
    ) -> tuple[ModelT, bool]:
        """Wrap repository instance creation.

        Args:
            *filters: Types for specific filtering operations.
            match_fields: a list of keys to use to match the existing model.  When
                empty, all fields are matched.
            upsert: When using match_fields and actual model values differ from
                `kwargs`, perform an update operation on the model.
            create: Should a model be created.  If no model is found, an exception is raised.
            attribute_names: an iterable of attribute names to pass into the ``update``
                method.
            with_for_update: indicating FOR UPDATE should be used, or may be a
                dictionary containing flags to indicate a more specific set of
                FOR UPDATE flags for the SELECT
            auto_expunge: Remove object from session before returning.
            auto_refresh: Refresh object from session before returning.
            auto_commit: Commit objects before returning.
            error_messages: An optional dictionary of templates to use
                for friendlier error messages to clients
            load: Set default relationships to be loaded
            execution_options: Set default execution options
            uniquify: Optionally apply the ``unique()`` method to results before returning.
            **kwargs: Identifier of the instance to be retrieved.

        Returns:
            Representation of created instance.
        """
        match_fields = match_fields or self.match_fields
        validated_model = await self.to_model(kwargs, "create")
        return cast(
            "tuple[ModelT, bool]",
            await self.repository.get_or_upsert(
                *filters,
                match_fields=match_fields,
                upsert=upsert,
                attribute_names=attribute_names,
                with_for_update=with_for_update,
                auto_commit=auto_commit,
                auto_expunge=auto_expunge,
                auto_refresh=auto_refresh,
                error_messages=error_messages,
                load=load,
                execution_options=execution_options,
                uniquify=self._get_uniquify(uniquify),
                **validated_model.to_dict(),
            ),
        )

    async def get_and_update(
        self,
        *filters: Union[StatementFilter, ColumnElement[bool]],
        match_fields: Optional[Union[list[str], str]] = None,
        attribute_names: Optional[Iterable[str]] = None,
        with_for_update: Optional[bool] = None,
        auto_commit: Optional[bool] = None,
        auto_expunge: Optional[bool] = None,
        auto_refresh: Optional[bool] = None,
        error_messages: Union[ErrorMessages, None, EmptyType] = Empty,
        load: Optional[LoadSpec] = None,
        execution_options: Optional[dict[str, Any]] = None,
        uniquify: Optional[bool] = None,
        **kwargs: Any,
    ) -> tuple[ModelT, bool]:
        """Wrap repository instance creation.

        Args:
            *filters: Types for specific filtering operations.
            match_fields: a list of keys to use to match the existing model.  When
                empty, all fields are matched.
            attribute_names: an iterable of attribute names to pass into the ``update``
                method.
            with_for_update: indicating FOR UPDATE should be used, or may be a
                dictionary containing flags to indicate a more specific set of
                FOR UPDATE flags for the SELECT
            auto_expunge: Remove object from session before returning.
            auto_refresh: Refresh object from session before returning.
            auto_commit: Commit objects before returning.
            error_messages: An optional dictionary of templates to use
                for friendlier error messages to clients
            load: Set default relationships to be loaded
            execution_options: Set default execution options
            uniquify: Optionally apply the ``unique()`` method to results before returning.
            **kwargs: Identifier of the instance to be retrieved.

        Returns:
            Representation of updated instance.
        """
        match_fields = match_fields or self.match_fields
        validated_model = await self.to_model(kwargs, "update")
        return cast(
            "tuple[ModelT, bool]",
            await self.repository.get_and_update(
                *filters,
                match_fields=match_fields,
                attribute_names=attribute_names,
                with_for_update=with_for_update,
                auto_commit=auto_commit,
                auto_expunge=auto_expunge,
                auto_refresh=auto_refresh,
                error_messages=error_messages,
                load=load,
                execution_options=execution_options,
                uniquify=self._get_uniquify(uniquify),
                **validated_model.to_dict(),
            ),
        )

    async def delete(
        self,
        item_id: Any,
        *,
        auto_commit: Optional[bool] = None,
        auto_expunge: Optional[bool] = None,
        id_attribute: Optional[Union[str, InstrumentedAttribute[Any]]] = None,
        error_messages: Union[ErrorMessages, None, EmptyType] = Empty,
        load: Optional[LoadSpec] = None,
        execution_options: Optional[dict[str, Any]] = None,
        uniquify: Optional[bool] = None,
    ) -> ModelT:
        """Wrap repository delete operation.

        Args:
            item_id: Identifier of instance to be deleted.
            auto_commit: Commit objects before returning.
            auto_expunge: Remove object from session before returning.
            id_attribute: Allows customization of the unique identifier to use for model fetching.
                Defaults to `id`, but can reference any surrogate or candidate key for the table.
            error_messages: An optional dictionary of templates to use
                for friendlier error messages to clients
            load: Set default relationships to be loaded
            execution_options: Set default execution options
            uniquify: Optionally apply the ``unique()`` method to results before returning.

        Returns:
            Representation of the deleted instance.
        """
        return cast(
            "ModelT",
            await self.repository.delete(
                item_id=item_id,
                auto_commit=auto_commit,
                auto_expunge=auto_expunge,
                id_attribute=id_attribute,
                error_messages=error_messages,
                load=load,
                execution_options=execution_options,
                uniquify=self._get_uniquify(uniquify),
            ),
        )

    async def delete_many(
        self,
        item_ids: list[Any],
        *,
        auto_commit: Optional[bool] = None,
        auto_expunge: Optional[bool] = None,
        id_attribute: Optional[Union[str, InstrumentedAttribute[Any]]] = None,
        chunk_size: Optional[int] = None,
        error_messages: Union[ErrorMessages, None, EmptyType] = Empty,
        load: Optional[LoadSpec] = None,
        execution_options: Optional[dict[str, Any]] = None,
        uniquify: Optional[bool] = None,
    ) -> Sequence[ModelT]:
        """Wrap repository bulk instance deletion.

        Args:
            item_ids: Identifier of instance to be deleted.
            auto_expunge: Remove object from session before returning.
            auto_commit: Commit objects before returning.
            id_attribute: Allows customization of the unique identifier to use for model fetching.
                Defaults to `id`, but can reference any surrogate or candidate key for the table.
            chunk_size: Allows customization of the ``insertmanyvalues_max_parameters`` setting for the driver.
                Defaults to `950` if left unset.
            error_messages: An optional dictionary of templates to use
                for friendlier error messages to clients
            load: Set default relationships to be loaded
            execution_options: Set default execution options
            uniquify: Optionally apply the ``unique()`` method to results before returning.

        Returns:
            Representation of removed instances.
        """
        return cast(
            "Sequence[ModelT]",
            await self.repository.delete_many(
                item_ids=item_ids,
                auto_commit=auto_commit,
                auto_expunge=auto_expunge,
                id_attribute=id_attribute,
                chunk_size=chunk_size,
                error_messages=error_messages,
                load=load,
                execution_options=execution_options,
                uniquify=self._get_uniquify(uniquify),
            ),
        )

    async def delete_where(
        self,
        *filters: Union[StatementFilter, ColumnElement[bool]],
        auto_commit: Optional[bool] = None,
        auto_expunge: Optional[bool] = None,
        error_messages: Union[ErrorMessages, None, EmptyType] = Empty,
        sanity_check: bool = True,
        load: Optional[LoadSpec] = None,
        execution_options: Optional[dict[str, Any]] = None,
        uniquify: Optional[bool] = None,
        **kwargs: Any,
    ) -> Sequence[ModelT]:
        """Wrap repository scalars operation.

        Args:
            *filters: Types for specific filtering operations.
            auto_expunge: Remove object from session before returning.
            auto_commit: Commit objects before returning.
            error_messages: An optional dictionary of templates to use
                for friendlier error messages to clients
            sanity_check: When true, the length of selected instances is compared to the deleted row count
            load: Set default relationships to be loaded
            execution_options: Set default execution options
            uniquify: Optionally apply the ``unique()`` method to results before returning.
            **kwargs: Instance attribute value filters.

        Returns:
            The list of instances deleted from the repository.
        """
        return cast(
            "Sequence[ModelT]",
            await self.repository.delete_where(
                *filters,
                auto_commit=auto_commit,
                auto_expunge=auto_expunge,
                error_messages=error_messages,
                sanity_check=sanity_check,
                load=load,
                execution_options=execution_options,
                uniquify=self._get_uniquify(uniquify),
                **kwargs,
            ),
        )
