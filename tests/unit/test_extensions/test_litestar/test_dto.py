from __future__ import annotations

import datetime as dt
import sys
from typing import TYPE_CHECKING, Annotated, Any, ClassVar, Optional
from uuid import UUID, uuid4

import pytest
import sqlalchemy
from litestar import Request, get
from litestar.dto import DTOField, Mark
from litestar.dto.field import DTO_FIELD_META_KEY
from litestar.enums import MediaType
from litestar.plugins.pydantic import PydanticInitPlugin
from litestar.serialization import encode_json
from litestar.testing import RequestFactory, create_test_client
from litestar.typing import FieldDefinition
from sqlalchemy import ForeignKey, func, null, text
from sqlalchemy.orm import DeclarativeBase, Mapped, MappedAsDataclass, declared_attr, mapped_column, relationship
from typing_extensions import TypeVar

from advanced_alchemy.exceptions import ImproperConfigurationError
from advanced_alchemy.extensions.litestar.dto import (
    Empty,
    SQLAlchemyDTO,
    SQLAlchemyDTOConfig,
    _detect_defaults,
    parse_type_from_element,  # type: ignore
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import ModuleType


@pytest.fixture(name="base")
def fx_base() -> type[DeclarativeBase]:
    class Base(DeclarativeBase):
        id: Mapped[UUID] = mapped_column(default=uuid4, primary_key=True)
        created: Mapped[dt.datetime] = mapped_column(
            default=dt.datetime.now,
            info={DTO_FIELD_META_KEY: DTOField(mark=Mark.READ_ONLY)},
        )
        updated: Mapped[dt.datetime] = mapped_column(
            default=dt.datetime.now,
            info={DTO_FIELD_META_KEY: DTOField(mark=Mark.READ_ONLY)},
        )

        # noinspection PyMethodParameters
        @declared_attr.directive
        def __tablename__(cls) -> str:
            """Infer table name from class name."""
            return cls.__name__.lower()

    return Base


@pytest.fixture(name="author_model")
def fx_author_model(base: DeclarativeBase) -> type[DeclarativeBase]:
    class Author(base):  # type: ignore
        name: Mapped[str]
        dob: Mapped[dt.date]

    return Author


@pytest.fixture(name="raw_author")
def fx_raw_author() -> bytes:
    return b'{"id":"97108ac1-ffcb-411d-8b1e-d9183399f63b","name":"Agatha Christie","dob":"1890-09-15","created":"0001-01-01T00:00:00","updated":"0001-01-01T00:00:00"}'


@pytest.fixture(name="asgi_connection")
def fx_asgi_connection() -> Request[Any, Any, Any]:
    @get("/", name="handler_id", media_type=MediaType.JSON, type_decoders=PydanticInitPlugin.decoders())
    def _handler() -> None: ...

    return RequestFactory().get(path="/", route_handler=_handler)


T = TypeVar("T")
DataT = TypeVar("DataT", bound=DeclarativeBase)


async def get_model_from_dto(
    dto_type: type[SQLAlchemyDTO[DataT]],
    annotation: Any,
    asgi_connection: Request[Any, Any, Any],
    raw: bytes,
) -> Any:
    dto_type.create_for_field_definition(
        handler_id=asgi_connection.route_handler.handler_id,
        field_definition=FieldDefinition.from_kwarg(annotation, name="data"),
    )
    dto_type.create_for_field_definition(
        handler_id=asgi_connection.route_handler.handler_id,
        field_definition=FieldDefinition.from_kwarg(annotation, name="return"),
    )
    return dto_type(asgi_connection).decode_bytes(raw)


def assert_model_values(model_instance: DeclarativeBase, expected_values: dict[str, Any]) -> None:
    assert {k: v for k, v in model_instance.__dict__.items() if not k.startswith("_")} == expected_values


async def test_model_write_dto(
    author_model: type[DeclarativeBase],
    raw_author: bytes,
    asgi_connection: Request[Any, Any, Any],
) -> None:
    model = await get_model_from_dto(SQLAlchemyDTO[author_model], author_model, asgi_connection, raw_author)  # type: ignore
    assert_model_values(
        model,
        {
            "id": UUID("97108ac1-ffcb-411d-8b1e-d9183399f63b"),
            "name": "Agatha Christie",
            "dob": dt.date(1890, 9, 15),
        },
    )


async def test_model_read_dto(
    author_model: type[DeclarativeBase],
    raw_author: bytes,
    asgi_connection: Request[Any, Any, Any],
) -> None:
    config = SQLAlchemyDTOConfig()
    dto_type = SQLAlchemyDTO[Annotated[author_model, config]]  # type: ignore
    model = await get_model_from_dto(dto_type, author_model, asgi_connection, raw_author)
    assert_model_values(
        model,
        {
            "id": UUID("97108ac1-ffcb-411d-8b1e-d9183399f63b"),
            "name": "Agatha Christie",
            "dob": dt.date(1890, 9, 15),
        },
    )


async def test_model_list_dto(author_model: type[DeclarativeBase], asgi_connection: Request[Any, Any, Any]) -> None:
    dto_type = SQLAlchemyDTO[author_model]  # type: ignore
    raw = b'[{"id": "97108ac1-ffcb-411d-8b1e-d9183399f63b","name":"Agatha Christie","dob":"1890-09-15","created":"0001-01-01T00:00:00","updated":"0001-01-01T00:00:00"}]'
    dto_data = await get_model_from_dto(dto_type, list[author_model], asgi_connection, raw)  # type: ignore
    assert isinstance(dto_data, list)
    assert_model_values(
        dto_data[0],  # type: ignore
        {
            "id": UUID("97108ac1-ffcb-411d-8b1e-d9183399f63b"),
            "name": "Agatha Christie",
            "dob": dt.date(1890, 9, 15),
        },
    )


async def test_dto_exclude(
    author_model: type[DeclarativeBase],
    raw_author: bytes,
    asgi_connection: Request[Any, Any, Any],
) -> None:
    config = SQLAlchemyDTOConfig(exclude={"id"})
    model = await get_model_from_dto(
        SQLAlchemyDTO[Annotated[author_model, config]],  # type: ignore
        author_model,
        asgi_connection,
        raw_author,
    )
    assert "id" not in vars(model)


async def test_write_dto_field_default(base: type[DeclarativeBase], asgi_connection: Request[Any, Any, Any]) -> None:
    class Model(base):  # type: ignore
        field: Mapped[int] = mapped_column(default=3)

    dto_type = SQLAlchemyDTO[Annotated[Model, SQLAlchemyDTOConfig(exclude={"id", "created", "updated"})]]
    model = await get_model_from_dto(dto_type, Model, asgi_connection, b'{"a":"b"}')
    assert_model_values(model, {"field": 3})


async def test_write_dto_for_model_field_factory_default(
    base: type[DeclarativeBase],
    asgi_connection: Request[Any, Any, Any],
) -> None:
    val = uuid4()

    class Model(base):  # type: ignore
        field: Mapped[UUID] = mapped_column(default=lambda: val)

    dto_type = SQLAlchemyDTO[Annotated[Model, SQLAlchemyDTOConfig(exclude={"id", "created", "updated"})]]
    model = await get_model_from_dto(dto_type, Model, asgi_connection, b'{"a":"b"}')
    assert_model_values(model, {"field": val})


async def test_dto_instrumented_attribute_key(
    base: type[DeclarativeBase],
    asgi_connection: Request[Any, Any, Any],
) -> None:
    val = uuid4()

    class Model(base):  # type: ignore
        field: Mapped[UUID] = mapped_column(default=lambda: val)

    dto_type = SQLAlchemyDTO[Annotated[Model, SQLAlchemyDTOConfig(exclude={Model.id, Model.created, Model.updated})]]  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType,reportUnknownArgumentType]
    model = await get_model_from_dto(dto_type, Model, asgi_connection, b'{"a":"b"}')
    assert_model_values(model, {"field": val})


