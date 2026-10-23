"""Service object implementation for SQLAlchemy.

RepositoryService object is generic on the domain model type which
should be a SQLAlchemy model.
"""

from collections.abc import AsyncGenerator, Iterable, Sequence
from contextlib import asynccontextmanager
from functools import cached_property
from typing import Any, ClassVar, Generic, List, Optional, Union, cast, get_args, get_origin

from sqlalchemy import Select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio.scoping import async_scoped_session
from sqlalchemy.orm import InstrumentedAttribute
from sqlalchemy.sql import ColumnElement
from sqlalchemy.sql.selectable import ForUpdateParameter
from typing_extensions import Self

from advanced_alchemy.base import ModelProtocol, model_to_dict
from advanced_alchemy.config.asyncio import SQLAlchemyAsyncConfig
from advanced_alchemy.exceptions import AdvancedAlchemyError, ErrorMessages, ImproperConfigurationError, RepositoryError
from advanced_alchemy.filters import StatementFilter
from advanced_alchemy.repository import (
    SQLAlchemyAsyncQueryRepository,
    SQLAlchemyAsyncRepository,
)
from advanced_alchemy.repository._util import LoadSpec, model_from_dict, resolve_generic_type_args
from advanced_alchemy.repository.typing import ModelT, OrderingPair, PrimaryKeyType, SQLAlchemyAsyncRepositoryT
from advanced_alchemy.service._util import ResultConverter, resolve_item_ids
from advanced_alchemy.utils.dataclass import Empty, EmptyType
from advanced_alchemy.utils.deprecation import warn_deprecation
from advanced_alchemy.utils.serialization import (
    BulkModelDictT,
    ModelDictListT,
    ModelDictT,
    SchemaDumpConfig,
    is_attrs_instance,
    is_dataclass,
    is_dict,
    is_dto_data,
    is_msgspec_struct,
    is_pydantic_model,
    is_sqlmodel_table_model,
    schema_dump,
)


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
    ) -> AsyncGenerator[Self, None]:
        """Context manager that returns instance of service object.

        Handles construction of the database session._create_select_for_model

        Raises:
            AdvancedAlchemyError: If no configuration or session is provided.

        Yields:
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
    match_fields: ClassVar[Optional[Union[List[str], str]]] = None
    """List of dialects that prefer to use ``field.id = ANY(:1)`` instead of ``field.id IN (...)``."""
    uniquify: ClassVar[bool] = False
    """Optionally apply the ``unique()`` method to results before returning."""
    count_with_window_function: ClassVar[bool] = True
    """Use an analytical window function to count results.  This allows the count to be performed in a single query."""
    include_deleted: ClassVar[bool] = False
    """Default behavior for whether to include soft-deleted records in read queries."""
    schema_dump_config: ClassVar[SchemaDumpConfig] = SchemaDumpConfig()
    """Default dump behavior when schema-like input is converted into a model."""
    _model_type: ClassVar[Optional[type[Any]]] = None
    _repository_instance: SQLAlchemyAsyncRepositoryT

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        args = resolve_generic_type_args(cls, SQLAlchemyAsyncRepositoryReadService)
        model_cls: Optional[type[Any]] = None
        repo_cls: Optional[type[Any]] = None

        if len(args) >= 1 and isinstance(args[0], type):
            model_cls = args[0]
            if "_model_type" not in cls.__dict__:
                cls._model_type = model_cls
        elif getattr(cls, "_model_type", None) is not None:
            model_cls = cls._model_type

        if len(args) > 1:
            raw_repo = args[1]
            origin_repo = get_origin(raw_repo)
            if origin_repo is not None and isinstance(origin_repo, type):
                repo_cls = origin_repo
                repo_args = get_args(raw_repo)
                if model_cls is None and repo_args and isinstance(repo_args[0], type):
                    model_cls = repo_args[0]
                    if "_model_type" not in cls.__dict__:
                        cls._model_type = model_cls
            elif isinstance(raw_repo, type):
                repo_cls = raw_repo

        if "repository_type" not in cls.__dict__:
            if repo_cls is not None:
                if getattr(repo_cls, "model_type", None) is not None or model_cls is None:
                    cls.repository_type = repo_cls
                else:
                    cls.repository_type = cast(
                        "Any",
                        type(
                            f"{model_cls.__name__}{repo_cls.__name__}",
                            (repo_cls,),
                            {"model_type": model_cls},
                        ),
                    )
            elif getattr(cls, "repository_type", None) is None and model_cls is not None:
                cls.repository_type = cast(
                    "Any",
                    type(
                        f"{model_cls.__name__}Repository",
                        (SQLAlchemyAsyncRepository,),
                        {"model_type": model_cls},
                    ),
                )

    def __init__(
        self,
        session: Union[AsyncSession, async_scoped_session[AsyncSession]],
        *,
        statement: Optional[Select[Any]] = None,
        model_type: Optional[type[ModelT]] = None,
        repository_type: Optional[type[SQLAlchemyAsyncRepositoryT]] = None,
        auto_expunge: bool = False,
        auto_refresh: bool = True,
        auto_commit: bool = False,
        order_by: Optional[Union[List[OrderingPair], OrderingPair]] = None,
        error_messages: Optional[Union[ErrorMessages, EmptyType]] = Empty,
        wrap_exceptions: bool = True,
        load: Optional[LoadSpec] = None,
        execution_options: Optional[dict[str, Any]] = None,
        uniquify: Optional[bool] = None,
        count_with_window_function: Optional[bool] = None,
        include_deleted: Optional[bool] = None,
        **repo_kwargs: Any,
    ) -> None:
        """Configure the service object.

        Args:
            session: Session managing the unit-of-work for the operation.
            statement: To facilitate customization of the underlying select query.
            model_type: Optional SQLAlchemy model type when instantiating directly without subclassing.
            repository_type: Optional repository class override when instantiating directly.
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
            include_deleted: Whether to include soft-deleted records by default.
            **repo_kwargs: passed as keyword args to repo instantiation.
        """
        load = load if load is not None else self.loader_options
        execution_options = execution_options if execution_options is not None else self.execution_options
        count_with_window_function = (
            count_with_window_function if count_with_window_function is not None else self.count_with_window_function
        )
        resolved_include_deleted = include_deleted if include_deleted is not None else self.include_deleted
        if include_deleted is not None or self.include_deleted:
            repo_kwargs.setdefault("include_deleted", resolved_include_deleted)
        resolved_repo_type = repository_type if repository_type is not None else getattr(self, "repository_type", None)
        resolved_model_type = model_type if model_type is not None else getattr(self, "_model_type", None)
        if resolved_repo_type is None:
            if resolved_model_type is not None:
                resolved_repo_type = cast("Any", SQLAlchemyAsyncRepository)
            else:
                msg = (
                    "Service 'repository_type' or 'model_type' is not configured. Specify the model via "
                    "generic type parameter (e.g. SQLAlchemyAsyncRepositoryService[Model]), "
                    "class attribute 'repository_type = Repo', or keyword argument 'model_type=Model'."
                )
                raise ImproperConfigurationError(msg)
        if resolved_model_type is not None and getattr(resolved_repo_type, "model_type", None) is None:
            repo_kwargs.setdefault("model_type", resolved_model_type)
        self.repository_type = resolved_repo_type
        self._repository_instance: SQLAlchemyAsyncRepositoryT = resolved_repo_type(  # type: ignore[assignment]
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
        """Return the repository instance.

        Raises:
            ImproperConfigurationError: If the repository is not initialized.

        Returns:
            The repository instance.
        """
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
        error_messages: Optional[Union[ErrorMessages, EmptyType]] = Empty,
        load: Optional[LoadSpec] = None,
        execution_options: Optional[dict[str, Any]] = None,
        uniquify: Optional[bool] = None,
        include_deleted: Optional[bool] = None,
        bind_group: Optional[str] = None,
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
            include_deleted: Whether to include soft-deleted records.
            bind_group: The bind group to use for the operation.
            **kwargs: key value pairs of filter types.

        Returns:
           A count of the collection, filtered, but ignoring pagination.
        """
        if include_deleted is not None:
            kwargs["include_deleted"] = include_deleted
        return await self.repository.count(
            *filters,
            statement=statement,
            error_messages=error_messages,
            load=load,
            execution_options=execution_options,
            uniquify=self._get_uniquify(uniquify),
            bind_group=bind_group,
            **kwargs,
        )

    async def exists(
        self,
        *filters: Union[StatementFilter, ColumnElement[bool]],
        error_messages: Optional[Union[ErrorMessages, EmptyType]] = Empty,
        load: Optional[LoadSpec] = None,
        execution_options: Optional[dict[str, Any]] = None,
        uniquify: Optional[bool] = None,
        include_deleted: Optional[bool] = None,
        bind_group: Optional[str] = None,
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
            include_deleted: Whether to include soft-deleted records.
            bind_group: The bind group to use for the operation.
            **kwargs: Keyword arguments for attribute based filtering.

        Returns:
            Representation of instance with identifier `item_id`.
        """
        if include_deleted is not None:
            kwargs["include_deleted"] = include_deleted
        return await self.repository.exists(
            *filters,
            error_messages=error_messages,
            load=load,
            execution_options=execution_options,
            uniquify=self._get_uniquify(uniquify),
            bind_group=bind_group,
            **kwargs,
        )

    async def get(
        self,
        item_id: PrimaryKeyType,
        *,
        statement: Optional[Select[tuple[ModelT]]] = None,
        id_attribute: Optional[Union[str, InstrumentedAttribute[Any]]] = None,
        auto_expunge: Optional[bool] = None,
        error_messages: Optional[Union[ErrorMessages, EmptyType]] = Empty,
        load: Optional[LoadSpec] = None,
        execution_options: Optional[dict[str, Any]] = None,
        uniquify: Optional[bool] = None,
        include_deleted: Optional[bool] = None,
        bind_group: Optional[str] = None,
    ) -> ModelT:
        """Wrap repository scalar operation.

        Args:
            item_id: Identifier of instance to be retrieved.
                For single primary key models, pass a scalar value (int, str, UUID, etc.).
                For composite primary key models, pass a tuple of values in column order,
                or a dict mapping attribute names to values.
            auto_expunge: Remove object from session before returning.
            statement: To facilitate customization of the underlying select query.
            id_attribute: Allows customization of the unique identifier to use for model fetching.
                Defaults to `id`, but can reference any surrogate or candidate key for the table.
                Only applicable for single primary key models.
            error_messages: An optional dictionary of templates to use
                for friendlier error messages to clients
            load: Set relationships to be loaded
            execution_options: Set default execution options
            uniquify: Optionally apply the ``unique()`` method to results before returning.
            include_deleted: Whether to include soft-deleted records.
            bind_group: The bind group to use for the operation.

        Returns:
            Representation of instance with identifier `item_id`.

        Examples:
            # Single primary key
            >>> user = await service.get(123)

            # Composite primary key (tuple format)
            >>> assignment = await service.get((user_id, role_id))

            # Composite primary key (dict format)
            >>> assignment = await service.get({"user_id": 1, "role_id": 5})
        """
        extra_kwargs: dict[str, Any] = {}
        if include_deleted is not None:
            extra_kwargs["include_deleted"] = include_deleted
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
                bind_group=bind_group,
                **extra_kwargs,
            ),
        )

    async def get_one(
        self,
        *filters: Union[StatementFilter, ColumnElement[bool]],
        statement: Optional[Select[tuple[ModelT]]] = None,
        auto_expunge: Optional[bool] = None,
        load: Optional[LoadSpec] = None,
        error_messages: Optional[Union[ErrorMessages, EmptyType]] = Empty,
        execution_options: Optional[dict[str, Any]] = None,
        uniquify: Optional[bool] = None,
        with_for_update: ForUpdateParameter = None,
        include_deleted: Optional[bool] = None,
        bind_group: Optional[str] = None,
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
            with_for_update: Optional FOR UPDATE clause / parameters to apply to the SELECT statement.
            include_deleted: Whether to include soft-deleted records.
            bind_group: The bind group to use for the operation.
            **kwargs: Identifier of the instance to be retrieved.

        Returns:
            Representation of instance with identifier `item_id`.
        """
        if include_deleted is not None:
            kwargs["include_deleted"] = include_deleted
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
                with_for_update=with_for_update,
                bind_group=bind_group,
                **kwargs,
            ),
        )

    async def get_one_or_none(
        self,
        *filters: Union[StatementFilter, ColumnElement[bool]],
        statement: Optional[Select[tuple[ModelT]]] = None,
        auto_expunge: Optional[bool] = None,
        error_messages: Optional[Union[ErrorMessages, EmptyType]] = Empty,
        load: Optional[LoadSpec] = None,
        execution_options: Optional[dict[str, Any]] = None,
        uniquify: Optional[bool] = None,
        with_for_update: ForUpdateParameter = None,
        include_deleted: Optional[bool] = None,
        bind_group: Optional[str] = None,
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
            with_for_update: Optional FOR UPDATE clause / parameters to apply to the SELECT statement.
            include_deleted: Whether to include soft-deleted records.
            bind_group: The bind group to use for the operation.
            **kwargs: Identifier of the instance to be retrieved.

        Returns:
            Representation of instance with identifier `item_id`.
        """
        if include_deleted is not None:
            kwargs["include_deleted"] = include_deleted
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
                with_for_update=with_for_update,
                bind_group=bind_group,
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
        schema_dump_config: Optional[SchemaDumpConfig] = None,
    ) -> ModelT:
        """Parse and Convert input into a model.

        Args:
            data: Representations to be created.
            operation: Optional operation flag so that you can provide behavior based on CRUD operation
            schema_dump_config: Optional schema dump behavior for this conversion.

        Returns:
            Representation of created instances.
        """
        dump_config = schema_dump_config if schema_dump_config is not None else self.schema_dump_config
        if operation == "create":
            data = await self.to_model_on_create(data)
        elif operation == "update":
            data = await self.to_model_on_update(data)
        elif operation == "delete":
            data = await self.to_model_on_delete(data)
        elif operation == "upsert":
            data = await self.to_model_on_upsert(data)
        if isinstance(data, self.model_type):
            return data
        if is_dict(data):
            return model_from_dict(self.model_type, **data)
        if is_sqlmodel_table_model(data):
            return model_from_dict(self.model_type, **model_to_dict(cast("ModelProtocol", data)))
        if is_pydantic_model(data) or is_msgspec_struct(data) or is_attrs_instance(data) or is_dataclass(data):
            return model_from_dict(
                self.model_type,
                **schema_dump(data, config=dump_config),
            )

        if is_dto_data(data):
            return cast("ModelT", data.create_instance())

        # Fallback for objects with __dict__ (e.g., regular classes)
        if hasattr(data, "__dict__") and not isinstance(data, self.model_type):
            return model_from_dict(
                self.model_type,
                **data.__dict__,
            )

        return cast("ModelT", data)

    async def get_many_and_count(
        self,
        *filters: Union[StatementFilter, ColumnElement[bool]],
        statement: Optional[Select[tuple[ModelT]]] = None,
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
            use_cache: Whether to use the repository cache for this query.
            include_deleted: Whether to include soft-deleted records.
            bind_group: Optional routing group to use for the operation.
            **kwargs: Instance attribute value filters.

        Returns:
            List of instances and count of total collection, ignoring pagination.
        """
        if include_deleted is not None:
            kwargs["include_deleted"] = include_deleted
        return cast(
            "tuple[Sequence[ModelT], int]",
            await self.repository.get_many_and_count(
                *filters,
                statement=statement,
                auto_expunge=auto_expunge,
                count_with_window_function=count_with_window_function,
                order_by=order_by,
                error_messages=error_messages,
                load=load,
                execution_options=execution_options,
                uniquify=self._get_uniquify(uniquify),
                use_cache=use_cache,
                bind_group=bind_group,
                **kwargs,
            ),
        )

    async def list_and_count(
        self,
        *filters: Union[StatementFilter, ColumnElement[bool]],
        statement: Optional[Select[tuple[ModelT]]] = None,
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
    ) -> tuple[Sequence[ModelT], int]:
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
        return await self.get_many_and_count(
            *filters,
            statement=statement,
            auto_expunge=auto_expunge,
            count_with_window_function=count_with_window_function,
            order_by=order_by,
            error_messages=error_messages,
            load=load,
            execution_options=execution_options,
            uniquify=uniquify,
            use_cache=use_cache,
            include_deleted=include_deleted,
            bind_group=bind_group,
            **kwargs,
        )

    @classmethod
    @asynccontextmanager
    async def new(
        cls,
        session: Optional[Union[AsyncSession, async_scoped_session[AsyncSession]]] = None,
        statement: Optional[Select[tuple[ModelT]]] = None,
        config: Optional[SQLAlchemyAsyncConfig] = None,
        model_type: Optional[type[ModelT]] = None,
        repository_type: Optional[type[SQLAlchemyAsyncRepositoryT]] = None,
        error_messages: Optional[Union[ErrorMessages, EmptyType]] = Empty,
        load: Optional[LoadSpec] = None,
        execution_options: Optional[dict[str, Any]] = None,
        uniquify: Optional[bool] = None,
        count_with_window_function: Optional[bool] = None,
        include_deleted: Optional[bool] = None,
    ) -> AsyncGenerator[Self, None]:
        """Context manager that returns instance of service object.

        Handles construction of the database session._create_select_for_model

        Raises:
            AdvancedAlchemyError: If no configuration or session is provided.

        Yields:
            The service object instance.
        """
        if not config and not session:
            raise AdvancedAlchemyError(detail="Please supply an optional configuration or session to use.")

        if session:
            yield cls(
                statement=statement,
                session=session,
                model_type=model_type,
                repository_type=repository_type,
                error_messages=error_messages,
                load=load,
                execution_options=execution_options,
                uniquify=uniquify,
                count_with_window_function=count_with_window_function,
                include_deleted=include_deleted,
            )
        elif config:
            async with config.get_session() as db_session:
                yield cls(
                    statement=statement,
                    session=db_session,
                    model_type=model_type,
                    repository_type=repository_type,
                    error_messages=error_messages,
                    load=load,
                    execution_options=execution_options,
                    uniquify=uniquify,
                    count_with_window_function=count_with_window_function,
                    include_deleted=include_deleted,
                )

    async def get_many(
        self,
        *filters: Union[StatementFilter, ColumnElement[bool]],
        statement: Optional[Select[tuple[ModelT]]] = None,
        auto_expunge: Optional[bool] = None,
        order_by: Optional[Union[List[OrderingPair], OrderingPair]] = None,
        error_messages: Optional[Union[ErrorMessages, EmptyType]] = Empty,
        load: Optional[LoadSpec] = None,
        execution_options: Optional[dict[str, Any]] = None,
        uniquify: Optional[bool] = None,
        use_cache: bool = True,
        include_deleted: Optional[bool] = None,
        bind_group: Optional[str] = None,
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
            use_cache: Whether to use the repository cache for this query.
            include_deleted: Whether to include soft-deleted records.
            bind_group: Optional routing group to use for the operation.
            **kwargs: Instance attribute value filters.

        Returns:
            The list of instances retrieved from the repository.
        """
        if include_deleted is not None:
            kwargs["include_deleted"] = include_deleted
        return cast(
            "Sequence[ModelT]",
            await self.repository.get_many(
                *filters,
                statement=statement,
                auto_expunge=auto_expunge,
                order_by=order_by,
                error_messages=error_messages,
                load=load,
                execution_options=execution_options,
                uniquify=self._get_uniquify(uniquify),
                use_cache=use_cache,
                bind_group=bind_group,
                **kwargs,
            ),
        )

    async def list(
        self,
        *filters: Union[StatementFilter, ColumnElement[bool]],
        statement: Optional[Select[tuple[ModelT]]] = None,
        auto_expunge: Optional[bool] = None,
        order_by: Optional[Union[List[OrderingPair], OrderingPair]] = None,
        error_messages: Optional[Union[ErrorMessages, EmptyType]] = Empty,
        load: Optional[LoadSpec] = None,
        execution_options: Optional[dict[str, Any]] = None,
        uniquify: Optional[bool] = None,
        use_cache: bool = True,
        include_deleted: Optional[bool] = None,
        bind_group: Optional[str] = None,
        **kwargs: Any,
    ) -> Sequence[ModelT]:
        """Wrap repository scalars operation.

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
        return await self.get_many(
            *filters,
            statement=statement,
            auto_expunge=auto_expunge,
            order_by=order_by,
            error_messages=error_messages,
            load=load,
            execution_options=execution_options,
            uniquify=uniquify,
            use_cache=use_cache,
            include_deleted=include_deleted,
            bind_group=bind_group,
            **kwargs,
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
        error_messages: Optional[Union[ErrorMessages, EmptyType]] = Empty,
        bind_group: Optional[str] = None,
        schema_dump_config: Optional[SchemaDumpConfig] = None,
    ) -> "ModelT":
        """Wrap repository instance creation.

        Args:
            data: Representation to be created.
            auto_expunge: Remove object from session before returning.
            auto_refresh: Refresh object from session before returning.
            auto_commit: Commit objects before returning.
            error_messages: An optional dictionary of templates to use
                for friendlier error messages to clients
            bind_group: Optional routing group to use for the operation.
            schema_dump_config: Optional schema dump behavior for this operation.

        Returns:
            Representation of created instance.
        """
        data = await self.to_model(data, "create", schema_dump_config=schema_dump_config)
        return cast(
            "ModelT",
            await self.repository.add(
                data=data,
                auto_commit=auto_commit,
                auto_expunge=auto_expunge,
                auto_refresh=auto_refresh,
                error_messages=error_messages,
                bind_group=bind_group,
            ),
        )

    async def create_many(
        self,
        data: "BulkModelDictT[ModelT]",
        *,
        auto_commit: Optional[bool] = None,
        auto_expunge: Optional[bool] = None,
        error_messages: Optional[Union[ErrorMessages, EmptyType]] = Empty,
        bind_group: Optional[str] = None,
        schema_dump_config: Optional[SchemaDumpConfig] = None,
    ) -> Sequence[ModelT]:
        """Wrap repository bulk instance creation.

        Args:
            data: Representations to be created.
            auto_expunge: Remove object from session before returning.
            auto_commit: Commit objects before returning.
            error_messages: An optional dictionary of templates to use
                for friendlier error messages to clients
            bind_group: Optional routing group to use for the operation.
            schema_dump_config: Optional schema dump behavior for this operation.

        Returns:
            Representation of created instances.
        """
        if is_dto_data(data):
            data = data.create_instance()
        data = [
            (await self.to_model(datum, "create", schema_dump_config=schema_dump_config))
            for datum in cast("ModelDictListT[ModelT]", data)
        ]
        return cast(
            "Sequence[ModelT]",
            await self.repository.add_many(
                data=cast("List[ModelT]", data),  # pyright: ignore[reportUnnecessaryCast]
                auto_commit=auto_commit,
                auto_expunge=auto_expunge,
                error_messages=error_messages,
                bind_group=bind_group,
            ),
        )

    async def update(
        self,
        data: "ModelDictT[ModelT]",
        item_id: Optional[Any] = None,
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
        schema_dump_config: Optional[SchemaDumpConfig] = None,
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
            bind_group: Optional routing group to use for the operation.
            schema_dump_config: Optional schema dump behavior for this operation.

        Raises:
            RepositoryError: If no configuration or session is provided.

        Returns:
            Updated representation.
        """
        data = await self.to_model(data, "update", schema_dump_config=schema_dump_config)

        if item_id is not None:
            if id_attribute is None and self.repository.has_composite_pk:
                self.repository.set_primary_key_value(data, item_id)
            else:
                self.repository.set_id_attribute_value(  # pyright: ignore[reportUnknownMemberType]
                    item_id,
                    data,
                    id_attribute=id_attribute,
                )
        elif id_attribute is None and self.repository.has_composite_pk:
            if not self.repository.has_primary_key_values(data):
                pk_names = ", ".join(self.repository.pk_attr_names)
                msg = f"Could not identify composite PK values. Required attributes: {pk_names}"
                raise RepositoryError(msg)
        elif (
            self.repository.get_id_attribute_value(  # pyright: ignore[reportUnknownMemberType]
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
                bind_group=bind_group,
            ),
        )

    async def update_many(
        self,
        data: "BulkModelDictT[ModelT]",
        *,
        auto_commit: Optional[bool] = None,
        auto_expunge: Optional[bool] = None,
        error_messages: Optional[Union[ErrorMessages, EmptyType]] = Empty,
        load: Optional[LoadSpec] = None,
        execution_options: Optional[dict[str, Any]] = None,
        uniquify: Optional[bool] = None,
        bind_group: Optional[str] = None,
        schema_dump_config: Optional[SchemaDumpConfig] = None,
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
            bind_group: Optional routing group to use for the operation.
            schema_dump_config: Optional schema dump behavior for this operation.

        Returns:
            Representation of updated instances.
        """
        if is_dto_data(data):
            data = data.create_instance()
        data = [
            (await self.to_model(datum, "update", schema_dump_config=schema_dump_config))
            for datum in cast("ModelDictListT[ModelT]", data)
        ]
        return cast(
            "Sequence[ModelT]",
            await self.repository.update_many(
                cast("List[ModelT]", data),  # pyright: ignore[reportUnnecessaryCast]
                auto_commit=auto_commit,
                auto_expunge=auto_expunge,
                error_messages=error_messages,
                load=load,
                execution_options=execution_options,
                uniquify=self._get_uniquify(uniquify),
                bind_group=bind_group,
            ),
        )

    async def upsert(
        self,
        data: "ModelDictT[ModelT]",
        item_id: Optional[Any] = None,
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
        schema_dump_config: Optional[SchemaDumpConfig] = None,
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
            bind_group: Optional routing group to use for the operation.
            schema_dump_config: Optional schema dump behavior for this operation.

        Returns:
            Updated or created representation.
        """
        data = await self.to_model(data, "upsert", schema_dump_config=schema_dump_config)
        # Handle ID extraction and setting for single-column PKs
        # For composite PKs, the repository's upsert() handles this directly
        if item_id is None:
            if self.repository.has_composite_pk:
                # For composite PKs, extract the full PK if present
                if self.repository.has_primary_key_values(data):
                    item_id = self.repository.get_primary_key_value(data)
            else:
                item_id = self.repository.get_id_attribute_value(item=data)  # pyright: ignore[reportUnknownMemberType]
        if item_id is not None and not self.repository.has_composite_pk:
            # Only set single-column ID (composite PK values are already on the instance)
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
                bind_group=bind_group,
            ),
        )

    async def upsert_many(
        self,
        data: "BulkModelDictT[ModelT]",
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
        schema_dump_config: Optional[SchemaDumpConfig] = None,
        chunk_size: Optional[int] = None,
    ) -> Sequence[ModelT]:
        """Wrap repository upsert operation.

        Args:
            data: Instance to update existing, or be created.
            auto_expunge: Remove object from session before returning.
            auto_commit: Commit objects before returning.
            no_merge: When True, forces the SELECT+partition fallback path even on
                dialects that support a native upsert primitive. Use for callers
                that need deterministic per-row UPDATE/INSERT semantics or to
                bypass native dispatch for testing.
            match_fields: a list of keys to use to match the existing model.  When
                empty, all fields are matched.
            error_messages: An optional dictionary of templates to use
                for friendlier error messages to clients
            load: Set default relationships to be loaded
            execution_options: Set default execution options
            uniquify: Optionally apply the ``unique()`` method to results before returning.
            bind_group: Optional routing group to use for the operation.
            schema_dump_config: Optional schema dump behavior for this operation.
            chunk_size: Optional parameter cap for each native statement. Defaults
                to the active dialect's ``insertmanyvalues_max_parameters``;
                native upserts also respect ``insertmanyvalues_page_size``. Must be
                greater than zero.

        Returns:
            Updated or created representation.
        """
        if is_dto_data(data):
            data = data.create_instance()
        data = [
            (await self.to_model(datum, "upsert", schema_dump_config=schema_dump_config))
            for datum in cast("ModelDictListT[ModelT]", data)
        ]
        return cast(
            "Sequence[ModelT]",
            await self.repository.upsert_many(
                data=cast("List[ModelT]", data),  # pyright: ignore[reportUnnecessaryCast]
                auto_expunge=auto_expunge,
                auto_commit=auto_commit,
                no_merge=no_merge,
                match_fields=match_fields,
                error_messages=error_messages,
                load=load,
                execution_options=execution_options,
                uniquify=self._get_uniquify(uniquify),
                bind_group=bind_group,
                chunk_size=chunk_size,
            ),
        )

    async def get_or_upsert(
        self,
        *filters: Union[StatementFilter, ColumnElement[bool]],
        match_fields: Optional[Union[List[str], str]] = None,
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
        schema_dump_config: Optional[SchemaDumpConfig] = None,
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
            bind_group: Optional routing group to use for the operation.
            schema_dump_config: Optional schema dump behavior for this operation.
            **kwargs: Identifier of the instance to be retrieved.

        Returns:
            Representation of created instance.
        """
        match_fields = match_fields or self.match_fields
        validated_model = await self.to_model(kwargs, "create", schema_dump_config=schema_dump_config)
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
                bind_group=bind_group,
                **model_to_dict(validated_model),
            ),
        )

    async def get_and_update(
        self,
        *filters: Union[StatementFilter, ColumnElement[bool]],
        match_fields: Optional[Union[List[str], str]] = None,
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
        schema_dump_config: Optional[SchemaDumpConfig] = None,
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
            bind_group: Optional routing group to use for the operation.
            schema_dump_config: Optional schema dump behavior for this operation.
            **kwargs: Identifier of the instance to be retrieved.

        Returns:
            Representation of updated instance.
        """
        match_fields = match_fields or self.match_fields
        validated_model = await self.to_model(kwargs, "update", schema_dump_config=schema_dump_config)
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
                bind_group=bind_group,
                **model_to_dict(validated_model),
            ),
        )

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
        """Wrap repository delete operation.

        Args:
            item_id: Identifier of instance to be deleted.
                For single primary key models, pass a scalar value (int, str, UUID, etc.).
                For composite primary key models, pass a tuple of values in column order,
                or a dict mapping attribute names to values.
            auto_commit: Commit objects before returning.
            auto_expunge: Remove object from session before returning.
            id_attribute: Allows customization of the unique identifier to use for model fetching.
                Defaults to `id`, but can reference any surrogate or candidate key for the table.
                Only applicable for single primary key models.
            error_messages: An optional dictionary of templates to use
                for friendlier error messages to clients
            load: Set default relationships to be loaded
            execution_options: Set default execution options
            uniquify: Optionally apply the ``unique()`` method to results before returning.
            include_deleted: Whether to include soft-deleted records when hard-deleting.
            bind_group: Optional routing group to use for the operation.

        Returns:
            Representation of the deleted instance.

        Examples:
            # Single primary key
            >>> deleted_user = await service.delete(123)

            # Composite primary key (tuple format)
            >>> deleted = await service.delete((user_id, role_id))

            # Composite primary key (dict format)
            >>> deleted = await service.delete({"user_id": 1, "role_id": 5})
        """
        extra_kwargs: dict[str, Any] = {}
        if not include_deleted:
            extra_kwargs["include_deleted"] = False
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
                bind_group=bind_group,
                **extra_kwargs,
            ),
        )

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
    ) -> Sequence[ModelT]:
        """Wrap repository bulk instance deletion.

        Args:
            item_ids: List of identifiers of instances to be deleted.
                For single primary key models, pass a list of scalar values.
                For composite primary key models, pass a list of tuples or dicts.
                Model instances may also be passed in place of identifiers, and the list
                may mix instances with raw identifier values.
            auto_expunge: Remove object from session before returning.
            auto_commit: Commit objects before returning.
            id_attribute: Allows customization of the unique identifier to use for model fetching.
                Defaults to `id`, but can reference any surrogate or candidate key for the table.
                Only applicable for single primary key models.
            chunk_size: Allows customization of the ``insertmanyvalues_max_parameters`` setting for the driver.
                Defaults to the active dialect's limit, with a conservative `950`
                fallback. Must be greater than zero.
            error_messages: An optional dictionary of templates to use
                for friendlier error messages to clients
            load: Set default relationships to be loaded
            execution_options: Set default execution options
            uniquify: Optionally apply the ``unique()`` method to results before returning.
            include_deleted: Whether to include soft-deleted records when hard-deleting.
            bind_group: Optional routing group to use for the operation.

        Returns:
            Representation of removed instances.

        Examples:
            # Single primary key
            >>> deleted = await service.delete_many([1, 2, 3])

            # Composite primary key (tuple format)
            >>> deleted = await service.delete_many(
            ...     [
            ...         (user_id_1, role_id_1),
            ...         (user_id_2, role_id_2),
            ...     ]
            ... )

            # Composite primary key (dict format)
            >>> deleted = await service.delete_many(
            ...     [
            ...         {"user_id": 1, "role_id": 5},
            ...         {"user_id": 1, "role_id": 6},
            ...     ]
            ... )
        """
        extra_kwargs: dict[str, Any] = {}
        if not include_deleted:
            extra_kwargs["include_deleted"] = False
        return cast(
            "Sequence[ModelT]",
            await self.repository.delete_many(
                item_ids=resolve_item_ids(
                    item_ids,
                    model_type=self.model_type,
                    repository=self.repository,
                    id_attribute=id_attribute,
                ),
                auto_commit=auto_commit,
                auto_expunge=auto_expunge,
                id_attribute=id_attribute,
                chunk_size=chunk_size,
                error_messages=error_messages,
                load=load,
                execution_options=execution_options,
                uniquify=self._get_uniquify(uniquify),
                bind_group=bind_group,
                **extra_kwargs,
            ),
        )

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
            include_deleted: Whether to include soft-deleted records when hard-deleting.
            bind_group: Optional routing group to use for the operation.
            **kwargs: Instance attribute value filters.

        Returns:
            The list of instances deleted from the repository.
        """
        if not include_deleted:
            kwargs["include_deleted"] = False
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
                bind_group=bind_group,
                **kwargs,
            ),
        )

    async def soft_delete(
        self,
        item_id: PrimaryKeyType,
        *,
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
        """Soft-delete a single instance by identifier."""
        return cast(
            "ModelT",
            await self.repository.soft_delete(
                item_id=item_id,
                auto_commit=auto_commit,
                auto_expunge=auto_expunge,
                auto_refresh=auto_refresh,
                id_attribute=id_attribute,
                error_messages=error_messages,
                load=load,
                execution_options=execution_options,
                uniquify=self._get_uniquify(uniquify),
                bind_group=bind_group,
            ),
        )

    async def soft_delete_many(
        self,
        item_ids: List[PrimaryKeyType],
        *,
        auto_commit: Optional[bool] = None,
        auto_expunge: Optional[bool] = None,
        id_attribute: Optional[Union[str, InstrumentedAttribute[Any]]] = None,
        error_messages: Optional[Union[ErrorMessages, EmptyType]] = Empty,
        load: Optional[LoadSpec] = None,
        execution_options: Optional[dict[str, Any]] = None,
        uniquify: Optional[bool] = None,
        bind_group: Optional[str] = None,
    ) -> Sequence[ModelT]:
        """Soft-delete multiple instances by identifiers or model instances."""
        return cast(
            "Sequence[ModelT]",
            await self.repository.soft_delete_many(
                item_ids=resolve_item_ids(
                    item_ids,
                    model_type=self.model_type,
                    repository=self.repository,
                    id_attribute=id_attribute,
                ),
                auto_commit=auto_commit,
                auto_expunge=auto_expunge,
                id_attribute=id_attribute,
                error_messages=error_messages,
                load=load,
                execution_options=execution_options,
                uniquify=self._get_uniquify(uniquify),
                bind_group=bind_group,
            ),
        )

    async def restore(
        self,
        item_id: PrimaryKeyType,
        *,
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
        """Restore a soft-deleted instance by identifier."""
        return cast(
            "ModelT",
            await self.repository.restore(
                item_id=item_id,
                auto_commit=auto_commit,
                auto_expunge=auto_expunge,
                auto_refresh=auto_refresh,
                id_attribute=id_attribute,
                error_messages=error_messages,
                load=load,
                execution_options=execution_options,
                uniquify=self._get_uniquify(uniquify),
                bind_group=bind_group,
            ),
        )

    async def restore_many(
        self,
        item_ids: List[PrimaryKeyType],
        *,
        auto_commit: Optional[bool] = None,
        auto_expunge: Optional[bool] = None,
        id_attribute: Optional[Union[str, InstrumentedAttribute[Any]]] = None,
        error_messages: Optional[Union[ErrorMessages, EmptyType]] = Empty,
        load: Optional[LoadSpec] = None,
        execution_options: Optional[dict[str, Any]] = None,
        uniquify: Optional[bool] = None,
        bind_group: Optional[str] = None,
    ) -> Sequence[ModelT]:
        """Restore multiple soft-deleted instances by identifiers or model instances."""
        return cast(
            "Sequence[ModelT]",
            await self.repository.restore_many(
                item_ids=resolve_item_ids(
                    item_ids,
                    model_type=self.model_type,
                    repository=self.repository,
                    id_attribute=id_attribute,
                ),
                auto_commit=auto_commit,
                auto_expunge=auto_expunge,
                id_attribute=id_attribute,
                error_messages=error_messages,
                load=load,
                execution_options=execution_options,
                uniquify=self._get_uniquify(uniquify),
                bind_group=bind_group,
            ),
        )
