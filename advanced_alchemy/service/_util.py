"""Service object implementation for SQLAlchemy.

RepositoryService object is generic on the domain model type which
should be a SQLAlchemy model.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, overload

from advanced_alchemy.service._converters import EMPTY_FILTER, to_schema

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy import RowMapping
    from sqlalchemy.sql import ColumnElement

    from advanced_alchemy.base import ModelProtocol
    from advanced_alchemy.filters import FilterTypes
    from advanced_alchemy.repository.typing import ModelOrRowMappingT
    from advanced_alchemy.service.pagination import OffsetPagination
    from advanced_alchemy.service.typing import ModelDTOT


class ResultConverter:
    """Simple mixin to help convert to a paginated response model the results set is a list."""

    @overload
    def to_schema(
        self,
        data: ModelOrRowMappingT,
        *,
        total: int | None = None,
        filters: Sequence[FilterTypes | ColumnElement[bool]] | Sequence[FilterTypes] = EMPTY_FILTER,
    ) -> ModelOrRowMappingT: ...

    @overload
    def to_schema(
        self,
        data: Sequence[ModelOrRowMappingT],
        *,
        total: int | None = None,
        filters: Sequence[FilterTypes | ColumnElement[bool]] | Sequence[FilterTypes] = EMPTY_FILTER,
    ) -> OffsetPagination[ModelOrRowMappingT]: ...

    @overload
    def to_schema(
        self,
        data: ModelProtocol | RowMapping,
        *,
        total: int | None = None,
        filters: Sequence[FilterTypes | ColumnElement[bool]] | Sequence[FilterTypes] = EMPTY_FILTER,
        schema_type: type[ModelDTOT],
    ) -> ModelDTOT: ...

    @overload
    def to_schema(
        self,
        data: Sequence[ModelOrRowMappingT],
        *,
        total: int | None = None,
        filters: Sequence[FilterTypes | ColumnElement[bool]] | Sequence[FilterTypes] = EMPTY_FILTER,
        schema_type: type[ModelDTOT],
    ) -> OffsetPagination[ModelDTOT]: ...

    def to_schema(
        self,
        data: ModelOrRowMappingT | Sequence[ModelOrRowMappingT],
        *,
        total: int | None = None,
        filters: Sequence[FilterTypes | ColumnElement[bool]] | Sequence[FilterTypes] = EMPTY_FILTER,
        schema_type: type[ModelDTOT] | None = None,
    ) -> ModelOrRowMappingT | OffsetPagination[ModelOrRowMappingT] | ModelDTOT | OffsetPagination[ModelDTOT]:
        """Convert the object to a response schema.  When `schema_type` is None, the model is returned with no conversion.

        Args:
            data: The return from one of the service calls.
            total: the total number of rows in the data
            filters: Collection route filters.
            schema_type: Collection route filters.

        Returns:
            The list of instances retrieved from the repository.
        """
        return to_schema(data=data, total=total, filters=filters, schema_type=schema_type)
