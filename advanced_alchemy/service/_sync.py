# Do not edit this file directly. It has been autogenerated from
# advanced_alchemy/service/_async.py
"""Service object implementation for SQLAlchemy.

RepositoryService object is generic on the domain model type which
should be a SQLAlchemy model.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Generic, Iterable, cast

from advanced_alchemy.repository._util import model_from_dict
from advanced_alchemy.repository.typing import ModelT

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy import Select, StatementLambdaElement
    from sqlalchemy.orm import InstrumentedAttribute, Session
    from sqlalchemy.sql import ColumnElement

    from advanced_alchemy.filters import FilterTypes
    from advanced_alchemy.repository import SQLAlchemySyncRepository
    from advanced_alchemy.service.typing import FilterTypeT


class SQLAlchemySyncRepositoryReadService(Generic[ModelT]):
    """Service object that operates on a repository object."""

    repository_type: type[SQLAlchemySyncRepository[ModelT]]
    match_fields: list[str] | None = None

    def __init__(
        self,
        session: Session,
        statement: Select[tuple[ModelT]] | StatementLambdaElement | None = None,
        auto_expunge: bool = False,
        auto_refresh: bool = True,
        auto_commit: bool = False,
        **repo_kwargs: Any,
    ) -> None:
        """Configure the service object.

        Args:
            session: Session managing the unit-of-work for the operation.
            statement: To facilitate customization of the underlying select query.
            auto_expunge: Remove object from session before returning.
            auto_refresh: Refresh object from session before returning.
            auto_commit: Commit objects before returning.
            **repo_kwargs: passed as keyword args to repo instantiation.
        """
        self.repository = self.repository_type(
            session=session,
            statement=statement,
            auto_expunge=auto_expunge,
            auto_refresh=auto_refresh,
            auto_commit=auto_commit,
            **repo_kwargs,
        )

    def count(
        self,
        *filters: FilterTypes,
        statement: Select[tuple[ModelT]] | StatementLambdaElement | None = None,
        **kwargs: Any,
    ) -> int:
        """Count of records returned by query.

        Args:
            *filters: arguments for filtering.
            statement: To facilitate customization of the underlying select query.
                Defaults to :class:`SQLAlchemySyncRepository.statement <SQLAlchemySyncRepository>`
            **kwargs: key value pairs of filter types.

        Returns:
           A count of the collection, filtered, but ignoring pagination.
        """
        return self.repository.count(*filters, statement=statement, **kwargs)

    def exists(self, *filters: FilterTypes | ColumnElement[bool], **kwargs: Any) -> bool:
        """Wrap repository exists operation.

        Args:
            *filters: Types for specific filtering operations.
            **kwargs: Keyword arguments for attribute based filtering.

        Returns:
            Representation of instance with identifier `item_id`.
        """
        return self.repository.count(*filters, **kwargs) > 0

    def get(
        self,
        item_id: Any,
        auto_expunge: bool | None = None,
        statement: Select[tuple[ModelT]] | StatementLambdaElement | None = None,
        id_attribute: str | InstrumentedAttribute | None = None,
    ) -> ModelT:
        """Wrap repository scalar operation.

        Args:
            item_id: Identifier of instance to be retrieved.
            auto_expunge: Remove object from session before returning. Defaults to
                :class:`SQLAlchemySyncRepository.auto_expunge <SQLAlchemySyncRepository>`
            statement: To facilitate customization of the underlying select query.
                Defaults to :class:`SQLAlchemySyncRepository.statement <SQLAlchemySyncRepository>`
            id_attribute: Allows customization of the unique identifier to use for model fetching.
                Defaults to `id`, but can reference any surrogate or candidate key for the table.


        Returns:
            Representation of instance with identifier `item_id`.
        """
        return self.repository.get(
            item_id=item_id,
            auto_expunge=auto_expunge,
            statement=statement,
            id_attribute=id_attribute,
        )

    def get_one(
        self,
        auto_expunge: bool | None = None,
        statement: Select[tuple[ModelT]] | StatementLambdaElement | None = None,
        **kwargs: Any,
    ) -> ModelT:
        """Wrap repository scalar operation.

        Args:
            auto_expunge: Remove object from session before returning. Defaults to
                :class:`SQLAlchemySyncRepository.auto_expunge <SQLAlchemySyncRepository>`
            statement: To facilitate customization of the underlying select query.
                Defaults to :class:`SQLAlchemySyncRepository.statement <SQLAlchemySyncRepository>`
            **kwargs: Identifier of the instance to be retrieved.

        Returns:
            Representation of instance with identifier `item_id`.
        """
        return self.repository.get_one(auto_expunge=auto_expunge, statement=statement, **kwargs)

    def get_one_or_none(
        self,
        auto_expunge: bool | None = None,
        statement: Select[tuple[ModelT]] | StatementLambdaElement | None = None,
        **kwargs: Any,
    ) -> ModelT | None:
        """Wrap repository scalar operation.

        Args:
            auto_expunge: Remove object from session before returning. Defaults to
                :class:`SQLAlchemySyncRepository.auto_expunge <SQLAlchemySyncRepository>`
            statement: To facilitate customization of the underlying select query.
                Defaults to :class:`SQLAlchemySyncRepository.statement <SQLAlchemySyncRepository>`
            **kwargs: Identifier of the instance to be retrieved.

        Returns:
            Representation of instance with identifier `item_id`.
        """
        return self.repository.get_one_or_none(auto_expunge=auto_expunge, statement=statement, **kwargs)

    def to_model(self, data: ModelT | dict[str, Any], operation: str | None = None) -> ModelT:
        """Parse and Convert input into a model.

        Args:
            data: Representations to be created.
            operation: Optional operation flag so that you can provide behavior based on CRUD operation
        Returns:
            Representation of created instances.
        """
        if isinstance(data, dict):
            return model_from_dict(model=self.repository.model_type, **data)  # type: ignore  # noqa: PGH003
        return data

    def list_and_count(
        self,
        *filters: FilterTypes,
        auto_expunge: bool | None = None,
        statement: Select[tuple[ModelT]] | StatementLambdaElement | None = None,
        force_basic_query_mode: bool | None = None,
        **kwargs: Any,
    ) -> tuple[Sequence[ModelT], int]:
        """List of records and total count returned by query.

        Args:
            *filters: Types for specific filtering operations.
            auto_expunge: Remove object from session before returning. Defaults to
                :class:`SQLAlchemySyncRepository.auto_expunge <SQLAlchemySyncRepository>`.
            statement: To facilitate customization of the underlying select query.
                Defaults to :class:`SQLAlchemySyncRepository.statement <SQLAlchemySyncRepository>`
            force_basic_query_mode: Force list and count to use two queries instead of an analytical window function.
            **kwargs: Instance attribute value filters.

        Returns:
            List of instances and count of total collection, ignoring pagination.
        """
        return self.repository.list_and_count(
            *filters,
            statement=statement,
            auto_expunge=auto_expunge,
            force_basic_query_mode=force_basic_query_mode,
            **kwargs,
        )

    def list(
        self,
        *filters: FilterTypes | ColumnElement[bool],
        auto_expunge: bool | None = None,
        statement: Select[tuple[ModelT]] | StatementLambdaElement | None = None,
        **kwargs: Any,
    ) -> Sequence[ModelT]:
        """Wrap repository scalars operation.

        Args:
            *filters: Types for specific filtering operations.
            auto_expunge: Remove object from session before returning. Defaults to
                :class:`SQLAlchemySyncRepository.auto_expunge <SQLAlchemySyncRepository>`
            statement: To facilitate customization of the underlying select query.
                Defaults to :class:`SQLAlchemySyncRepository.statement <SQLAlchemySyncRepository>`
            **kwargs: Instance attribute value filters.

        Returns:
            The list of instances retrieved from the repository.
        """
        return self.repository.list(*filters, statement=statement, auto_expunge=auto_expunge, **kwargs)

    @staticmethod
    def find_filter(
        filter_type: type[FilterTypeT],
        *filters: FilterTypes | ColumnElement[bool],
    ) -> FilterTypeT | None:
        """Get the filter specified by filter type from the filters.

        Args:
            filter_type: The type of filter to find.
            *filters: filter types to apply to the query

        Returns:
            The match filter instance or None
        """
        return next(
            (cast("FilterTypeT | None", filter_) for filter_ in filters if isinstance(filter_, filter_type)),
            None,
        )


class SQLAlchemySyncRepositoryService(SQLAlchemySyncRepositoryReadService[ModelT]):
    """Service object that operates on a repository object."""

    def create(self, data: ModelT | dict[str, Any]) -> ModelT:
        """Wrap repository instance creation.

        Args:
            data: Representation to be created.

        Returns:
            Representation of created instance.
        """
        data = self.to_model(data, "create")
        return self.repository.add(data)

    def create_many(
        self,
        data: list[ModelT | dict[str, Any]] | list[dict[str, Any]] | list[ModelT],
        auto_commit: bool | None = None,
        auto_expunge: bool | None = None,
    ) -> Sequence[ModelT]:
        """Wrap repository bulk instance creation.

        Args:
            data: Representations to be created.
            auto_expunge: Remove object from session before returning. Defaults to
                :class:`SQLAlchemySyncRepository.auto_expunge <SQLAlchemySyncRepository>`.
            auto_commit: Commit objects before returning. Defaults to
                :class:`SQLAlchemySyncRepository.auto_commit <SQLAlchemySyncRepository>`

        Returns:
            Representation of created instances.
        """
        data = [(self.to_model(datum, "create")) for datum in data]
        return self.repository.add_many(data=data, auto_commit=auto_commit, auto_expunge=auto_expunge)

    def update(
        self,
        item_id: Any,
        data: ModelT | dict[str, Any],
        attribute_names: Iterable[str] | None = None,
        with_for_update: bool | None = None,
        auto_commit: bool | None = None,
        auto_expunge: bool | None = None,
        auto_refresh: bool | None = None,
        id_attribute: str | InstrumentedAttribute | None = None,
    ) -> ModelT:
        """Wrap repository update operation.

        Args:
            item_id: Identifier of item to be updated.
            data: Representation to be updated.
            attribute_names: an iterable of attribute names to pass into the ``update``
                method.
            with_for_update: indicating FOR UPDATE should be used, or may be a
                dictionary containing flags to indicate a more specific set of
                FOR UPDATE flags for the SELECT
            auto_expunge: Remove object from session before returning. Defaults to
                :class:`SQLAlchemySyncRepository.auto_expunge <SQLAlchemySyncRepository>`.
            auto_refresh: Refresh object from session before returning. Defaults to
                :class:`SQLAlchemySyncRepository.auto_refresh <SQLAlchemySyncRepository>`
            auto_commit: Commit objects before returning. Defaults to
                :class:`SQLAlchemySyncRepository.auto_commit <SQLAlchemySyncRepository>`
            id_attribute: Allows customization of the unique identifier to use for model fetching.
                Defaults to `id`, but can reference any surrogate or candidate key for the table.

        Returns:
            Updated representation.
        """
        data = self.to_model(data, "update")
        data = self.repository.set_id_attribute_value(item_id, data)
        return self.repository.update(
            data=data,
            attribute_names=attribute_names,
            with_for_update=with_for_update,
            auto_expunge=auto_expunge,
            auto_commit=auto_commit,
            auto_refresh=auto_refresh,
            id_attribute=id_attribute,
        )

    def update_many(
        self,
        data: list[ModelT | dict[str, Any]] | list[dict[str, Any]] | list[ModelT],
        auto_commit: bool | None = None,
        auto_expunge: bool | None = None,
    ) -> Sequence[ModelT]:
        """Wrap repository bulk instance update.

        Args:
            data: Representations to be updated.
            auto_expunge: Remove object from session before returning. Defaults to
                :class:`SQLAlchemySyncRepository.auto_expunge <SQLAlchemySyncRepository>`.
            auto_commit: Commit objects before returning. Defaults to
                :class:`SQLAlchemySyncRepository.auto_commit <SQLAlchemySyncRepository>`

        Returns:
            Representation of updated instances.
        """
        data = [(self.to_model(datum, "update")) for datum in data]
        return self.repository.update_many(data, auto_commit=auto_commit, auto_expunge=auto_expunge)

    def upsert(
        self,
        item_id: Any,
        data: ModelT | dict[str, Any],
        attribute_names: Iterable[str] | None = None,
        with_for_update: bool | None = None,
        auto_expunge: bool | None = None,
        auto_commit: bool | None = None,
        auto_refresh: bool | None = None,
    ) -> ModelT:
        """Wrap repository upsert operation.

        Args:
            item_id: Identifier of the object for upsert.
            data: Instance to update existing, or be created. Identifier used to determine if an
                existing instance exists is the value of an attribute on `data` named as value of
                `self.id_attribute`.
            attribute_names: an iterable of attribute names to pass into the ``update`` method.
            with_for_update: indicating FOR UPDATE should be used, or may be a
                dictionary containing flags to indicate a more specific set of
                FOR UPDATE flags for the SELECT
            auto_expunge: Remove object from session before returning. Defaults to
                :class:`SQLAlchemySyncRepository.auto_expunge <SQLAlchemySyncRepository>`.
            auto_refresh: Refresh object from session before returning. Defaults to
                :class:`SQLAlchemySyncRepository.auto_refresh <SQLAlchemySyncRepository>`
            auto_commit: Commit objects before returning. Defaults to
                :class:`SQLAlchemySyncRepository.auto_commit <SQLAlchemySyncRepository>`


        Returns:
            Updated or created representation.
        """
        data = self.to_model(data, "upsert")
        self.repository.set_id_attribute_value(item_id, data)
        return self.repository.upsert(
            data=data,
            attribute_names=attribute_names,
            with_for_update=with_for_update,
            auto_expunge=auto_expunge,
            auto_commit=auto_commit,
            auto_refresh=auto_refresh,
        )

    def upsert_many(
        self,
        data: list[ModelT | dict[str, Any]] | list[dict[str, Any]] | list[ModelT],
        auto_expunge: bool | None = None,
        auto_commit: bool | None = None,
        no_merge: bool = False,
    ) -> list[ModelT]:
        """Wrap repository upsert operation.

        Args:
            data: Instance to update existing, or be created. Identifier used to determine if an
                existing instance exists is the value of an attribute on ``data`` named as value of
                :attr:`~advanced_alchemy.repository.AbstractAsyncRepository.id_attribute`.
            auto_expunge: Remove object from session before returning. Defaults to
                :class:`SQLAlchemySyncRepository.auto_expunge <SQLAlchemySyncRepository>`.
            auto_commit: Commit objects before returning. Defaults to
                :class:`SQLAlchemySyncRepository.auto_commit <SQLAlchemySyncRepository>`
            no_merge: Skip the usage of optimized Merge statements
                :class:`SQLAlchemySyncRepository.auto_commit <SQLAlchemySyncRepository>`


        Returns:
            Updated or created representation.
        """
        data = [(self.to_model(datum, "upsert")) for datum in data]
        return self.repository.upsert_many(
            data=data,
            auto_expunge=auto_expunge,
            auto_commit=auto_commit,
            no_merge=no_merge,
        )

    def get_or_upsert(
        self,
        match_fields: list[str] | None = None,
        upsert: bool = True,
        attribute_names: Iterable[str] | None = None,
        with_for_update: bool | None = None,
        auto_commit: bool | None = None,
        auto_expunge: bool | None = None,
        auto_refresh: bool | None = None,
        **kwargs: Any,
    ) -> tuple[ModelT, bool]:
        """Wrap repository instance creation.

        Args:
            match_fields: a list of keys to use to match the existing model.  When
                empty, all fields are matched.
            upsert: When using match_fields and actual model values differ from
                `kwargs`, perform an update operation on the model.
            attribute_names: an iterable of attribute names to pass into the ``update``
                method.
            with_for_update: indicating FOR UPDATE should be used, or may be a
                dictionary containing flags to indicate a more specific set of
                FOR UPDATE flags for the SELECT
            auto_expunge: Remove object from session before returning. Defaults to
                :class:`SQLAlchemySyncRepository.auto_expunge <SQLAlchemySyncRepository>`.
            auto_refresh: Refresh object from session before returning. Defaults to
                :class:`SQLAlchemySyncRepository.auto_refresh <SQLAlchemySyncRepository>`
            auto_commit: Commit objects before returning. Defaults to
                :class:`SQLAlchemySyncRepository.auto_commit <SQLAlchemySyncRepository>`
            **kwargs: Identifier of the instance to be retrieved.

        Returns:
            Representation of created instance.
        """
        match_fields = match_fields or self.match_fields
        validated_model = self.to_model(kwargs, "create")
        return self.repository.get_or_create(
            match_fields=match_fields,
            upsert=upsert,
            attribute_names=attribute_names,
            with_for_update=with_for_update,
            auto_commit=auto_commit,
            auto_expunge=auto_expunge,
            auto_refresh=auto_refresh,
            **validated_model.to_dict(),
        )

    def delete(
        self,
        item_id: Any,
        auto_commit: bool | None = None,
        auto_expunge: bool | None = None,
        id_attribute: str | InstrumentedAttribute | None = None,
    ) -> ModelT:
        """Wrap repository delete operation.

        Args:
            item_id: Identifier of instance to be deleted.
            auto_expunge: Remove object from session before returning. Defaults to
                :class:`SQLAlchemySyncRepository.auto_expunge <SQLAlchemySyncRepository>`.
            auto_commit: Commit objects before returning. Defaults to
                :class:`SQLAlchemySyncRepository.auto_commit <SQLAlchemySyncRepository>`
            id_attribute: Allows customization of the unique identifier to use for model fetching.
                Defaults to `id`, but can reference any surrogate or candidate key for the table.


        Returns:
            Representation of the deleted instance.
        """
        return self.repository.delete(
            item_id=item_id,
            auto_commit=auto_commit,
            auto_expunge=auto_expunge,
            id_attribute=id_attribute,
        )

    def delete_many(
        self,
        item_ids: list[Any],
        auto_commit: bool | None = None,
        auto_expunge: bool | None = None,
        id_attribute: str | InstrumentedAttribute | None = None,
        chunk_size: int | None = None,
    ) -> Sequence[ModelT]:
        """Wrap repository bulk instance deletion.

        Args:
            item_ids: Identifier of instance to be deleted.
            auto_expunge: Remove object from session before returning. Defaults to
                :class:`SQLAlchemySyncRepository.auto_expunge <SQLAlchemySyncRepository>`.
            auto_commit: Commit objects before returning. Defaults to
                :class:`SQLAlchemySyncRepository.auto_commit <SQLAlchemySyncRepository>`
            id_attribute: Allows customization of the unique identifier to use for model fetching.
                Defaults to `id`, but can reference any surrogate or candidate key for the table.
            chunk_size: Allows customization of the ``insertmanyvalues_max_parameters`` setting for the driver.
                Defaults to `950` if left unset.


        Returns:
            Representation of removed instances.
        """
        return self.repository.delete_many(
            item_ids=item_ids,
            auto_commit=auto_commit,
            auto_expunge=auto_expunge,
            id_attribute=id_attribute,
            chunk_size=chunk_size,
        )