def test_write_dto_for_model_field_unsupported_default() -> None:
    """Ensure genuinely unrecognized default objects raise ValueError."""

    class _UnsupportedDefault:
        is_scalar = False
        is_callable = False
        is_sequence = False
        is_sentinel = False
        is_clause_element = False

    class _ColumnStub:
        default = _UnsupportedDefault()
        nullable = False

    with pytest.raises(ValueError, match="Unexpected default type"):
        _detect_defaults(_ColumnStub())  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "default_expr",
    [
        pytest.param(func.now(), id="func-now"),
        pytest.param(null(), id="sql-null"),
        pytest.param(text("CURRENT_TIMESTAMP"), id="sql-text"),
    ],
)
def test_clause_element_defaults_do_not_crash_dto_generation(
    base: type[DeclarativeBase],
    default_expr: Any,
) -> None:
    """Ensure SQL clause-element defaults leave DTO default as Empty without crashing startup."""

    class Model(base):  # type: ignore[valid-type, misc]
        field: Mapped[Optional[dt.datetime]] = mapped_column(default=default_expr)

    dto_cls = SQLAlchemyDTO[Annotated[Model, SQLAlchemyDTOConfig()]]
    field_defs = {f.name: f for f in dto_cls.generate_field_definitions(Model)}
    assert field_defs["field"].default is Empty


