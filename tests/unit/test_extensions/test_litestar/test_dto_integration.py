from __future__ import annotations

from dataclasses import dataclass
from types import ModuleType
from typing import Any, Callable, Dict, List, Tuple
from uuid import UUID

import pytest
from litestar import get, post
from litestar.di import Provide
from litestar.dto import DTOField, Mark
from litestar.dto._backend import _camelize  # type: ignore
from litestar.dto.field import DTO_FIELD_META_KEY
from litestar.dto.types import RenameStrategy
from litestar.testing import create_test_client  # type: ignore
from sqlalchemy import Column, ForeignKey, Integer, String, Table, func, select
from sqlalchemy.ext.associationproxy import AssociationProxy, association_proxy
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    column_property,
    composite,
    declared_attr,
    mapped_column,
    relationship,
)
from typing_extensions import Annotated

from advanced_alchemy.extensions.litestar.dto import SQLAlchemyDTO, SQLAlchemyDTOConfig


class Base(DeclarativeBase):
    id: Mapped[str] = mapped_column(primary_key=True, default=UUID)  # pyright: ignore

    # noinspection PyMethodParameters
    @declared_attr.directive
    def __tablename__(cls) -> str:
        """Infer table name from class name."""
        return cls.__name__.lower()


class Tag(Base):
    name: Mapped[str] = mapped_column(default="best seller")  # pyright: ignore


class TaggableMixin:
    @classmethod
    @declared_attr.directive
    def tag_association_table(cls) -> Table:
        return Table(
            f"{cls.__tablename__}_tag_association",  # type: ignore
            cls.metadata,  # type: ignore
            Column("base_id", ForeignKey(f"{cls.__tablename__}.id", ondelete="CASCADE"), primary_key=True),  # pyright: ignore # type: ignore
            Column("tag_id", ForeignKey("tag.id", ondelete="CASCADE"), primary_key=True),  # pyright: ignore # type: ignore
        )

    @declared_attr
    def assigned_tags(cls) -> Mapped[List[Tag]]:
        return relationship(
            "Tag",
            secondary=lambda: cls.tag_association_table,
            lazy="immediate",
            cascade="all, delete",
            passive_deletes=True,
        )

    @declared_attr
    def tags(cls) -> AssociationProxy[List[str]]:
        return association_proxy(
            "assigned_tags",
            "name",
            creator=lambda name: Tag(name=name),  # pyright: ignore
            info={"__dto__": DTOField()},
        )


class Author(Base):
    name: Mapped[str] = mapped_column(default="Arthur")  # pyright: ignore
    date_of_birth: Mapped[str] = mapped_column(nullable=True)  # pyright: ignore


class BookReview(Base):
    review: Mapped[str]  # pyright: ignore
    book_id: Mapped[str] = mapped_column(ForeignKey("book.id"), default="000")  # pyright: ignore


class Book(Base):
    title: Mapped[str] = mapped_column(String(length=250), default="Hi")  # pyright: ignore
    author_id: Mapped[str] = mapped_column(ForeignKey("author.id"), default="123")  # pyright: ignore
    first_author: Mapped[Author] = relationship(lazy="joined", innerjoin=True)  # pyright: ignore
    reviews: Mapped[List[BookReview]] = relationship(lazy="joined", innerjoin=True)  # pyright: ignore
    bar: Mapped[str] = mapped_column(default="Hello")  # pyright: ignore
    SPAM: Mapped[str] = mapped_column(default="Bye")  # pyright: ignore
    spam_bar: Mapped[str] = mapped_column(default="Goodbye")  # pyright: ignore
    number_of_reviews: Mapped[int | None] = column_property(
        select(func.count(BookReview.id)).where(BookReview.book_id == id).scalar_subquery(),  # type: ignore
    )


def _rename_field(name: str, strategy: RenameStrategy) -> str:
    if callable(strategy):
        return strategy(name)

    if strategy == "camel":
        return _camelize(value=name, capitalize_first_letter=False)

    if strategy == "pascal":
        return _camelize(value=name, capitalize_first_letter=True)

    return name.lower() if strategy == "lower" else name.upper()


