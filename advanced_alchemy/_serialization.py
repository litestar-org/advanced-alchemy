# pyright: reportUnsupportedDunderAll=false
"""Deprecated shim for ``advanced_alchemy._serialization``.

Re-exports the public surface that lived here in v1.x from its new
locations under :mod:`advanced_alchemy.utils.serialization` and
:mod:`advanced_alchemy.typing`.  Importing any name from this module
emits a :class:`DeprecationWarning` via the project's
:func:`~advanced_alchemy.utils.deprecation.warn_deprecation` helper.

This module will be removed in 2.0.
"""

from typing import Any

from advanced_alchemy.utils.deprecation import warn_deprecation

_RENAMES: "dict[str, tuple[str, str]]" = {
    "BaseModel": ("advanced_alchemy.typing", "BaseModel"),
    "PYDANTIC_INSTALLED": ("advanced_alchemy.typing", "PYDANTIC_INSTALLED"),
    "encode_json": ("advanced_alchemy.utils.serialization", "encode_json"),
    "decode_json": ("advanced_alchemy.utils.serialization", "decode_json"),
    "encode_complex_type": ("advanced_alchemy.utils.serialization", "encode_complex_type"),
    "decode_complex_type": ("advanced_alchemy.utils.serialization", "decode_complex_type"),
    "convert_datetime_to_gmt_iso": ("advanced_alchemy.utils.serialization", "convert_datetime_to_gmt_iso"),
    "convert_date_to_iso": ("advanced_alchemy.utils.serialization", "convert_date_to_iso"),
}

# Names below are resolved lazily via ``__getattr__`` for the deprecation
# warning. ruff's F822 / pyright's reportUnsupportedDunderAll don't see them
# at module level — that's the point.
__all__ = (  # noqa: F822
    "PYDANTIC_INSTALLED",
    "BaseModel",
    "convert_date_to_iso",
    "convert_datetime_to_gmt_iso",
    "decode_complex_type",
    "decode_json",
    "encode_complex_type",
    "encode_json",
)


def __getattr__(name: str) -> Any:
    if name not in _RENAMES:
        msg = f"module {__name__!r} has no attribute {name!r}"
        raise AttributeError(msg)
    new_module, new_name = _RENAMES[name]
    warn_deprecation(
        version="1.10.0",
        removal_in="2.0.0",
        deprecated_name=f"{__name__}.{name}",
        kind="import",
        alternative=f"{new_module}.{new_name}",
    )
    import importlib

    return getattr(importlib.import_module(new_module), new_name)
