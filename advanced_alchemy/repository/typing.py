from typing import TYPE_CHECKING, Any, Tuple, TypeVar, Union

if TYPE_CHECKING:
    from sqlalchemy import RowMapping, Select

    from advanced_alchemy import base

__all__ = (
    "ModelT",
    "SelectT",
    "RowT",
    "MISSING",
)

T = TypeVar("T")
ModelT = TypeVar("ModelT", bound="base.ModelProtocol")
SelectT = TypeVar("SelectT", bound="Select[Any]")
RowT = TypeVar("RowT", bound=Tuple[Any, ...])
RowMappingT = TypeVar("RowMappingT", bound="RowMapping")
ModelOrRowMappingT = TypeVar("ModelOrRowMappingT", bound="Union[base.ModelProtocol, RowMapping]")


class _MISSING:
    pass


MISSING = _MISSING()
