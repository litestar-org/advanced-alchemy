# ruff: noqa: PLR0911
import datetime
import decimal
import enum
import uuid
from typing import Any, ClassVar, Protocol, Union, cast

from typing_extensions import runtime_checkable

from advanced_alchemy.exceptions import MissingDependencyError

try:
    from pydantic import BaseModel  # type: ignore

    PYDANTIC_INSTALLED = True
except ImportError:

    @runtime_checkable
    class BaseModel(Protocol):  # type: ignore[no-redef]
        """Placeholder Implementation"""

        model_fields: ClassVar[dict[str, Any]]

        def model_dump_json(self, *args: Any, **kwargs: Any) -> str:
            """Placeholder for pydantic.BaseModel.model_dump_json

            Returns:
                The JSON representation of the model.
            """
            msg = "pydantic"
            raise MissingDependencyError(msg)

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
    """Handle datetime serialization for nested timestamps.

    Returns:
        str: The ISO 8601 formatted datetime string.
    """
    if not dt.tzinfo:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


def convert_date_to_iso(dt: datetime.date) -> str:  # pragma: no cover
    """Handle datetime serialization for nested timestamps.

    Returns:
        str: The ISO 8601 formatted date string.
    """
    return dt.isoformat()


def encode_complex_type(obj: Any) -> Any:
    """Convert an object to a JSON-serializable format if possible.

    Handles types that are not natively JSON serializable:
    - datetime, date, time: ISO format strings
    - timedelta: total seconds as float
    - Decimal: string representation
    - bytes: hex string
    - UUID: string representation
    - set, frozenset: list

    Args:
        obj: The object to encode.

    Returns:
        A JSON-serializable representation of the object, or None if the type is not supported.
    """
    if isinstance(obj, datetime.datetime):
        return {"__type__": "datetime", "value": obj.isoformat()}
    if isinstance(obj, datetime.date):
        return {"__type__": "date", "value": obj.isoformat()}
    if isinstance(obj, datetime.time):
        return {"__type__": "time", "value": obj.isoformat()}
    if isinstance(obj, datetime.timedelta):
        return {"__type__": "timedelta", "value": obj.total_seconds()}
    if isinstance(obj, decimal.Decimal):
        return {"__type__": "decimal", "value": str(obj)}
    if isinstance(obj, bytes):
        return {"__type__": "bytes", "value": obj.hex()}
    if isinstance(obj, uuid.UUID):
        return {"__type__": "uuid", "value": str(obj)}
    if isinstance(obj, (set, frozenset)):
        items: list[Any] = list(cast("Union[set[Any], frozenset[Any]]", obj))  # type: ignore[redundant-cast]
        return {"__type__": "set", "value": items}
    return None


def decode_complex_type(value: Any) -> Any:
    """Recursively decode special type markers.

    Decodes the special ``{"__type__": ..., "value": ...}`` structures.
    """
    if isinstance(value, list):
        value_list = cast("list[Any]", value)  # type: ignore[redundant-cast]
        return [decode_complex_type(v) for v in value_list]

    if not isinstance(value, dict):
        return value

    # Decode any nested values first
    value_dict = cast("dict[Any, Any]", value)  # type: ignore[redundant-cast]
    decoded: dict[str, Any] = {str(k): decode_complex_type(v) for k, v in value_dict.items()}

    # Then decode "typed" marker dicts
    if "__type__" in decoded and "value" in decoded:
        return _decode_typed_marker(decoded)

    return decoded


def _decode_typed_marker(obj: dict[str, Any]) -> Any:
    """Custom JSON decoder for special types.

    Args:
        obj: The dictionary to decode.

    Returns:
        The decoded object, or the original dict if not a special type.
    """
    type_name = obj["__type__"]
    value = obj["value"]

    if type_name == "datetime":
        return datetime.datetime.fromisoformat(value)
    if type_name == "date":
        return datetime.date.fromisoformat(value)
    if type_name == "time":
        return datetime.time.fromisoformat(value)
    if type_name == "timedelta":
        return datetime.timedelta(seconds=value)
    if type_name == "decimal":
        return decimal.Decimal(value)
    if type_name == "bytes":
        return bytes.fromhex(value)
    if type_name == "uuid":
        return uuid.UUID(value)
    if type_name == "set":
        return set(value)

    return obj
