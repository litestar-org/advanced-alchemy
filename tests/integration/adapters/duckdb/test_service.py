from typing import Any

import pytest

from tests.fixtures.types import AuthorModel, AuthorService, BookService, RawRecordData, SlugBookModel, SlugBookService


@pytest.mark.asyncio
class TestSQLAlchemyService:
    async def test_service_filter_search(self, author_service: AuthorService) -> None:
        await test_service_filter_search(author_service)

    async def test_service_count_method(self, author_service: AuthorService) -> None:
        await test_service_count_method(author_service)

    async def test_service_count_method_with_filters(
        self,
        raw_authors: RawRecordData,
        author_service: AuthorService,
    ) -> None:
        await test_service_count_method_with_filters(raw_authors, author_service)

    async def test_service_list_and_count_method(
        self,
        raw_authors: RawRecordData,
        author_service: AuthorService,
    ) -> None:
        await test_service_list_and_count_method(raw_authors, author_service)

    async def test_service_list_and_count_method_with_filters(
        self,
        raw_authors: RawRecordData,
        author_service: AuthorService,
    ) -> None:
        await test_service_list_and_count_method_with_filters(raw_authors, author_service)

    async def test_service_list_and_count_basic_method(
        self,
        raw_authors: RawRecordData,
        author_service: AuthorService,
    ) -> None:
        await test_service_list_and_count_basic_method(raw_authors, author_service)

    async def test_service_list_and_count_method_empty(self, book_service: BookService) -> None:
        await test_service_list_and_count_method_empty(book_service)

    async def test_service_list_method(self, raw_authors_uuid: RawRecordData, author_service: AuthorService) -> None:
        await test_service_list_method(raw_authors_uuid, author_service)

    async def test_service_list_method_with_filters(
        self,
        raw_authors: RawRecordData,
        author_service: AuthorService,
    ) -> None:
        await test_service_list_method_with_filters(raw_authors, author_service)

    async def test_service_create_method(
        self,
        raw_authors: RawRecordData,
        author_service: AuthorService,
        author_model: AuthorModel,
    ) -> None:
        await test_service_create_method(raw_authors, author_service, author_model)

    async def test_service_create_many_method(
        self,
        raw_authors: RawRecordData,
        author_service: AuthorService,
        author_model: AuthorModel,
    ) -> None:
        await test_service_create_many_method(raw_authors, author_service, author_model)

    async def test_service_update_many_method(self, author_service: AuthorService) -> None:
        await test_service_update_many_method(author_service)

    async def test_service_exists_method(self, author_service: AuthorService, first_author_id: Any) -> None:
        await test_service_exists_method(author_service, first_author_id)

    async def test_service_update_method_item_id(self, author_service: AuthorService, first_author_id: Any) -> None:
        await test_service_update_method_item_id(author_service, first_author_id)

    async def test_service_update_method_no_item_id(self, author_service: AuthorService, first_author_id: Any) -> None:
        await test_service_update_method_no_item_id(author_service, first_author_id)

    async def test_service_update_method_data_is_dict(
        self,
        author_service: AuthorService,
        first_author_id: Any,
    ) -> None:
        await test_service_update_method_data_is_dict(author_service, first_author_id)

    async def test_service_update_method_data_is_dict_with_none_value(
        self,
        author_service: AuthorService,
        first_author_id: Any,
    ) -> None:
        await test_service_update_method_data_is_dict_with_none_value(author_service, first_author_id)

    async def test_service_update_method_instrumented_attribute(
        self,
        author_service: AuthorService,
        first_author_id: Any,
    ) -> None:
        await test_service_update_method_instrumented_attribute(author_service, first_author_id)

    async def test_service_delete_method(self, author_service: AuthorService, first_author_id: Any) -> None:
        await test_service_delete_method(author_service, first_author_id)

    async def test_service_delete_many_method(self, author_service: AuthorService, author_model: AuthorModel) -> None:
        await test_service_delete_many_method(author_service, author_model)

    async def test_service_delete_where_method_empty(
        self,
        author_service: AuthorService,
        author_model: AuthorModel,
    ) -> None:
        await test_service_delete_where_method_empty(author_service, author_model)

    async def test_service_delete_where_method_filter(
        self,
        author_service: AuthorService,
        author_model: AuthorModel,
    ) -> None:
        await test_service_delete_where_method_filter(author_service, author_model)

    async def test_service_delete_where_method_search_filter(
        self,
        author_service: AuthorService,
        author_model: AuthorModel,
    ) -> None:
        await test_service_delete_where_method_search_filter(author_service, author_model)

    async def test_service_get_method(self, author_service: AuthorService, first_author_id: Any) -> None:
        await test_service_get_method(author_service, first_author_id)

    async def test_service_get_one_or_none_method(self, author_service: AuthorService, first_author_id: Any) -> None:
        await test_service_get_one_or_none_method(author_service, first_author_id)

    async def test_service_get_one_method(self, author_service: AuthorService, first_author_id: Any) -> None:
        await test_service_get_one_method(author_service, first_author_id)

    async def test_service_get_or_upsert_method(self, author_service: AuthorService, first_author_id: Any) -> None:
        await test_service_get_or_upsert_method(author_service, first_author_id)

    async def test_service_get_and_update_method(self, author_service: AuthorService, first_author_id: Any) -> None:
        await test_service_get_and_update_method(author_service, first_author_id)

    async def test_service_upsert_method(
        self,
        author_service: AuthorService,
        first_author_id: Any,
        author_model: AuthorModel,
        new_pk_id: Any,
    ) -> None:
        await test_service_upsert_method(author_service, first_author_id, author_model, new_pk_id)

    async def test_service_upsert_method_match(
        self,
        author_service: AuthorService,
        first_author_id: Any,
        author_model: AuthorModel,
        new_pk_id: Any,
    ) -> None:
        await test_service_upsert_method_match(author_service, first_author_id, author_model, new_pk_id)

    async def test_service_upsert_many_method(self, author_service: AuthorService, author_model: AuthorModel) -> None:
        await test_service_upsert_many_method(author_service, author_model)

    async def test_service_upsert_many_method_match_fields_id(
        self,
        author_service: AuthorService,
        author_model: AuthorModel,
    ) -> None:
        await test_service_upsert_many_method_match_fields_id(author_service, author_model)

    async def test_service_upsert_many_method_match_fields_non_id(
        self,
        author_service: AuthorService,
        author_model: AuthorModel,
    ) -> None:
        await test_service_upsert_many_method_match_fields_non_id(author_service, author_model)

    async def test_service_update_no_pk(self, author_service: AuthorService) -> None:
        await test_service_update_no_pk(author_service)

    async def test_service_create_method_slug(
        self,
        raw_slug_books: RawRecordData,
        slug_book_service: SlugBookService,
        slug_book_model: SlugBookModel,
    ) -> None:
        await test_service_create_method_slug(raw_slug_books, slug_book_service, slug_book_model)

    async def test_service_create_method_slug_existing(
        self,
        raw_slug_books: RawRecordData,
        slug_book_service: SlugBookService,
        slug_book_model: SlugBookModel,
    ) -> None:
        await test_service_create_method_slug_existing(raw_slug_books, slug_book_service, slug_book_model)

    async def test_service_create_many_method_slug(
        self,
        raw_slug_books: RawRecordData,
        slug_book_service: SlugBookService,
        slug_book_model: SlugBookModel,
    ) -> None:
        await test_service_create_many_method_slug(raw_slug_books, slug_book_service, slug_book_model)

    async def test_service_paginated_to_schema(self, raw_authors: RawRecordData, author_service: AuthorService) -> None:
        await test_service_paginated_to_schema(raw_authors, author_service)

    async def test_service_to_schema(self, author_service: AuthorService, first_author_id: Any) -> None:
        await test_service_to_schema(author_service, first_author_id)
