from typing import TYPE_CHECKING, Any, Union

from sqlalchemy.orm import InstrumentedAttribute
from typing_extensions import TypeAlias, TypeVar

if TYPE_CHECKING:
    from sqlalchemy import RowMapping, Select

    from advanced_alchemy import base
    from advanced_alchemy.repository._async import SQLAlchemyAsyncRepository
    from advanced_alchemy.repository._sync import SQLAlchemySyncRepository
    from advanced_alchemy.repository.memory._async import SQLAlchemyAsyncMockRepository
    from advanced_alchemy.repository.memory._sync import SQLAlchemySyncMockRepository

__all__ = (
    "MISSING",
    "ModelOrRowMappingT",
    "ModelT",
    "OrderingPair",
    "RowMappingT",
    "RowT",
    "SQLAlchemyAsyncRepositoryT",
    "SQLAlchemySyncRepositoryT",
    "SelectT",
    "T",
)

T = TypeVar("T")
ModelT = TypeVar("ModelT", bound="base.ModelProtocol")
"""Type variable for SQLAlchemy models.

:class:`~advanced_alchemy.base.ModelProtocol`
"""
SelectT = TypeVar("SelectT", bound="Select[Any]")
"""Type variable for SQLAlchemy select statements.

:class:`~sqlalchemy.sql.Select`
"""
RowT = TypeVar("RowT", bound=tuple[Any, ...])
"""Type variable for rows.

:class:`~sqlalchemy.engine.Row`
"""
RowMappingT = TypeVar("RowMappingT", bound="RowMapping")
"""Type variable for row mappings.

:class:`~sqlalchemy.engine.RowMapping`
"""
ModelOrRowMappingT = TypeVar("ModelOrRowMappingT", bound="Union[base.ModelProtocol, RowMapping]")
"""Type variable for models or row mappings.

:class:`~advanced_alchemy.base.ModelProtocol` | :class:`~sqlalchemy.engine.RowMapping`
"""
SQLAlchemySyncRepositoryT = TypeVar(
    "SQLAlchemySyncRepositoryT",
    bound="Union[SQLAlchemySyncRepository[Any], SQLAlchemySyncMockRepository[Any]]",
    default="Any",
)
"""Type variable for synchronous SQLAlchemy repositories.

:class:`~advanced_alchemy.repository.SQLAlchemySyncRepository`
"""
SQLAlchemyAsyncRepositoryT = TypeVar(
    "SQLAlchemyAsyncRepositoryT",
    bound="Union[SQLAlchemyAsyncRepository[Any], SQLAlchemyAsyncMockRepository[Any]]",
    default="Any",
)
"""Type variable for asynchronous SQLAlchemy repositories.

:class:`~advanced_alchemy.repository.SQLAlchemyAsyncRepository`
"""
OrderingPair: TypeAlias = tuple[Union[str, InstrumentedAttribute[Any]], bool]
"""Type alias for ordering pairs.

A tuple of (column, ascending) where:
- column: Union[str, :class:`sqlalchemy.orm.InstrumentedAttribute`]
- ascending: bool

This type is used to specify ordering criteria for repository queries.
"""


class _MISSING:
    """Placeholder for missing values."""


MISSING = _MISSING()
"""Missing value placeholder.

:class:`~advanced_alchemy.repository.typing._MISSING`
"""
