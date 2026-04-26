import contextlib
from typing import TYPE_CHECKING, Any

from litestar.plugins import InitPluginProtocol, SerializationPlugin
from litestar.typing import FieldDefinition
from sqlalchemy.orm import DeclarativeBase

from advanced_alchemy.extensions.litestar.dto import SQLAlchemyDTO
from advanced_alchemy.extensions.litestar.plugins import _slots_base
from advanced_alchemy.utils.serialization import DEFAULT_TYPE_ENCODERS

if TYPE_CHECKING:
    from collections.abc import Callable

    from litestar.config.app import AppConfig


def _get_aa_type_encoders() -> "dict[type, Callable[[Any], Any]]":
    """Return Advanced Alchemy's built-in Litestar type encoders.

    These cover database-specific types (asyncpg's ``pgproto.UUID``,
    ``uuid_utils.UUID``) that need explicit serialization to JSON-friendly
    forms.  They are merged into ``AppConfig.type_encoders`` with lower
    precedence than user-supplied encoders.
    """
    encoders: dict[type, Callable[[Any], Any]] = {**DEFAULT_TYPE_ENCODERS}

    with contextlib.suppress(ImportError):
        from asyncpg.pgproto import pgproto  # pyright: ignore[reportMissingImports]

        encoders[pgproto.UUID] = str

    with contextlib.suppress(ImportError):
        import uuid_utils  # pyright: ignore[reportMissingImports]

        encoders[uuid_utils.UUID] = str  # pyright: ignore[reportUnknownMemberType]

    return encoders


def _get_aa_type_decoders() -> "list[tuple[Callable[[Any], bool], Callable[[type, Any], Any]]]":
    """Return Advanced Alchemy's built-in Litestar type decoders.

    Currently covers ``uuid_utils.UUID`` for request-side parsing.  Decoders
    are merged into ``AppConfig.type_decoders`` with lower precedence than
    user-supplied decoders.
    """
    decoders: list[tuple[Callable[[Any], bool], Callable[[type, Any], Any]]] = []

    with contextlib.suppress(ImportError):
        import uuid_utils  # pyright: ignore[reportMissingImports]

        decoders.append(
            (lambda x: x is uuid_utils.UUID, lambda t, v: t(str(v)))  # pyright: ignore[reportUnknownMemberType]
        )

    return decoders


class SQLAlchemySerializationPlugin(SerializationPlugin, InitPluginProtocol, _slots_base.SlotsBase):
    def __init__(self) -> None:
        self._type_dto_map: dict[type[DeclarativeBase], type[SQLAlchemyDTO[Any]]] = {}

    def on_app_init(self, app_config: "AppConfig") -> "AppConfig":
        """Register Advanced Alchemy's built-in type encoders and decoders.

        AA encoders/decoders are added with lower precedence so user-supplied
        ``type_encoders`` / ``type_decoders`` on the application config win.
        """
        aa_encoders = _get_aa_type_encoders()
        aa_decoders = _get_aa_type_decoders()
        app_config.type_encoders = {**aa_encoders, **(app_config.type_encoders or {})}
        app_config.type_decoders = [*aa_decoders, *(app_config.type_decoders or [])]
        return app_config

    def supports_type(self, field_definition: FieldDefinition) -> bool:
        return (
            field_definition.is_collection and field_definition.has_inner_subclass_of(DeclarativeBase)
        ) or field_definition.is_subclass_of(DeclarativeBase)

    def create_dto_for_type(self, field_definition: FieldDefinition) -> type[SQLAlchemyDTO[Any]]:
        # assumes that the type is a container of SQLAlchemy models or a single SQLAlchemy model
        annotation = next(
            (
                inner_type.annotation
                for inner_type in field_definition.inner_types
                if inner_type.is_subclass_of(DeclarativeBase)
            ),
            field_definition.annotation,
        )
        if annotation in self._type_dto_map:
            return self._type_dto_map[annotation]

        self._type_dto_map[annotation] = dto_type = SQLAlchemyDTO[annotation]  # type:ignore[valid-type]

        return dto_type
