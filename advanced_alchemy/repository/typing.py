from __future__ import annotations

from typing import TYPE_CHECKING, Any, Tuple, Union

from sqlalchemy.orm import InstrumentedAttribute
from typing_extensions import TypeAlias, TypeVar

if TYPE_CHECKING:
    from sqlalchemy import RowMapping, Select

    from advanced_alchemy import base
    from advanced_alchemy.repository._async import SQLAlchemyAsyncRepository
    from advanced_alchemy.repository._sync import SQLAlchemySyncRepository

__all__ = (
    "T",
    "ModelT",
    "SelectT",
    "RowT",
    "MISSING",
    "OrderingPair",
    "RowMappingT",
    "ModelOrRowMappingT",
    "SQLAlchemySyncRepositoryT",
    "SQLAlchemyAsyncRepositoryT",
)

T = TypeVar("T")
ModelT = TypeVar("ModelT", bound="base.ModelProtocol")
SelectT = TypeVar("SelectT", bound="Select[Any]")
RowT = TypeVar("RowT", bound=Tuple[Any, ...])
RowMappingT = TypeVar("RowMappingT", bound="RowMapping")
ModelOrRowMappingT = TypeVar("ModelOrRowMappingT", bound="Union[base.ModelProtocol, RowMapping]")
SQLAlchemySyncRepositoryT = TypeVar("SQLAlchemySyncRepositoryT", bound="SQLAlchemySyncRepository[Any]")
SQLAlchemyAsyncRepositoryT = TypeVar(
    "SQLAlchemyAsyncRepositoryT",
    bound="SQLAlchemyAsyncRepository[Any]",
)
OrderingPair: TypeAlias = Tuple[Union[str, InstrumentedAttribute[Any]], bool]


class _MISSING:
    pass


MISSING = _MISSING()
