from typing import TYPE_CHECKING, Any, Tuple, TypeVar, Union

if TYPE_CHECKING:
    from sqlalchemy import RowMapping, Select

    from advanced_alchemy import base
    from advanced_alchemy.repository._async import SQLAlchemyAsyncRepository
    from advanced_alchemy.repository._sync import SQLAlchemySyncRepository

__all__ = (
    "ModelT",
    "SelectT",
    "RowT",
    "MISSING",
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


class _MISSING:
    pass


MISSING = _MISSING()