@pytest.mark.parametrize(
    "config_expr",
    [
        pytest.param('SQLAlchemyDTOConfig(include={"id", "name"})', id="include-only"),
        pytest.param(
            'SQLAlchemyDTOConfig(exclude={"geom", "topic", "topic_id", "untyped_computed"})',
            id="exclude-bad",
        ),
    ],
)
def test_dto_skips_excluded_unreflectable_columns_and_relationships(
    create_module: Callable[[str], ModuleType],
    config_expr: str,
) -> None:
    """Ensure root include/exclude skips unreflectable types and relationships before type resolution."""
    module = create_module(
        f"""
from __future__ import annotations

from typing import Annotated, Any, Optional
from litestar import get
from sqlalchemy import ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import UserDefinedType
from advanced_alchemy.extensions.litestar.dto import SQLAlchemyDTO, SQLAlchemyDTOConfig


class UnsupportedGeo(UserDefinedType[Any]):
    def get_col_spec(self, **kw: Any) -> str:
        return "GEOGRAPHY"


class Base(DeclarativeBase):
    id: Mapped[int] = mapped_column(primary_key=True)


class Topic(Base):
    __tablename__ = "dto_236_topic"
    geom = mapped_column(UnsupportedGeo())


class Item(Base):
    __tablename__ = "dto_236_item"
    name: Mapped[str]
    geom = mapped_column(UnsupportedGeo())
    topic_id: Mapped[Optional[int]] = mapped_column(ForeignKey("dto_236_topic.id"))
    topic: Mapped[Optional[Topic]] = relationship()

    @property
    def untyped_computed(self):
        return self.name


dto_cls = SQLAlchemyDTO[Annotated[Item, {config_expr}]]


@get("/items", return_dto=dto_cls, sync_to_thread=False)
def get_items() -> list[Item]:
    return [Item(id=1, name="alpha")]
""",
    )

    field_names = {f.name for f in module.dto_cls.generate_field_definitions(module.Item)}
    assert {"id", "name"}.issubset(field_names)
    assert "geom" not in field_names
    assert "untyped_computed" not in field_names

    with create_test_client(route_handlers=[module.get_items]) as client:
        response = client.get("/items")
        assert response.status_code == 200
        assert response.json() == [{"id": 1, "name": "alpha"}]


def test_dto_preserves_nested_include_and_exclude_paths(base: type[DeclarativeBase]) -> None:
    """Ensure dotted nested include and exclude keys still reflect the parent relationship."""

    class Topic(base):  # type: ignore[valid-type, misc]
        name: Mapped[str]
        secret: Mapped[str]

    class Item(base):  # type: ignore[valid-type, misc]
        name: Mapped[str]
        topic_id: Mapped[UUID] = mapped_column(ForeignKey(Topic.id))
        topic: Mapped[Topic] = relationship()

    @get(
        "/items/{item_id:str}", return_dto=SQLAlchemyDTO[Annotated[Item, SQLAlchemyDTOConfig(exclude={"topic.secret"})]]
    )
    async def get_item_exclude() -> Item:
        raise NotImplementedError

    @get(
        "/items-inc/{item_id:str}",
        return_dto=SQLAlchemyDTO[Annotated[Item, SQLAlchemyDTOConfig(include={"id", "topic.name"})]],
    )
    async def get_item_include() -> Item:
        raise NotImplementedError

    assert get_item_exclude.return_dto is not None
    assert get_item_include.return_dto is not None
    excluded_defs = {f.name: f for f in get_item_exclude.return_dto.generate_field_definitions(Item)}
    included_defs = {f.name: f for f in get_item_include.return_dto.generate_field_definitions(Item)}
    assert "topic" in excluded_defs
    assert "topic" in included_defs


async def test_dto_for_private_model_field(
    base: type[DeclarativeBase],
    asgi_connection: Request[Any, Any, Any],
) -> None:
    class Model(base):  # type: ignore
        field: Mapped[dt.datetime] = mapped_column(
            info={DTO_FIELD_META_KEY: DTOField(mark=Mark.PRIVATE)},
        )

    dto_type = SQLAlchemyDTO[Annotated[Model, SQLAlchemyDTOConfig()]]
    raw = b'{"id":"97108ac1-ffcb-411d-8b1e-d9183399f63b","created":"0001-01-01T00:00:00","updated":"0001-01-01T00:00:00","field":"0001-01-01T00:00:00"}'
    assert "field" not in vars(await get_model_from_dto(dto_type, Model, asgi_connection, raw))

    dto_instance = dto_type(asgi_connection)
    serializable = dto_instance.data_to_encodable_type(  # pyright: ignore[reportUnknownMemberType,reportUnknownVariableType]
        Model(
            id=UUID("0956ca9e-5671-4d7d-a862-b98e6368ed2c"),
            created=dt.datetime.min,
            updated=dt.datetime.min,
            field=dt.datetime.min,
        ),
    )
    assert b"field" not in encode_json(serializable)


async def test_dto_for_non_mapped_model_field(
    base: type[DeclarativeBase],
    asgi_connection: Request[Any, Any, Any],
) -> None:
    class Model(base):  # type: ignore
        field: ClassVar[dt.datetime]

    dto_type = SQLAlchemyDTO[Annotated[Model, SQLAlchemyDTOConfig()]]
    raw = b'{"id": "97108ac1-ffcb-411d-8b1e-d9183399f63b","created":"0001-01-01T00:00:00","updated":"0001-01-01T00:00:00","field":"0001-01-01T00:00:00"}'
    assert "field" not in vars(await get_model_from_dto(dto_type, Model, asgi_connection, raw))