@dataclass
class BookAuthorTestData:
    book_id: str = "000"
    book_title: str = "TDD Python"
    book_author_id: str = "123"
    book_author_name: str = "Harry Percival"
    book_author_date_of_birth: str = "01/01/1900"
    book_bar: str = "Hi"
    book_SPAM: str = "Bye"
    book_spam_bar: str = "GoodBye"
    book_review_id: str = "23432"
    book_review: str = "Excellent!"
    number_of_reviews: int | None = None


@pytest.fixture
def book_json_data() -> Callable[[RenameStrategy, BookAuthorTestData], Tuple[Dict[str, Any], Book]]:
    def _generate(rename_strategy: RenameStrategy, test_data: BookAuthorTestData) -> Tuple[Dict[str, Any], Book]:
        data: Dict[str, Any] = {
            _rename_field(name="id", strategy=rename_strategy): test_data.book_id,
            _rename_field(name="title", strategy=rename_strategy): test_data.book_title,
            _rename_field(name="author_id", strategy=rename_strategy): test_data.book_author_id,
            _rename_field(name="bar", strategy=rename_strategy): test_data.book_bar,
            _rename_field(name="SPAM", strategy=rename_strategy): test_data.book_SPAM,
            _rename_field(name="spam_bar", strategy=rename_strategy): test_data.book_spam_bar,
            _rename_field(name="first_author", strategy=rename_strategy): {
                _rename_field(name="id", strategy=rename_strategy): test_data.book_author_id,
                _rename_field(name="name", strategy=rename_strategy): test_data.book_author_name,
                _rename_field(name="date_of_birth", strategy=rename_strategy): test_data.book_author_date_of_birth,
            },
            _rename_field(name="reviews", strategy=rename_strategy): [
                {
                    _rename_field(name="book_id", strategy=rename_strategy): test_data.book_id,
                    _rename_field(name="id", strategy=rename_strategy): test_data.book_review_id,
                    _rename_field(name="review", strategy=rename_strategy): test_data.book_review,
                },
            ],
            _rename_field(name="number_of_reviews", strategy=rename_strategy): test_data.number_of_reviews,
        }
        book = Book(
            id=test_data.book_id,
            title=test_data.book_title,
            author_id=test_data.book_author_id,
            bar=test_data.book_bar,
            SPAM=test_data.book_SPAM,
            spam_bar=test_data.book_spam_bar,
            first_author=Author(
                id=test_data.book_author_id,
                name=test_data.book_author_name,
                date_of_birth=test_data.book_author_date_of_birth,
            ),
            reviews=[
                BookReview(id=test_data.book_review_id, review=test_data.book_review, book_id=test_data.book_id),
            ],
        )
        return data, book

    return _generate


@pytest.mark.parametrize(
    "rename_strategy",
    ("camel",),
)
def test_fields_alias_generator_sqlalchemy(
    rename_strategy: RenameStrategy,
    book_json_data: Callable[[RenameStrategy, BookAuthorTestData], Tuple[Dict[str, Any], Book]],
) -> None:
    test_data = BookAuthorTestData()
    json_data, instance = book_json_data(rename_strategy, test_data)
    config = SQLAlchemyDTOConfig(rename_strategy=rename_strategy)
    dto = SQLAlchemyDTO[Annotated[Book, config]]

    @post(dto=dto, signature_namespace={"Book": Book})
    def post_handler(data: Book) -> Book:
        return data

    @get(dto=dto, signature_namespace={"Book": Book})
    def get_handler() -> Book:
        return instance

    with create_test_client(
        route_handlers=[post_handler, get_handler],
    ) as client:
        response_callback = client.get("/")
        assert response_callback.json() == json_data

        response_callback = client.post("/", json=json_data)
        assert response_callback.json() == json_data


class ConcreteBase(Base):
    pass


func_result_query = select(func.count()).scalar_subquery()
model_with_func_query = select(ConcreteBase, func_result_query.label("func_result")).subquery()


