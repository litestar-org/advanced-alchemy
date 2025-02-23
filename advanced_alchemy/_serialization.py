import datetime
import enum
from typing import Any

from typing_extensions import runtime_checkable

try:
    from pydantic import BaseModel  # type: ignore # noqa: PGH003

    PYDANTIC_INSTALLED = True
except ImportError:
    from typing import ClassVar, Protocol

    @runtime_checkable
    class BaseModel(Protocol):  # type: ignore[no-redef]
        """Placeholder Implementation"""

        model_fields: ClassVar[dict[str, Any]]

        def model_dump_json(self, *args: Any, **kwargs: Any) -> str:
            """Placeholder"""
            return ""

    PYDANTIC_INSTALLED = False  # pyright: ignore[reportConstantRedefinition]


def _type_to_string(value: Any) -> str:  # pragma: no cover
    if isinstance(value, datetime.datetime):
        return convert_datetime_to_gmt_iso(value)
    if isinstance(value, datetime.date):
        return convert_date_to_iso(value)
    if isinstance(value, enum.Enum):
        return str(value.value)
    if PYDANTIC_INSTALLED and isinstance(value, BaseModel):
        return value.model_dump_json()
    try:
        val = str(value)
    except Exception as exc:
        raise TypeError from exc
    return val


try:
    from msgspec.json import Decoder, Encoder

    encoder, decoder = Encoder(enc_hook=_type_to_string), Decoder()
    decode_json = decoder.decode

    def encode_json(data: Any) -> str:  # pragma: no cover
        return encoder.encode(data).decode("utf-8")

except ImportError:
    try:
        from orjson import OPT_NAIVE_UTC, OPT_SERIALIZE_NUMPY, OPT_SERIALIZE_UUID
        from orjson import dumps as _encode_json
        from orjson import loads as decode_json  # type: ignore[no-redef,assignment]

        def encode_json(data: Any) -> str:  # pragma: no cover
            return _encode_json(
                data, default=_type_to_string, option=OPT_SERIALIZE_NUMPY | OPT_NAIVE_UTC | OPT_SERIALIZE_UUID
            ).decode("utf-8")  # type: ignore[no-any-return]

    except ImportError:
        from json import dumps as encode_json  # type: ignore[assignment] # noqa: F401
        from json import loads as decode_json  # type: ignore[assignment]  # noqa: F401


def convert_datetime_to_gmt_iso(dt: datetime.datetime) -> str:  # pragma: no cover
    """Handle datetime serialization for nested timestamps."""
    if not dt.tzinfo:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


def convert_date_to_iso(dt: datetime.date) -> str:  # pragma: no cover
    """Handle datetime serialization for nested timestamps."""
    return dt.isoformat()
