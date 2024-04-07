from typing import TYPE_CHECKING, Any, Tuple, TypeVar

if TYPE_CHECKING:
    from sqlalchemy import Select

    from advanced_alchemy import base
    from advanced_alchemy.repository._async import SQLAlchemyAsyncRepository
    from advanced_alchemy.repository._sync import SQLAlchemySyncRepository

__all__ = (
    "ModelT",
    "SelectT",
    "RowT",
    "SQLAlchemySyncRepositoryT",
    "SQLAlchemyAsyncRepositoryT",
    "MISSING",
)

T = TypeVar("T")
ModelT = TypeVar("ModelT", bound="base.ModelProtocol")


SelectT = TypeVar("SelectT", bound="Select[Any]")
RowT = TypeVar("RowT", bound=Tuple[Any, ...])


SQLAlchemySyncRepositoryT = TypeVar("SQLAlchemySyncRepositoryT", bound="SQLAlchemySyncRepository")
SQLAlchemyAsyncRepositoryT = TypeVar("SQLAlchemyAsyncRepositoryT", bound="SQLAlchemyAsyncRepository")


class _MISSING:
    pass


MISSING = _MISSING()
