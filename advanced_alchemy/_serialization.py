from typing import Any

__all__ = ("encode_json", "decode_json")

try:
    from msgspec.json import Decoder, Encoder

    encoder, decoder = Encoder(), Decoder()
    decode_json = decoder.decode

    def encode_json(data: Any) -> str:
        return encoder.encode(data).decode("utf-8")

except ImportError:
    try:
        from orjson import dumps as _encode_json
        from orjson import loads as decode_json  # type: ignore[no-redef,assignment]

        def encode_json(data: Any) -> str:
            return _encode_json(data).decode("utf-8")  # type: ignore[no-any-return]

    except ImportError:
        from json import dumps as encode_json  # type: ignore[assignment]
        from json import loads as decode_json  # type: ignore[assignment]