async def test_dto_mapped_as_dataclass_model_type(
    base: type[DeclarativeBase],
    asgi_connection: Request[Any, Any, Any],
) -> None:
    """Test declare pydantic type on `dto.DTOField`."""

    class Model(base, MappedAsDataclass):  # type: ignore
        clz_var: ClassVar[str]
        field: Mapped[str]

    dto_type = SQLAlchemyDTO[Annotated[Model, SQLAlchemyDTOConfig(exclude={"id"})]]
    model = await get_model_from_dto(dto_type, Model, asgi_connection, b'{"clz_var":"nope","field":"yep"}')
    assert_model_values(model, {"field": "yep"})


async def test_to_mapped_model_with_collection_relationship(
    base: type[DeclarativeBase],
    create_module: Callable[[str], ModuleType],
    asgi_connection: Request[Any, Any, Any],
) -> None:
    """Test building a DTO with collection relationship, and parsing data."""

    module = create_module(
        """
from __future__ import annotations

from typing import Dict, List, Set, Tuple, Type, List

from sqlalchemy import ForeignKey, Integer
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from typing_extensions import Annotated

from advanced_alchemy.extensions.litestar.dto import SQLAlchemyDTO, SQLAlchemyDTOConfig

class Base(DeclarativeBase):
    id: Mapped[int] = mapped_column(primary_key=True)

class A(Base):
    __tablename__ = "a"
    b_id: Mapped[int] = mapped_column(ForeignKey("b.id"))

class B(Base):
    __tablename__ = "b"
    a: Mapped[List[A]] = relationship("A")

dto_type = SQLAlchemyDTO[Annotated[B, SQLAlchemyDTOConfig()]]
""",
    )

    model = await get_model_from_dto(
        module.dto_type,
        module.B,
        asgi_connection,
        b'{"id": 1, "a": [{"id": 2, "b_id": 1}, {"id": 3, "b_id": 1}]}',
    )
    assert isinstance(model, module.B)
    assert len(model.a) == 2
    assert all(isinstance(val, module.A) for val in model.a)


async def test_to_mapped_model_with_relationship_type_hint(
    base: type[DeclarativeBase],
    create_module: Callable[[str], ModuleType],
    asgi_connection: Request[Any, Any, Any],
) -> None:
    """Test building a DTO with collection relationship, and parsing data."""

    module = create_module(
        """
from __future__ import annotations

from typing import Dict, List, Set, Tuple, Type, List

from sqlalchemy import ForeignKey, Integer
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, Relationship
from typing_extensions import Annotated

from advanced_alchemy.extensions.litestar.dto import SQLAlchemyDTO, SQLAlchemyDTOConfig

class Base(DeclarativeBase):
    id: Mapped[int] = mapped_column(primary_key=True)

class A(Base):
    __tablename__ = "a"
    b_id: Mapped[int] = mapped_column(ForeignKey("b.id"))

class B(Base):
    __tablename__ = "b"
    a: Relationship[List[A]] = relationship("A")

dto_type = SQLAlchemyDTO[Annotated[B, SQLAlchemyDTOConfig()]]
""",
    )

    model = await get_model_from_dto(
        module.dto_type,
        module.B,
        asgi_connection,
        b'{"id": 1, "a": [{"id": 2, "b_id": 1}, {"id": 3, "b_id": 1}]}',
    )
    assert isinstance(model, module.B)
    assert len(model.a) == 2
    assert all(isinstance(val, module.A) for val in model.a)


async def test_to_mapped_model_with_scalar_relationship(
    create_module: Callable[[str], ModuleType],
    asgi_connection: Request[Any, Any, Any],
) -> None:
    """Test building DTO with Scalar relationship, and parsing data."""

    module = create_module(
        """
from __future__ import annotations

from sqlalchemy import ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from typing_extensions import Annotated

from advanced_alchemy.extensions.litestar.dto import SQLAlchemyDTO, SQLAlchemyDTOConfig

class Base(DeclarativeBase):
    id: Mapped[int] = mapped_column(primary_key=True)

class A(Base):
    __tablename__ = "a"

class B(Base):
    __tablename__ = "b"
    a_id: Mapped[int] = mapped_column(ForeignKey("a.id"))
    a: Mapped[A] = relationship(A)

dto_type = SQLAlchemyDTO[Annotated[B, SQLAlchemyDTOConfig()]]
""",
    )
    model = await get_model_from_dto(
        module.dto_type,
        module.B,
        asgi_connection,
        b'{"id": 2, "a_id": 1, "a": {"id": 1}}',
    )
    assert isinstance(model, module.B)
    assert isinstance(model.a, module.A)


