"""Service object implementation for SQLAlchemy.

RepositoryService object is generic on the domain model type which
should be a SQLAlchemy model.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, overload

from advanced_alchemy.service._converters import to_schema

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy import RowMapping
    from sqlalchemy.sql import ColumnElement

    from advanced_alchemy.base import ModelProtocol
    from advanced_alchemy.filters import StatementFilter
    from advanced_alchemy.repository.typing import ModelOrRowMappingT
    from advanced_alchemy.service.pagination import OffsetPagination
    from advanced_alchemy.service.typing import PydanticModelDTOT, StructModelDTOT


class ResultConverter:
    """Simple mixin to help convert to a paginated response model the results set is a list."""

    @overload
    def to_schema(
        self,
        data: ModelOrRowMappingT,
        total: int | None = None,
        filters: Sequence[StatementFilter | ColumnElement[bool]] | Sequence[StatementFilter] | None = None,
        *,
        schema_type: None = None,
    ) -> ModelOrRowMappingT: ...

    @overload
    def to_schema(
        self,
        data: Sequence[ModelOrRowMappingT],
        total: int | None = None,
        filters: Sequence[StatementFilter | ColumnElement[bool]] | Sequence[StatementFilter] | None = None,
        *,
        schema_type: None = None,
    ) -> OffsetPagination[ModelOrRowMappingT]: ...

    @overload
    def to_schema(
        self,
        data: ModelProtocol | RowMapping,
        total: int | None = None,
        filters: Sequence[StatementFilter | ColumnElement[bool]] | Sequence[StatementFilter] | None = None,
        *,
        schema_type: type[StructModelDTOT],
    ) -> StructModelDTOT: ...

    @overload
    def to_schema(
        self,
        data: Sequence[ModelProtocol] | Sequence[RowMapping],
        total: int | None = None,
        filters: Sequence[StatementFilter | ColumnElement[bool]] | Sequence[StatementFilter] | None = None,
        *,
        schema_type: type[StructModelDTOT],
    ) -> OffsetPagination[StructModelDTOT]: ...

    @overload
    def to_schema(
        self,
        data: ModelProtocol | RowMapping,
        total: int | None = None,
        filters: Sequence[StatementFilter | ColumnElement[bool]] | Sequence[StatementFilter] | None = None,
        *,
        schema_type: type[PydanticModelDTOT],
    ) -> PydanticModelDTOT: ...

    @overload
    def to_schema(
        self,
        data: Sequence[ModelProtocol] | Sequence[RowMapping],
        total: int | None = None,
        filters: Sequence[StatementFilter | ColumnElement[bool]] | Sequence[StatementFilter] | None = None,
        *,
        schema_type: type[PydanticModelDTOT],
    ) -> OffsetPagination[PydanticModelDTOT]: ...

    def to_schema(
        self,
        data: ModelOrRowMappingT | Sequence[ModelOrRowMappingT] | ModelProtocol | Sequence[ModelProtocol],
        total: int | None = None,
        filters: Sequence[StatementFilter | ColumnElement[bool]] | Sequence[StatementFilter] | None = None,
        *,
        schema_type: type[PydanticModelDTOT | StructModelDTOT] | None = None,
    ) -> (
        ModelOrRowMappingT
        | OffsetPagination[ModelOrRowMappingT]
        | ModelProtocol
        | OffsetPagination[ModelProtocol]
        | StructModelDTOT
        | OffsetPagination[StructModelDTOT]
        | PydanticModelDTOT
        | OffsetPagination[PydanticModelDTOT]
    ):
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