class ModelWithFunc(Base):
    __table__ = model_with_func_query
    func_result: Mapped[int | None] = column_property(model_with_func_query.c.func_result)


def test_model_using_func() -> None:
    instance = ModelWithFunc(id="hi")
    config = SQLAlchemyDTOConfig()
    dto = SQLAlchemyDTO[Annotated[ModelWithFunc, config]]

    @get(dto=dto, signature_namespace={"ModelWithFunc": ModelWithFunc})
    async def get_handler() -> ModelWithFunc:
        return instance

    with create_test_client(
        route_handlers=[get_handler],
    ) as client:
        response_callback = client.get("/")
        assert response_callback


def test_dto_with_association_proxy(create_module: Callable[[str], ModuleType]) -> None:
    module = create_module(
        """
from __future__ import annotations

from typing import Dict, List, Set, Tuple, Type, Final, List

from sqlalchemy import Column
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import Table
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.ext.associationproxy import AssociationProxy

from litestar import get
from advanced_alchemy.extensions.litestar.dto import SQLAlchemyDTO
from litestar.dto import dto_field

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "user"
    id: Mapped[int] = mapped_column(primary_key=True)
    kw: Mapped[List[Keyword]] = relationship(secondary=lambda: user_keyword_table, info=dto_field("private"))
    # proxy the 'keyword' attribute from the 'kw' relationship
    keywords: AssociationProxy[List[str]] = association_proxy("kw", "keyword")

class Keyword(Base):
    __tablename__ = "keyword"
    id: Mapped[int] = mapped_column(primary_key=True)
    keyword: Mapped[str] = mapped_column(String(64))

user_keyword_table: Final[Table] = Table(
    "user_keyword",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("user.id"), primary_key=True),
    Column("keyword_id", Integer, ForeignKey("keyword.id"), primary_key=True),
)

dto = SQLAlchemyDTO[User]

@get("/", return_dto=dto)
async def get_handler() -> User:
    return User(id=1, kw=[Keyword(keyword="bar"), Keyword(keyword="baz")])
""",
    )

    with create_test_client(route_handlers=[module.get_handler]) as client:
        response = client.get("/")
        assert response.json() == {"id": 1, "keywords": ["bar", "baz"]}


def test_dto_with_hybrid_property(create_module: Callable[[str], ModuleType]) -> None:
    module = create_module(
        """
from __future__ import annotations

from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from litestar import get
from advanced_alchemy.extensions.litestar.dto import SQLAlchemyDTO

class Base(DeclarativeBase):
    pass

class Interval(Base):
    __tablename__ = 'interval'

    id: Mapped[int] = mapped_column(primary_key=True)
    start: Mapped[int]
    end: Mapped[int]

    @hybrid_property
    def length(self) -> int:
        return self.end - self.start

dto = SQLAlchemyDTO[Interval]

@get("/", return_dto=dto)
async def get_handler() -> Interval:
    return Interval(id=1, start=1, end=3)
""",
    )

    with create_test_client(route_handlers=[module.get_handler]) as client:
        response = client.get("/")
        assert response.json() == {"id": 1, "start": 1, "end": 3, "length": 2}


def test_dto_with_hybrid_property_expression(create_module: Callable[[str], ModuleType]) -> None:
    module = create_module(
        """
from __future__ import annotations

from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.sql import SQLColumnExpression

from litestar import get
from advanced_alchemy.extensions.litestar.dto import SQLAlchemyDTO

class Base(DeclarativeBase):
    pass

class Interval(Base):
    __tablename__ = 'interval'

    id: Mapped[int] = mapped_column(primary_key=True)
    start: Mapped[int]
    end: Mapped[int]

    @hybrid_property
    def length(self) -> int:
        return self.end - self.start

    @length.inplace.expression
    def _length_expression(cls) -> SQLColumnExpression[int]:
        return cls.end - cls.start

dto = SQLAlchemyDTO[Interval]

@get("/", return_dto=dto)
async def get_handler() -> Interval:
    return Interval(id=1, start=1, end=3)
""",
    )

    with create_test_client(route_handlers=[module.get_handler]) as client:
        response = client.get("/")
        assert response.json() == {"id": 1, "start": 1, "end": 3, "length": 2}