async def test_dto_mapped_union(
    create_module: Callable[[str], ModuleType],
    asgi_connection: Request[Any, Any, Any],
) -> None:
    """Test where a column type declared as e.g., `Mapped[str | None]`."""

    module = create_module(
        """
from __future__ import annotations

from typing import Dict, List, Set, Tuple, Type, Union

from sqlalchemy import ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from typing_extensions import Annotated

from advanced_alchemy.extensions.litestar.dto import SQLAlchemyDTO

class Base(DeclarativeBase):
    id: Mapped[int] = mapped_column(primary_key=True)

class A(Base):
    __tablename__ = "a"
    a: Mapped[Union[str, None]]

dto_type = SQLAlchemyDTO[A]
    """,
    )
    model = await get_model_from_dto(module.dto_type, module.A, asgi_connection, b'{"id": 1}')
    assert vars(model)["a"] is None


@pytest.mark.skipif(sys.version_info < (3, 10), reason="requires python3.10 or higher")
async def test_dto_mapped_union_type(
    create_module: Callable[[str], ModuleType],
    asgi_connection: Request[Any, Any, Any],
) -> None:
    """Test where a column type declared as e.g., `Mapped[str | None]`."""

    module = create_module(
        """
from __future__ import annotations

from typing import Dict, List, Set, Tuple, Type, Union, Optional

from sqlalchemy import ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from typing_extensions import Annotated

from advanced_alchemy.extensions.litestar.dto import SQLAlchemyDTO

class Base(DeclarativeBase):
    id: Mapped[int] = mapped_column(primary_key=True)

class A(Base):
    __tablename__ = "a"
    a: Mapped[Optional[str]]

dto_type = SQLAlchemyDTO[A]
    """,
    )
    model = await get_model_from_dto(module.dto_type, module.A, asgi_connection, b'{"id": 1}')
    assert vars(model)["a"] is None
    model = await get_model_from_dto(module.dto_type, module.A, asgi_connection, b'{"id": 1, "a": "a"}')
    assert vars(model)["a"] == "a"


async def test_dto_self_referencing_relationships(
    create_module: Callable[[str], ModuleType],
    asgi_connection: Request[Any, Any, Any],
) -> None:
    module = create_module(
        """
from __future__ import annotations

from sqlalchemy import ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from advanced_alchemy.extensions.litestar.dto import SQLAlchemyDTO

class Base(DeclarativeBase):
    id: Mapped[int] = mapped_column(primary_key=True)

class A(Base):
    __tablename__ = "a"
    b_id: Mapped[int] = mapped_column(ForeignKey("b.id"))
    b: Mapped[B] = relationship(back_populates="a")

class B(Base):
    __tablename__ = "b"
    a: Mapped[A] = relationship(back_populates="b")

dto_type = SQLAlchemyDTO[A]
""",
    )
    raw = b'{"id": 1, "b_id": 1, "b": {"id": 1, "a": {"id": 1, "b_id": 1}}}'
    model = await get_model_from_dto(module.dto_type, module.A, asgi_connection, raw)
    assert isinstance(model, module.A)
    assert isinstance(model.b, module.B)
    assert isinstance(model.b.a, module.A)

    encodable_type = module.dto_type(asgi_connection).data_to_encodable_type(model)
    assert encodable_type.id == 1
    assert encodable_type.b_id == 1
    assert encodable_type.b.id == 1


async def test_dto_optional_relationship_with_none_value(
    create_module: Callable[[str], ModuleType],
    asgi_connection: Request[Any, Any, Any],
) -> None:
    module = create_module(
        """
from __future__ import annotations

from typing import Dict, List, Set, Tuple, Type, Optional

from sqlalchemy import ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from typing_extensions import Annotated

from advanced_alchemy.extensions.litestar.dto import SQLAlchemyDTO, SQLAlchemyDTOConfig

class Base(DeclarativeBase):
    id: Mapped[int] = mapped_column(primary_key=True)

class A(Base):
    __tablename__ = "a"

class B(Base):
    __tablename__ = "b"
    a_id: Mapped[Optional[int]] = mapped_column(ForeignKey("a.id"))
    a: Mapped[Optional[A]] = relationship(A)

dto_type = SQLAlchemyDTO[Annotated[B, SQLAlchemyDTOConfig()]]
""",
    )
    model = await get_model_from_dto(module.dto_type, module.B, asgi_connection, b'{"id": 2, "a_id": null, "a": null}')
    assert isinstance(model, module.B)
    assert model.a is None


