from __future__ import annotations

from datetime import datetime
from typing import Any, Generator

import pytest
from time_machine import Coordinates

from tests.fixtures.types import (
    AnyAuthorRepository,
    AnyBook,
    AuthorModel,
    AuthorRepository,
    BookRepository,
    ItemModel,
    ItemRepository,
    ModelWithFetchedValue,
    ModelWithFetchedValueRepository,
    RawRecordData,
    RepositoryPKType,
    RuleModel,
    RuleRepository,
    RuleService,
    SecretModel,
    SecretRepository,
    TagModel,
    TagRepository,
)
from tests.integration import _repository_tests as repo_tests


@pytest.mark.asyncio
class TestSQLAlchemyRepository:
    def test_filter_by_kwargs_with_incorrect_attribute_name(self, author_repo: AnyAuthorRepository) -> None:
        repo_tests.test_filter_by_kwargs_with_incorrect_attribute_name(author_repo)

    async def test_repo_count_method(self, author_repo: AnyAuthorRepository) -> None:
        await repo_tests.test_repo_count_method(author_repo)

    async def test_repo_count_method_with_filters(
        self,
        raw_authors: RawRecordData,
        author_repo: AnyAuthorRepository,
    ) -> None:
        await repo_tests.test_repo_count_method_with_filters(raw_authors, author_repo)

    async def test_repo_list_and_count_method(
        self,
        raw_authors: RawRecordData,
        author_repo: AnyAuthorRepository,
    ) -> None:
        await repo_tests.test_repo_list_and_count_method(raw_authors, author_repo)

    async def test_repo_list_and_count_method_with_filters(
        self,
        raw_authors: RawRecordData,
        author_repo: AnyAuthorRepository,
    ) -> None:
        await repo_tests.test_repo_list_and_count_method_with_filters(raw_authors, author_repo)

    async def test_repo_list_and_count_basic_method(
        self,
        raw_authors: RawRecordData,
        author_repo: AnyAuthorRepository,
    ) -> None:
        await repo_tests.test_repo_list_and_count_basic_method(raw_authors, author_repo)

    async def test_repo_list_and_count_method_empty(self, book_repo: BookRepository) -> None:
        await repo_tests.test_repo_list_and_count_method_empty(book_repo)

    @pytest.fixture()
    def frozen_datetime(self) -> Generator[Coordinates, None, None]:
        from time_machine import travel

        with travel(datetime.utcnow, tick=False) as frozen:  # type: ignore
            yield frozen

    async def test_repo_created_updated(
        self,
        frozen_datetime: Coordinates,
        author_repo: AnyAuthorRepository,
        book_model: type[AnyBook],
        repository_pk_type: RepositoryPKType,
    ) -> None:
        await repo_tests.test_repo_created_updated(frozen_datetime, author_repo, book_model, repository_pk_type)

    async def test_repo_created_updated_no_listener(
        self,
        frozen_datetime: Coordinates,
        author_repo: AuthorRepository,
        book_model: type[AnyBook],
        repository_pk_type: RepositoryPKType,
    ) -> None:
        await repo_tests.test_repo_created_updated_no_listener(
            frozen_datetime,
            author_repo,
            book_model,
            repository_pk_type,
        )

    async def test_repo_list_method(self, raw_authors_uuid: RawRecordData, author_repo: AnyAuthorRepository) -> None:
        await repo_tests.test_repo_list_method(raw_authors_uuid, author_repo)

    async def test_repo_list_method_with_filters(
        self,
        raw_authors: RawRecordData,
        author_repo: AnyAuthorRepository,
    ) -> None:
        await repo_tests.test_repo_list_method_with_filters(raw_authors, author_repo)

    async def test_repo_add_method(
        self,
        raw_authors: RawRecordData,
        author_repo: AnyAuthorRepository,
        author_model: AuthorModel,
    ) -> None:
        await repo_tests.test_repo_add_method(raw_authors, author_repo, author_model)

    async def test_repo_add_many_method(
        self,
        raw_authors: RawRecordData,
        author_repo: AnyAuthorRepository,
        author_model: AuthorModel,
    ) -> None:
        await repo_tests.test_repo_add_many_method(raw_authors, author_repo, author_model)

    async def test_repo_update_many_method(self, author_repo: AnyAuthorRepository) -> None:
        await repo_tests.test_repo_update_many_method(author_repo)

    async def test_repo_exists_method(self, author_repo: AnyAuthorRepository, first_author_id: Any) -> None:
        await repo_tests.test_repo_exists_method(author_repo, first_author_id)

    async def test_repo_exists_method_with_filters(
        self,
        raw_authors: RawRecordData,
        author_repo: AnyAuthorRepository,
        first_author_id: Any,
    ) -> None:
        await repo_tests.test_repo_exists_method_with_filters(raw_authors, author_repo, first_author_id)

    async def test_repo_update_method(self, author_repo: AnyAuthorRepository, first_author_id: Any) -> None:
        await repo_tests.test_repo_update_method(author_repo, first_author_id)

    async def test_repo_delete_method(self, author_repo: AnyAuthorRepository, first_author_id: Any) -> None:
        await repo_tests.test_repo_delete_method(author_repo, first_author_id)

    async def test_repo_delete_many_method(self, author_repo: AnyAuthorRepository, author_model: AuthorModel) -> None:
        await repo_tests.test_repo_delete_many_method(author_repo, author_model)

    async def test_repo_get_method(self, author_repo: AnyAuthorRepository, first_author_id: Any) -> None:
        await repo_tests.test_repo_get_method(author_repo, first_author_id)

    async def test_repo_get_one_or_none_method(self, author_repo: AnyAuthorRepository, first_author_id: Any) -> None:
        await repo_tests.test_repo_get_one_or_none_method(author_repo, first_author_id)

    async def test_repo_get_one_method(self, author_repo: AnyAuthorRepository, first_author_id: Any) -> None:
        await repo_tests.test_repo_get_one_method(author_repo, first_author_id)

    async def test_repo_get_or_upsert_method(self, author_repo: AnyAuthorRepository, first_author_id: Any) -> None:
        await repo_tests.test_repo_get_or_upsert_method(author_repo, first_author_id)

    async def test_repo_get_or_upsert_match_filter(
        self,
        author_repo: AnyAuthorRepository,
        first_author_id: Any,
    ) -> None:
        await repo_tests.test_repo_get_or_upsert_match_filter(author_repo, first_author_id)

    async def test_repo_get_or_upsert_match_filter_no_upsert(
        self,
        author_repo: AnyAuthorRepository,
        first_author_id: Any,
    ) -> None:
        await repo_tests.test_repo_get_or_upsert_match_filter_no_upsert(author_repo, first_author_id)

    async def test_repo_get_and_update(self, author_repo: AnyAuthorRepository, first_author_id: Any) -> None:
        await repo_tests.test_repo_get_and_update(author_repo, first_author_id)

    async def test_repo_get_and_upsert_match_filter(
        self,
        author_repo: AnyAuthorRepository,
        first_author_id: Any,
    ) -> None:
        await repo_tests.test_repo_get_and_upsert_match_filter(author_repo, first_author_id)

    async def test_repo_upsert_method(
        self,
        author_repo: AnyAuthorRepository,
        first_author_id: Any,
        author_model: AuthorModel,
        new_pk_id: Any,
    ) -> None:
        await repo_tests.test_repo_upsert_method(author_repo, first_author_id, author_model, new_pk_id)

    async def test_repo_upsert_many_method(self, author_repo: AnyAuthorRepository, author_model: AuthorModel) -> None:
        await repo_tests.test_repo_upsert_many_method(author_repo, author_model)

    async def test_repo_upsert_many_method_match(
        self,
        author_repo: AnyAuthorRepository,
        author_model: AuthorModel,
    ) -> None:
        await repo_tests.test_repo_upsert_many_method_match(author_repo, author_model)

    async def test_repo_upsert_many_method_match_non_id(
        self,
        author_repo: AnyAuthorRepository,
        author_model: AuthorModel,
    ) -> None:
        await repo_tests.test_repo_upsert_many_method_match_non_id(author_repo, author_model)

    async def test_repo_upsert_many_method_match_not_on_input(
        self,
        author_repo: AnyAuthorRepository,
        author_model: AuthorModel,
    ) -> None:
        await repo_tests.test_repo_upsert_many_method_match_not_on_input(author_repo, author_model)

    async def test_repo_filter_before_after(self, author_repo: AnyAuthorRepository) -> None:
        await repo_tests.test_repo_filter_before_after(author_repo)

    async def test_repo_filter_on_before_after(self, author_repo: AnyAuthorRepository) -> None:
        await repo_tests.test_repo_filter_on_before_after(author_repo)

    async def test_repo_filter_search(self, author_repo: AnyAuthorRepository) -> None:
        await repo_tests.test_repo_filter_search(author_repo)

    async def test_repo_filter_search_multi_field(self, author_repo: AnyAuthorRepository) -> None:
        await repo_tests.test_repo_filter_search_multi_field(author_repo)

    async def test_repo_filter_not_in_search(self, author_repo: AnyAuthorRepository) -> None:
        await repo_tests.test_repo_filter_not_in_search(author_repo)

    async def test_repo_filter_not_in_search_multi_field(self, author_repo: AnyAuthorRepository) -> None:
        await repo_tests.test_repo_filter_not_in_search_multi_field(author_repo)

    async def test_repo_filter_order_by(self, author_repo: AnyAuthorRepository) -> None:
        await repo_tests.test_repo_filter_order_by(author_repo)

    async def test_repo_filter_collection(
        self,
        author_repo: AnyAuthorRepository,
        existing_author_ids: Generator[Any, None, None],
    ) -> None:
        await repo_tests.test_repo_filter_collection(author_repo, existing_author_ids)

    async def test_repo_filter_no_obj_collection(self, author_repo: AnyAuthorRepository) -> None:
        await repo_tests.test_repo_filter_no_obj_collection(author_repo)

    async def test_repo_filter_null_collection(self, author_repo: AnyAuthorRepository) -> None:
        await repo_tests.test_repo_filter_null_collection(author_repo)

    async def test_repo_filter_not_in_collection(
        self,
        author_repo: AnyAuthorRepository,
        existing_author_ids: Generator[Any, None, None],
    ) -> None:
        await repo_tests.test_repo_filter_not_in_collection(author_repo, existing_author_ids)

    async def test_repo_filter_not_in_no_obj_collection(self, author_repo: AnyAuthorRepository) -> None:
        await repo_tests.test_repo_filter_not_in_no_obj_collection(author_repo)

    async def test_repo_filter_not_in_null_collection(self, author_repo: AnyAuthorRepository) -> None:
        await repo_tests.test_repo_filter_not_in_null_collection(author_repo)

    async def test_repo_json_methods(
        self,
        raw_rules_uuid: RawRecordData,
        rule_repo: RuleRepository,
        rule_service: RuleService,
        rule_model: RuleModel,
    ) -> None:
        await repo_tests.test_repo_json_methods(raw_rules_uuid, rule_repo, rule_service, rule_model)

    async def test_repo_fetched_value(
        self,
        model_with_fetched_value_repo: ModelWithFetchedValueRepository,
        model_with_fetched_value: ModelWithFetchedValue,
        request: Any,
    ) -> None:
        await repo_tests.test_repo_fetched_value(model_with_fetched_value_repo, model_with_fetched_value, request)

    async def test_lazy_load(
        self,
        item_repo: ItemRepository,
        tag_repo: TagRepository,
        item_model: ItemModel,
        tag_model: TagModel,
    ) -> None:
        await repo_tests.test_lazy_load(item_repo, tag_repo, item_model, tag_model)

    async def test_repo_health_check(self, author_repo: AnyAuthorRepository) -> None:
        await repo_tests.test_repo_health_check(author_repo)

    async def test_repo_encrypted_methods(
        self,
        raw_secrets_uuid: RawRecordData,
        secret_repo: SecretRepository,
        raw_secrets: RawRecordData,
        first_secret_id: Any,
        secret_model: SecretModel,
    ) -> None:
        await repo_tests.test_repo_encrypted_methods(
            raw_secrets_uuid,
            secret_repo,
            raw_secrets,
            first_secret_id,
            secret_model,
        )
