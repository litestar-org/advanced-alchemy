from __future__ import annotations

from typing import Generator

import pytest
from sqlalchemy import Engine, create_engine, insert, text
from sqlalchemy.orm import Session, sessionmaker

from advanced_alchemy import base
from tests.fixtures import types
from tests.fixtures.types import RepositoryPKType, SessionType
from tests.integration._repository_tests import TestModelsMixin


class SessionTestsMixin(TestModelsMixin):
    @pytest.fixture(scope="class")
    def engine(self) -> Generator[Engine, None, None]:
        """SQLite engine for end-to-end testing.

        Returns:
            Async SQLAlchemy engine instance.
        """
        engine = create_engine("duckdb:///:memory:")
        try:
            yield engine
        finally:
            engine.dispose()

    @pytest.fixture(scope="class")
    def initialize_database(
        self,
        engine: Engine,
    ) -> Generator[None, None, None]:
        with engine.begin() as conn:
            base.orm_registry.metadata.create_all(conn, checkfirst=True)
        yield

    @pytest.fixture(name="sessionmaker", scope="class")
    def session_maker_factory(self, engine: Engine) -> Generator[sessionmaker[Session], None, None]:
        yield sessionmaker(bind=engine, expire_on_commit=False)

    @pytest.fixture()
    def any_session(
        self,
        session_type: SessionType,
        pk_type: RepositoryPKType,
        sessionmaker: sessionmaker[Session],
        initialize_database: None,
        author_model: types.AuthorModel,
        model_with_fetched_value: types.ModelWithFetchedValue,
        item_model: types.ItemModel,
        tag_model: types.TagModel,
        book_model: types.BookModel,
        rule_model: types.RuleModel,
        secret_model: types.SecretModel,
        slug_book_model: types.SlugBookModel,
    ) -> Generator[Session, None, None]:
        models_and_data = (
            (rule_model, self.raw_rules(pk_type)),
            (book_model, None),
            (tag_model, None),
            (item_model, None),
            (model_with_fetched_value, None),
            (secret_model, self.raw_secrets(pk_type)),
            (slug_book_model, self.raw_slug_books(pk_type)),
            (author_model, self.raw_authors(pk_type)),
        )
        with sessionmaker() as session:
            try:
                for model, raw_models in models_and_data:
                    if raw_models is not None:
                        session.execute(text(f"truncate table {model.__tablename__} cascade;"))
                        session.execute(insert(model).values(raw_models))
                session.commit()
                session.begin()
                yield session

            finally:
                session.rollback()