async def test_dto_nullable_one_to_one_inverse_relationship(
    create_module: Callable[[str], ModuleType],
    asgi_connection: Request[Any, Any, Any],
) -> None:
    """Test that nullable one-to-one relationships on the inverse side (no FK) are handled correctly.

    Regression test for https://github.com/jolt-org/advanced-alchemy/issues/227.
    When the FK is on the other model and uselist=False, the DTO should allow None.
    """
    module = create_module(
        """
from __future__ import annotations

from typing import Optional

from sqlalchemy import ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from typing_extensions import Annotated

from advanced_alchemy.extensions.litestar.dto import SQLAlchemyDTO, SQLAlchemyDTOConfig

class Base(DeclarativeBase):
    id: Mapped[int] = mapped_column(primary_key=True)

class B(Base):
    __tablename__ = "b"
    a_id: Mapped[int] = mapped_column(ForeignKey("a.id"))
    a: Mapped["A"] = relationship(back_populates="b")

class A(Base):
    __tablename__ = "a"
    b: Mapped[Optional[B]] = relationship(back_populates="a")

dto_type = SQLAlchemyDTO[Annotated[A, SQLAlchemyDTOConfig()]]
""",
    )
    model = await get_model_from_dto(module.dto_type, module.A, asgi_connection, b'{"id": 1, "b": null}')
    assert isinstance(model, module.A)
    assert model.b is None


async def test_forward_ref_relationship_resolution(
    create_module: Callable[[str], ModuleType],
    asgi_connection: Request[Any, Any, Any],
) -> None:
    """Testing that classes related to the mapped class for the dto are considered for forward-ref resolution.

    The key part of this test is that the `B` type is only imported inside an `if TYPE_CHECKING:` block
    in `a_module`, so it should not be available for forward-ref resolution when `a_module` is imported. This
    works due to related mapped classes (via `mapper.registry.mappers`) being added to forward-ref resolution
    namespace.
    """
    base_module = create_module(
        """
from __future__ import annotations
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    id: Mapped[int] = mapped_column(primary_key=True)
""",
    )

    b_module = create_module(
        f"""
from __future__ import annotations

from {base_module.__name__} import Base

class B(Base):
    __tablename__ = "b"
""",
    )

    a_module = create_module(
        f"""
from __future__ import annotations

from typing import Dict, List, Set, Tuple, Type, TYPE_CHECKING

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing_extensions import Annotated

from advanced_alchemy.extensions.litestar.dto import SQLAlchemyDTO, SQLAlchemyDTOConfig

from {base_module.__name__} import Base

if TYPE_CHECKING:
    from {b_module.__name__} import B

class A(Base):
    __tablename__ = "a"
    b_id: Mapped[int] = mapped_column(ForeignKey("b.id"))
    b: Mapped[B] = relationship()

dto_type = SQLAlchemyDTO[Annotated[A, SQLAlchemyDTOConfig()]]
""",
    )

    model = await get_model_from_dto(
        a_module.dto_type,
        a_module.A,
        asgi_connection,
        b'{"id": 1, "b_id": 2, "b": {"id": 2}}',
    )
    assert isinstance(model, a_module.A)
    assert isinstance(model.b, b_module.B)


async def test_dto_mapped_builtin_collection(
    create_module: Callable[[str], ModuleType],
    asgi_connection: Request[Any, Any, Any],
) -> None:
    """Test where a column type declared as e.g., `Mapped[dict]`."""

    module = create_module(
        """
from __future__ import annotations

from typing import Dict, List, Set, Tuple, Type, Union

from sqlalchemy import ForeignKey, Integer
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON, ARRAY
from typing_extensions import Annotated

from advanced_alchemy.extensions.litestar.dto import SQLAlchemyDTO

class Base(DeclarativeBase):
    id: Mapped[int] = mapped_column(primary_key=True)

class A(Base):
    __tablename__ = "a"
    a: Mapped[dict] = mapped_column(JSON)
    c: Mapped[list] = mapped_column(ARRAY(Integer))

dto_type = SQLAlchemyDTO[A]
    """,
    )
    model = await get_model_from_dto(
        module.dto_type,
        module.A,
        asgi_connection,
        b'{"id": 1, "a": {"b": 1}, "c": [1, 2, 3]}',
    )
    assert vars(model)["a"] == {"b": 1}
    assert vars(model)["c"] == [1, 2, 3]


async def test_no_type_hint_column(base: type[DeclarativeBase], asgi_connection: Request[Any, Any, Any]) -> None:
    class Model(base):  # type: ignore
        nullable_field = mapped_column(sqlalchemy.String)
        not_nullable_field = mapped_column(sqlalchemy.String, nullable=False, default="")

    dto_type = SQLAlchemyDTO[Annotated[Model, SQLAlchemyDTOConfig()]]
    model = await get_model_from_dto(dto_type, Model, asgi_connection, b"{}")
    assert model.nullable_field is None
    assert model.not_nullable_field == ""


async def test_no_type_hint_scalar_relationship_with_nullable_fk(
    base: type[DeclarativeBase],
    asgi_connection: Request[Any, Any, Any],
) -> None:
    class Child(base):  # type: ignore
        ...

    class Model(base):  # type: ignore
        child_id = mapped_column(ForeignKey("child.id"))
        child = relationship(Child)

    dto_type = SQLAlchemyDTO[Annotated[Model, SQLAlchemyDTOConfig(exclude={"child_id"})]]
    model = await get_model_from_dto(dto_type, Model, asgi_connection, b"{}")
    assert model.child is None