def test_dto_with_hybrid_property_setter(create_module: Callable[[str], ModuleType]) -> None:
    module = create_module(
        """
from __future__ import annotations

from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.sql import SQLColumnExpression

from litestar import post
from advanced_alchemy.extensions.litestar.dto import SQLAlchemyDTO
from litestar.dto import dto_field

class Base(DeclarativeBase):
    pass

class Circle(Base):
    __tablename__ = 'circle'

    id: Mapped[int] = mapped_column(primary_key=True, info=dto_field("read-only"))
    diameter: Mapped[float] = mapped_column(info=dto_field("private"))

    @hybrid_property
    def radius(self) -> float:
        return self.diameter / 2

    @radius.inplace.setter
    def _radius_setter(self, value: float) -> None:
        self.diameter = value * 2

dto = SQLAlchemyDTO[Circle]

DIAMETER: float = 0

@post("/", dto=dto, sync_to_thread=False)
def get_handler(data: Circle) -> Circle:
    global DIAMETER
    DIAMETER = data.diameter
    data.id = 1
    return data
""",
    )

    with create_test_client(route_handlers=[module.get_handler]) as client:
        response = client.post("/", json={"radius": 5})
        assert response.json() == {"id": 1, "radius": 5}
        assert module.DIAMETER == 10


@pytest.mark.skip(reason="Debug me!")
async def test_dto_with_composite_map() -> None:
    @dataclass
    class Point:
        x: int
        y: int

    class Vertex1(Base):
        start: Mapped[Point] = composite(mapped_column("x1"), mapped_column("y1"))
        end: Mapped[Point] = composite(mapped_column("x2"), mapped_column("y2"))

    dto = SQLAlchemyDTO[Vertex1]

    @post(dto=dto, signature_namespace={"Vertex": Vertex1})
    async def post_handler(data: Vertex1) -> Vertex1:
        return data

    with create_test_client(route_handlers=[post_handler]) as client:
        response = client.post(
            "/",
            json={
                "id": "1",
                "start": {"x": 10, "y": 20},
                "end": {"x": 1, "y": 2},
            },
        )
        assert response.json() == {
            "id": "1",
            "start": {"x": 10, "y": 20},
            "end": {"x": 1, "y": 2},
        }


@pytest.mark.skip(reason="Debug me!")
async def test_dto_with_composite_map_using_explicit_columns() -> None:
    @dataclass
    class Point:
        x: int
        y: int

    class Vertex2(Base):
        x1: Mapped[int]
        y1: Mapped[int]
        x2: Mapped[int]
        y2: Mapped[int]

        start: Mapped[Point] = composite("x1", "y1")
        end: Mapped[Point] = composite("x2", "y2")

    dto = SQLAlchemyDTO[Vertex2]

    @post(dto=dto, signature_namespace={"Vertex": Vertex2})
    async def post_handler(data: Vertex2) -> Vertex2:
        return data

    with create_test_client(route_handlers=[post_handler]) as client:
        response = client.post(
            "/",
            json={
                "id": "1",
                "start": {"x": 10, "y": 20},
                "end": {"x": 1, "y": 2},
            },
        )
        assert response.json() == {
            "id": "1",
            "start": {"x": 10, "y": 20},
            "end": {"x": 1, "y": 2},
        }


