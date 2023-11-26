from __future__ import annotations

from abc import ABCMeta, abstractmethod
from typing import TYPE_CHECKING, Any, Generic, TypeVar

from advanced_alchemy.exceptions import NotFoundError

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_scoped_session

    from advanced_alchemy.filters import FilterTypes

R = TypeVar("R", bound="Any")
ModelT = TypeVar("ModelT", bound="Any")

__all__ = ["AbstractRepository"]


class AbstractRepository(Generic[ModelT], metaclass=ABCMeta):
    model_type: type[ModelT]
    id_attribute: Any = "id"
    """Name of the primary identifying attribute on :attr:`model_type`."""

    def __init__(self, **kwargs: Any) -> None:
        """Repository constructors accept arbitrary kwargs."""
        super().__init__(**kwargs)

    @classmethod
    @abstractmethod
    async def check_health(cls, session: AsyncSession | async_scoped_session[AsyncSession]) -> bool:
        """Perform a health check on the database.

        Args:
            session: through which we run a check statement

        Returns:
            ``True`` if healthy.
        """

    @abstractmethod
    async def add(self, data: ModelT) -> ModelT:
        """Add ``data`` to the collection.

        Args:
            data: Instance to be added to the collection.

        Returns:
            The added instance.
        """

    @abstractmethod
    async def add_many(self, data: list[ModelT]) -> list[ModelT]:
        """Add multiple ``data`` to the collection.

        Args:
            data: Instances to be added to the collection.

        Returns:
            The added instances.
        """

    @abstractmethod
    async def count(self, *filters: FilterTypes, **kwargs: Any) -> int:
        """Get the count of records returned by a query.

        Args:
            *filters: Types for specific filtering operations.
            **kwargs: Instance attribute value filters.

        Returns:
            The count of instances
        """

    @abstractmethod
    async def delete(self, item_id: Any) -> ModelT:
        """Delete instance identified by ``item_id``.

        Args:
            item_id: Identifier of instance to be deleted.

        Returns:
            The deleted instance.

        Raises:
            NotFoundError: If no instance found identified by ``item_id``.
        """

    @abstractmethod
    async def delete_many(self, item_ids: list[Any]) -> list[ModelT]:
        """Delete multiple instances identified by list of IDs ``item_ids``.

        Args:
            item_ids: list of Identifiers to be deleted.

        Returns:
            The deleted instances.
        """

    @abstractmethod
    async def exists(self, *filters: FilterTypes, **kwargs: Any) -> bool:
        """Return true if the object specified by ``kwargs`` exists.

        Args:
            *filters: Types for specific filtering operations.
            **kwargs: Identifier of the instance to be retrieved.

        Returns:
            True if the instance was found.  False if not found.

        """

    @abstractmethod
    async def get(self, item_id: Any, **kwargs: Any) -> ModelT:
        """Get instance identified by ``item_id``.

        Args:
            item_id: Identifier of the instance to be retrieved.
            **kwargs: Additional keyword arguments

        Returns:
            The retrieved instance.

        Raises:
            NotFoundError: If no instance found identified by ``item_id``.
        """

    @abstractmethod
    async def get_one(self, **kwargs: Any) -> ModelT:
        """Get an instance specified by the ``kwargs`` filters if it exists.

        Args:
            **kwargs: Instance attribute value filters.

        Returns:
            The retrieved instance.

        Raises:
            NotFoundError: If no instance found identified by ``kwargs``.
        """

    @abstractmethod
    async def get_or_create(self, **kwargs: Any) -> tuple[ModelT, bool]:
        """Get an instance specified by the ``kwargs`` filters if it exists or create it.

        Args:
            **kwargs: Instance attribute value filters.

        Returns:
            A tuple that includes the retrieved or created instance, and a boolean on whether the record was created or not
        """

    @abstractmethod
    async def get_one_or_none(self, **kwargs: Any) -> ModelT | None:
        """Get an instance if it exists or None.

        Args:
            **kwargs: Instance attribute value filters.

        Returns:
            The retrieved instance or None.
        """

    @abstractmethod
    async def update(self, data: ModelT) -> ModelT:
        """Update instance with the attribute values present on ``data``.

        Args:
            data: An instance that should have a value for :attr:`id_attribute <AbstractAsyncRepository.id_attribute>` that exists in the
                collection.

        Returns:
            The updated instance.

        Raises:
            NotFoundError: If no instance found with same identifier as ``data``.
        """

    @abstractmethod
    async def update_many(self, data: list[ModelT]) -> list[ModelT]:
        """Update multiple instances with the attribute values present on instances in ``data``.

        Args:
            data: A list of instance that should have a value for :attr:`id_attribute <AbstractAsyncRepository.id_attribute>` that exists in the
                collection.

        Returns:
            a list of the updated instances.

        Raises:
            NotFoundError: If no instance found with same identifier as ``data``.
        """

    @abstractmethod
    async def upsert(self, data: ModelT) -> ModelT:
        """Update or create instance.

        Updates instance with the attribute values present on ``data``, or creates a new instance if
        one doesn't exist.

        Args:
            data: Instance to update existing, or be created. Identifier used to determine if an
                existing instance exists is the value of an attribute on ``data`` named as value of
                :attr:`id_attribute <AbstractAsyncRepository.id_attribute>`.

        Returns:
            The updated or created instance.

        Raises:
            NotFoundError: If no instance found with same identifier as ``data``.
        """

    @abstractmethod
    async def upsert_many(self, data: list[ModelT]) -> list[ModelT]:
        """Update or create multiple instances.

        Update instances with the attribute values present on ``data``, or create a new instance if
        one doesn't exist.

        Args:
            data: Instances to update or created. Identifier used to determine if an
                existing instance exists is the value of an attribute on ``data`` named as value of
                :attr:`id_attribute <AbstractAsyncRepository.id_attribute>`.

        Returns:
            The updated or created instances.

        Raises:
            NotFoundError: If no instance found with same identifier as ``data``.
        """

    @abstractmethod
    async def list_and_count(self, *filters: FilterTypes, **kwargs: Any) -> tuple[list[ModelT], int]:
        """List records with total count.

        Args:
            *filters: Types for specific filtering operations.
            **kwargs: Instance attribute value filters.

        Returns:
            a tuple containing The list of instances, after filtering applied, and a count of records returned by query, ignoring pagination.
        """

    @abstractmethod
    def filter_collection_by_kwargs(self, collection: Any, /, **kwargs: Any) -> Any:
        """Filter the collection by kwargs.

        Has ``AND`` semantics where multiple kwargs name/value pairs are provided.

        Args:
            collection: the objects to be filtered
            **kwargs: key/value pairs such that objects remaining in the collection after filtering
                have the property that their attribute named ``key`` has value equal to ``value``.


        Returns:
            The filtered objects

        Raises:
            RepositoryError: if a named attribute doesn't exist on :attr:`model_type <AbstractAsyncRepository.model_type>`.
        """

    @staticmethod
    def check_not_found(item_or_none: ModelT | None) -> ModelT:
        """Raise :class:`NotFoundError` if ``item_or_none`` is ``None``.

        Args:
            item_or_none: Item (:class:`T <T>`) to be tested for existence.

        Returns:
            The item, if it exists.
        """
        if item_or_none is None:
            msg = "No item found when one was expected"
            raise NotFoundError(msg)
        return item_or_none

    @classmethod
    def get_id_attribute_value(cls, item: ModelT | type[ModelT], id_attribute: str | None = None) -> Any:
        """Get value of attribute named as :attr:`id_attribute <AbstractAsyncRepository.id_attribute>` on ``item``.

        Args:
            item: Anything that should have an attribute named as :attr:`id_attribute <AbstractAsyncRepository.id_attribute>` value.
            id_attribute: Allows customization of the unique identifier to use for model fetching.
                Defaults to `None`, but can reference any surrogate or candidate key for the table.

        Returns:
            The value of attribute on ``item`` named as :attr:`id_attribute <AbstractAsyncRepository.id_attribute>`.
        """
        return getattr(item, id_attribute if id_attribute is not None else cls.id_attribute)

    @classmethod
    def set_id_attribute_value(cls, item_id: Any, item: ModelT, id_attribute: str | None = None) -> ModelT:
        """Return the ``item`` after the ID is set to the appropriate attribute.

        Args:
            item_id: Value of ID to be set on instance
            item: Anything that should have an attribute named as :attr:`id_attribute <AbstractAsyncRepository.id_attribute>` value.
            id_attribute: Allows customization of the unique identifier to use for model fetching.
                Defaults to `None`, but can reference any surrogate or candidate key for the table.

        Returns:
            Item with ``item_id`` set to :attr:`id_attribute <AbstractAsyncRepository.id_attribute>`
        """
        setattr(item, id_attribute if id_attribute is not None else cls.id_attribute, item_id)
        return item

    @abstractmethod
    async def first(self) -> ModelT | None:
        """Return the first object of the collection if exists, None otherwise."""
        ...

    @abstractmethod
    async def random(self, size: int = 1) -> list[ModelT]:
        """Return a random sample of instances

        Args:
            size: Number of instance to return. Defaults to 1.

        Returns:
            List of instances
        """
        ...

    @abstractmethod
    def fork(self, repository_type: type[R], **kwargs: Any) -> R:
        """Return an instance of `repository_type`
        initialized with context from this repository.
        """
        ...

    @abstractmethod
    async def list(self, *filters: FilterTypes, **kwargs: Any) -> list[ModelT]:
        """Get a list of instances, optionally filtered.

        Args:
            *filters: filters for specific filtering operations
            **kwargs: Instance attribute value filters.

        Returns:
            The list of instances, after filtering applied
        """