async def test_no_type_hint_scalar_relationship_with_not_nullable_fk(
    base: type[DeclarativeBase],
    asgi_connection: Request[Any, Any, Any],
) -> None:
    class Child(base):  # type: ignore
        ...

    class Model(base):  # type: ignore
        child_id = mapped_column(ForeignKey("child.id"), nullable=False)
        child = relationship(Child)

    dto_type = SQLAlchemyDTO[Annotated[Model, SQLAlchemyDTOConfig(exclude={"child_id"})]]
    model = await get_model_from_dto(dto_type, Model, asgi_connection, b'{"child": {}}')
    assert isinstance(model.child, Child)


async def test_no_type_hint_collection_relationship(
    base: type[DeclarativeBase],
    asgi_connection: Request[Any, Any, Any],
) -> None:
    class Child(base):  # type: ignore
        model_id = mapped_column(ForeignKey("model.id"))

    class Model(base):  # type: ignore
        children = relationship(Child)

    dto_type = SQLAlchemyDTO[Annotated[Model, SQLAlchemyDTOConfig()]]
    model = await get_model_from_dto(dto_type, Model, asgi_connection, b'{"children": []}')
    assert model.children == []


async def test_no_type_hint_collection_relationship_alt_collection_class(
    base: type[DeclarativeBase],
    asgi_connection: Request[Any, Any, Any],
) -> None:
    class Child(base):  # type: ignore
        model_id = mapped_column(ForeignKey("model.id"))

    class Model(base):  # type: ignore
        children = relationship(Child, collection_class=set)

    dto_type = SQLAlchemyDTO[Annotated[Model, SQLAlchemyDTOConfig()]]
    model = await get_model_from_dto(dto_type, Model, asgi_connection, b'{"children": []}')
    assert model.children == set()


def test_parse_type_from_element_failure() -> None:
    with pytest.raises(ImproperConfigurationError) as exc:
        parse_type_from_element(1, None)  # type: ignore
    assert str(exc.value) == "Unable to parse type from element '1'. Consider adding a type hint."


async def test_to_mapped_model_with_dynamic_mapped(
    create_module: Callable[[str], ModuleType],
    asgi_connection: Request[Any, Any, Any],
) -> None:
    """Test building DTO with DynamicMapped relationship, and parsing data."""

    module = create_module(
        """
from __future__ import annotations

from sqlalchemy import ForeignKey
from sqlalchemy.orm import DeclarativeBase, DynamicMapped, Mapped, mapped_column, relationship, WriteOnlyMapped
from typing import List
from typing_extensions import Annotated

from advanced_alchemy.extensions.litestar.dto import SQLAlchemyDTO, SQLAlchemyDTOConfig

class Base(DeclarativeBase):
    id: Mapped[int] = mapped_column(primary_key=True)

class Child(Base):
    __tablename__ = "child"
    test_model_id: Mapped[int] = mapped_column(ForeignKey("test_model.id"))

class TestModel(Base):
    __tablename__ = "test_model"
    children: DynamicMapped[List[Child]] = relationship(Child, lazy="joined")

dto_type = SQLAlchemyDTO[Annotated[TestModel, SQLAlchemyDTOConfig()]]
""",
    )
    model = await get_model_from_dto(
        module.dto_type,
        module.TestModel,
        asgi_connection,
        b'{"id": 2, "children": [{"id": 1, "test_model_id": 2}]}',
    )
    assert isinstance(model, module.TestModel)
    # For DynamicMapped, we should check the query result
    child = model.children[0]  # Access first item from the dynamic query
    assert isinstance(child, module.Child)


async def test_to_mapped_model_with_writeonly_mapped(
    create_module: Callable[[str], ModuleType],
    asgi_connection: Request[Any, Any, Any],
) -> None:
    """Test building DTO with WriteOnlyMapped relationship, and parsing data."""

    module = create_module(
        """
from __future__ import annotations

from sqlalchemy import ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, WriteOnlyMapped, mapped_column, relationship
from typing import List
from typing_extensions import Annotated

from litestar.dto.field import Mark, dto_field
from advanced_alchemy.extensions.litestar.dto import SQLAlchemyDTO, SQLAlchemyDTOConfig

class Base(DeclarativeBase):
    id: Mapped[int] = mapped_column(primary_key=True)

class Child(Base):
    __tablename__ = "child"
    test_model_id: Mapped[int] = mapped_column(ForeignKey("test_model.id"))

class TestModel(Base):
    __tablename__ = "test_model"
    children: WriteOnlyMapped[List[Child]] = relationship(Child, info=dto_field(mark=Mark.WRITE_ONLY))

dto_type = SQLAlchemyDTO[Annotated[TestModel, SQLAlchemyDTOConfig()]]
""",
    )
    model = await get_model_from_dto(
        module.dto_type,
        module.TestModel,
        asgi_connection,
        b'{"id": 2, "children": [{"id": 1, "test_model_id": 2}]}',
    )
    assert isinstance(model, module.TestModel)


