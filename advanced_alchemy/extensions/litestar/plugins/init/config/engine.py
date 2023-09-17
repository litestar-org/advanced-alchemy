from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

from litestar.serialization import decode_json, encode_json

from advanced_alchemy.config import EngineConfig as _EngineConfig

if TYPE_CHECKING:
    from typing import Any


__all__ = ("EngineConfig",)


def serializer(value: Any) -> str:
    """Serialize JSON field values.

    Args:
        value: Any json serializable value.

    Returns:
        JSON string.
    """
    return encode_json(value).decode("utf-8")


@dataclass
class EngineConfig(_EngineConfig):
    """Configuration for SQLAlchemy's :class:`Engine <sqlalchemy.engine.Engine>`.

    For details see: https://docs.sqlalchemy.org/en/20/core/engines.html
    """

    json_deserializer: Callable[[str], Any] = decode_json
    """For dialects that support the :class:`JSON <sqlalchemy.types.JSON>` datatype, this is a Python callable that will
    convert a JSON string to a Python object. By default, this is set to Litestar's
    :attr:`decode_json() <.serialization.decode_json>` function."""
    json_serializer: Callable[[Any], str] = serializer
    """For dialects that support the JSON datatype, this is a Python callable that will render a given object as JSON.
    By default, Litestar's :attr:`encode_json() <.serialization.encode_json>` is used."""