@pytest.mark.skip(reason="Debug me!")
async def test_dto_with_composite_map_using_hybrid_imperative_mapping() -> None:
    @dataclass
    class Point:
        x: int
        y: int

    table = Table(
        "vertices2",
        Base.metadata,
        Column("id", String, primary_key=True),
        Column("x1", Integer),
        Column("y1", Integer),
        Column("x2", Integer),
        Column("y2", Integer),
    )

    class Vertex3(Base):
        __table__ = table

        id: Mapped[str]

        start = composite(Point, table.c.x1, table.c.y1)
        end = composite(Point, table.c.x2, table.c.y2)

    dto = SQLAlchemyDTO[Vertex3]

    @post(dto=dto, signature_namespace={"Vertex": Vertex3})
    async def post_handler(data: Vertex3) -> Vertex3:
        return data

    with create_test_client(route_handlers=[post_handler]) as client:
        response = client.post(
            "/",
            json={
                "id": "1",
                "start": {"x": 10, "y": 20},
                "end": {"x": 1, "y": 2},
            },
        )
        assert response.json() == {
            "id": "1",
            "start": {"x": 10, "y": 20},
            "end": {"x": 1, "y": 2},
        }


async def test_field_with_sequence_default(create_module: Callable[[str], ModuleType]) -> None:
    module = create_module(
        """
from sqlalchemy import create_engine, Column, Integer, Sequence
from sqlalchemy.orm import DeclarativeBase, Mapped, sessionmaker

from litestar import Litestar, post
from advanced_alchemy.extensions.litestar.dto import SQLAlchemyDTO, SQLAlchemyDTOConfig

engine = create_engine('sqlite:///:memory:', echo=True)
Session = sessionmaker(bind=engine, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

class Model(Base):
    __tablename__ = "model"
    id: Mapped[int] = Column(Integer, Sequence('model_id_seq', optional=False), primary_key=True)
    val: Mapped[str]

class ModelCreateDTO(SQLAlchemyDTO[Model]):
    config = SQLAlchemyDTOConfig(exclude={"id"})

ModelReturnDTO = SQLAlchemyDTO[Model]

@post("/", dto=ModelCreateDTO, return_dto=ModelReturnDTO, sync_to_thread=False)
def post_handler(data: Model) -> Model:
    Base.metadata.create_all(engine)

    with Session() as session:
        session.add(data)
        session.commit()

    return data
    """,
    )
    with create_test_client(route_handlers=[module.post_handler]) as client:
        response = client.post("/", json={"id": 1, "val": "value"})
        assert response.json() == {"id": 1, "val": "value"}


async def test_disable_implicitly_mapped_columns_using_annotated_notation() -> None:
    class Base(DeclarativeBase):
        id: Mapped[int] = mapped_column(default=int, primary_key=True)

    table = Table(
        "vertices2",
        Base.metadata,
        Column("id", Integer, primary_key=True),
        Column("field", String, nullable=True),
    )

    class Model(Base):
        __table__ = table
        id: Mapped[int]

        @hybrid_property
        def id_multiplied(self) -> int:
            return self.id * 10

    dto_type = SQLAlchemyDTO[Annotated[Model, SQLAlchemyDTOConfig(include_implicit_fields=False)]]

    @get(
        dto=None,
        return_dto=dto_type,
        signature_namespace={"Model": Model},
        dependencies={"model": Provide(lambda: Model(id=123, field="hi"), sync_to_thread=False)},
    )
    async def post_handler(model: Model) -> Model:
        return model

    with create_test_client(route_handlers=[post_handler]) as client:
        response = client.get(
            "/",
        )

        json = response.json()
        assert json.get("field") is None
        assert json.get("id_multiplied") is None


async def test_disable_implicitly_mapped_columns_special() -> None:
    class Base(DeclarativeBase):
        id: Mapped[int] = mapped_column(default=int, primary_key=True)

    table = Table(
        "vertices2",
        Base.metadata,
        Column("id", Integer, primary_key=True),
        Column("field", String, nullable=True),
    )

    class Model(Base):
        __table__ = table
        id: Mapped[int]

    class dto_type(SQLAlchemyDTO[Model]):
        config = SQLAlchemyDTOConfig(include_implicit_fields=False)

    @get(
        dto=None,
        return_dto=dto_type,
        signature_namespace={"Model": Model},
        dependencies={"model": Provide(lambda: Model(id=123, field="hi"), sync_to_thread=False)},
    )
    async def post_handler(model: Model) -> Model:
        return model

    with create_test_client(route_handlers=[post_handler]) as client:
        response = client.get(
            "/",
        )

        json = response.json()
        assert json.get("field") is None