def test_dto_exclude_and_include_skip_untyped_descriptors(
    create_module: Callable[[str], ModuleType],
) -> None:
    """Verify excluded or unincluded untyped descriptors do not break handler DTO serialization (#236)."""
    module = create_module(
        """
from __future__ import annotations

from typing import Optional
from typing_extensions import Annotated
import sqlalchemy
from litestar import get
from sqlalchemy import ForeignKey
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from advanced_alchemy.extensions.litestar.dto import SQLAlchemyDTO, SQLAlchemyDTOConfig


class Base(DeclarativeBase):
    id: Mapped[int] = mapped_column(primary_key=True)


class RelatedItem(Base):
    __tablename__ = "related_item_236"
    title: Mapped[str] = mapped_column(sqlalchemy.String)


class ItemWithUntypedDescriptors(Base):
    __tablename__ = "item_untyped_236"
    name: Mapped[str] = mapped_column(sqlalchemy.String)
    related_id: Mapped[int] = mapped_column(ForeignKey("related_item_236.id"))
    related: Mapped[RelatedItem] = relationship(RelatedItem)
    untyped_proxy = association_proxy("related", "title")
    untyped_hybrid = hybrid_property(lambda self: self.name)

    @property
    def untyped_prop(self):
        return self.name


exclude_dto = SQLAlchemyDTO[
    Annotated[
        ItemWithUntypedDescriptors,
        SQLAlchemyDTOConfig(exclude={"untyped_hybrid", "untyped_proxy", "untyped_prop"}),
    ]
]
include_dto = SQLAlchemyDTO[
    Annotated[
        ItemWithUntypedDescriptors,
        SQLAlchemyDTOConfig(include={"id", "name", "related.title"}),
    ]
]


@get("/excluded", return_dto=exclude_dto, sync_to_thread=False)
def get_excluded() -> ItemWithUntypedDescriptors:
    return ItemWithUntypedDescriptors(
        id=1,
        name="widget",
        related_id=10,
        related=RelatedItem(id=10, title="parent"),
    )


@get("/included", return_dto=include_dto, sync_to_thread=False)
def get_included() -> ItemWithUntypedDescriptors:
    return ItemWithUntypedDescriptors(
        id=1,
        name="widget",
        related_id=10,
        related=RelatedItem(id=10, title="parent"),
    )
""",
    )

    with create_test_client(route_handlers=[module.get_excluded, module.get_included]) as client:
        excluded_response = client.get("/excluded")
        assert excluded_response.status_code == 200
        assert excluded_response.json() == {
            "id": 1,
            "name": "widget",
            "related_id": 10,
            "related": {"id": 10, "title": "parent"},
        }

        included_response = client.get("/included")
        assert included_response.status_code == 200
        assert included_response.json() == {
            "id": 1,
            "name": "widget",
            "related": {"title": "parent"},
        }


@pytest.mark.parametrize(
    ("config_expr", "expected"),
    [
        (
            'SQLAlchemyDTOConfig(exclude={"id", "parent_id"})',
            {"name": "root", "children": [{"id": 2, "parent_id": 1, "name": "child"}]},
        ),
        (
            'SQLAlchemyDTOConfig(include={"id", "children.0.name"})',
            {"id": 1, "children": [{"name": "child"}]},
        ),
    ],
)
def test_dto_root_filters_do_not_apply_to_nested_same_type(
    create_module: Callable[[str], ModuleType],
    config_expr: str,
    expected: dict[str, Any],
) -> None:
    """Verify root exclude and include settings do not strip fields from nested occurrences of the same model."""
    module = create_module(
        f"""
from __future__ import annotations

from typing import Optional
from typing_extensions import Annotated
import sqlalchemy
from litestar import get
from sqlalchemy import ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from advanced_alchemy.extensions.litestar.dto import SQLAlchemyDTO, SQLAlchemyDTOConfig


class Base(DeclarativeBase):
    id: Mapped[int] = mapped_column(primary_key=True)


class Node(Base):
    __tablename__ = "self_ref_node"
    name: Mapped[str] = mapped_column(sqlalchemy.String)
    parent_id: Mapped[Optional[int]] = mapped_column(ForeignKey("self_ref_node.id"), default=None)
    children: Mapped[list[Node]] = relationship("Node")


dto_type = SQLAlchemyDTO[Annotated[Node, {config_expr}]]


@get("/tree", return_dto=dto_type, sync_to_thread=False)
def get_tree() -> Node:
    child = Node(id=2, name="child", parent_id=1, children=[])
    return Node(id=1, name="root", parent_id=None, children=[child])
""",
    )

    with create_test_client(route_handlers=[module.get_tree]) as client:
        response = client.get("/tree")
        assert response.status_code == 200
        assert response.json() == expected