async def test_disable_implicitly_mapped_columns_with_hybrid_properties_and_Mark_overrides() -> None:
    class Base(DeclarativeBase):
        id: Mapped[int] = mapped_column(default=int, primary_key=True)

    table = Table(
        "vertices2",
        Base.metadata,
        Column("id", Integer, primary_key=True),
        Column("field", String, nullable=True),
        Column("field2", String),
        Column("field3", String),
        Column("field4", String),
    )

    class Model(Base):
        __table__ = table
        id: Mapped[int]
        field2 = column_property(table.c.field2, info={DTO_FIELD_META_KEY: DTOField(mark=Mark.READ_ONLY)})  # type: ignore
        field3 = column_property(table.c.field3, info={DTO_FIELD_META_KEY: DTOField(mark=Mark.WRITE_ONLY)})  # type: ignore
        field4 = column_property(table.c.field4, info={DTO_FIELD_META_KEY: DTOField(mark=Mark.PRIVATE)})  # type: ignore

        @hybrid_property
        def id_multiplied(self) -> int:
            return self.id * 10

    dto_type = SQLAlchemyDTO[
        Annotated[
            Model,
            SQLAlchemyDTOConfig(include_implicit_fields="hybrid-only"),
        ]
    ]

    @get(
        dto=None,
        return_dto=dto_type,
        signature_namespace={"Model": Model},
        dependencies={
            "model": Provide(
                lambda: Model(id=12, field="hi", field2="bye2", field3="bye3", field4="bye4"),
                sync_to_thread=False,
            ),
        },
    )
    async def post_handler(model: Model) -> Model:
        return model

    with create_test_client(route_handlers=[post_handler]) as client:
        response = client.get(
            "/",
        )

        json = response.json()
        assert json.get("id_multiplied") == 120
        assert json.get("field") is None
        assert json.get("field2") is not None
        assert json.get("field3") is not None
        assert json.get("field4") is None


def test_dto_to_sync_service(create_module: Callable[[str], ModuleType]) -> None:
    module = create_module(
        """
from __future__ import annotations

from typing import Dict, List, Set, Tuple, Type, TYPE_CHECKING, Generator

from litestar import post
from litestar.di import Provide
from litestar.dto import DTOData
from sqlalchemy import create_engine
from sqlalchemy.orm import Mapped, sessionmaker

from advanced_alchemy.extensions.litestar import SQLAlchemyDTO, SQLAlchemyDTOConfig, base, repository, service

engine = create_engine("sqlite:///:memory:", echo=True, connect_args={"check_same_thread": False})
Session = sessionmaker(bind=engine, expire_on_commit=False)

class Model(base.BigIntBase):
    val: Mapped[str]

class ModelCreateDTO(SQLAlchemyDTO[Model]):
    config = SQLAlchemyDTOConfig(exclude={"id"})

ModelReturnDTO = SQLAlchemyDTO[Model]

class ModelRepository(repository.SQLAlchemySyncRepository[Model]):
    model_type=Model

class ModelService(service.SQLAlchemySyncRepositoryService[Model]):
    repository_type = ModelRepository

def provide_service( ) -> Generator[ModelService, None, None]:
    Model.metadata.create_all(engine)
    with Session() as db_session, ModelService.new(session=db_session) as service:
        yield service
    Model.metadata.drop_all(engine)


@post("/", dependencies={"service": Provide(provide_service, sync_to_thread=False)}, dto=ModelCreateDTO, return_dto=ModelReturnDTO, sync_to_thread=False)
def post_handler(data: DTOData[Model], service: ModelService) -> Model:
    return service.create(data, auto_commit=True)

    """,
    )
    with create_test_client(route_handlers=[module.post_handler]) as client:
        response = client.post("/", json={"id": 1, "val": "value"})
        assert response.json() == {"id": 1, "val": "value"}


async def test_dto_to_async_service(create_module: Callable[[str], ModuleType]) -> None:
    module = create_module(
        """
from __future__ import annotations

from typing import Dict, List, Set, Tuple, Type, AsyncGenerator

from litestar import post
from litestar.di import Provide
from litestar.dto import DTOData  # noqa: TCH002
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import Mapped  # noqa: TCH002

from advanced_alchemy.extensions.litestar import SQLAlchemyDTO, SQLAlchemyDTOConfig, base, repository, service

engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=True, connect_args={"check_same_thread": False})
Session = async_sessionmaker(bind=engine, expire_on_commit=False)

class AModel(base.BigIntBase):
    val: Mapped[str]

class ModelCreateDTO(SQLAlchemyDTO[AModel]):
    config = SQLAlchemyDTOConfig(exclude={"id"})

ModelReturnDTO = SQLAlchemyDTO[AModel]

class ModelRepository(repository.SQLAlchemyAsyncRepository[AModel]):
    model_type=AModel

class ModelService(service.SQLAlchemyAsyncRepositoryService[AModel]):
    repository_type = ModelRepository

async def provide_service( ) -> AsyncGenerator[ModelService, None]:
    async with engine.begin() as conn:
        await conn.run_sync(AModel.metadata.create_all)
    async with Session() as db_session, ModelService.new(session=db_session) as service:
        yield service
    async with engine.begin() as conn:
        await conn.run_sync(AModel.metadata.create_all)

@post("/", dependencies={"service": Provide(provide_service, sync_to_thread=False)}, dto=ModelCreateDTO, return_dto=ModelReturnDTO, sync_to_thread=False)
async def post_handler(data: DTOData[AModel], service: ModelService) -> AModel:
    return await service.create(data, auto_commit=True)

    """,
    )
    with create_test_client(route_handlers=[module.post_handler]) as client:
        response = client.post("/", json={"id": 1, "val": "value"})
        assert response.json() == {"id": 1, "val": "value"}


def test_dto_with_declared_attr(create_module: Callable[[str], ModuleType]) -> None:
    module = create_module(
        """
from __future__ import annotations

from typing import Dict, List, Set, Tuple, Type, Union

from litestar import post
from litestar.di import Provide
from litestar.dto import DTOData, DTOField, Mark
from litestar.dto.field import DTO_FIELD_META_KEY
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, column_property, declared_attr, mapped_column, sessionmaker

from advanced_alchemy.extensions.litestar import SQLAlchemyDTO, SQLAlchemyDTOConfig, base, repository, service

engine = create_engine("sqlite:///:memory:", echo=True, connect_args={"check_same_thread": False})
Session = sessionmaker(bind=engine, expire_on_commit=False)

class Model(base.BigIntBase):
    __tablename__ = "a"
    a: Mapped[int] = mapped_column()

    @declared_attr
    def a_doubled(cls) -> Mapped[int]:
        return column_property(cls.a * 2, info={DTO_FIELD_META_KEY: DTOField(mark=Mark.READ_ONLY)})

class ModelCreateDTO(SQLAlchemyDTO[Model]):
    config = SQLAlchemyDTOConfig(exclude={"id"})

ModelReturnDTO = SQLAlchemyDTO[Model]

class ModelRepository(repository.SQLAlchemySyncRepository[Model]):
    model_type=Model

class ModelService(service.SQLAlchemySyncRepositoryService[Model]):
    repository_type = ModelRepository

def provide_service( ) -> Generator[ModelService, None, None]:
    Model.metadata.create_all(engine)
    with Session() as db_session, ModelService.new(session=db_session) as service:
        yield service
    Model.metadata.drop_all(engine)

@post("/", dependencies={"service": Provide(provide_service, sync_to_thread=False)}, dto=ModelCreateDTO, return_dto=ModelReturnDTO, sync_to_thread=False)
def post_handler(data: DTOData[Model], service: ModelService) -> Model:
    return service.create(data, auto_commit=True)

""",
    )
    with create_test_client(route_handlers=[module.post_handler]) as client:
        response = client.post("/", json={"id": 1, "a": 21})
        assert response.json() == {"id": 1, "a": 21, "a_doubled": 42}
