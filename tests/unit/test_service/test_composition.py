"""Tests for service composition primitives."""

from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from advanced_alchemy.service import ServiceComposition, ServiceProvider, ServiceWithSession

pytestmark = pytest.mark.unit


class FakeServiceA:
    def __init__(self, *, session: AsyncSession) -> None:
        self.session = session


class FakeServiceB:
    def __init__(self, *, session: AsyncSession) -> None:
        self.session = session


class FakeServiceC:
    def __init__(self, *, session: AsyncSession) -> None:
        self.session = session


async def provider_a(session: AsyncSession) -> AsyncGenerator[FakeServiceA, None]:
    yield FakeServiceA(session=session)


async def provider_b(session: AsyncSession) -> AsyncGenerator[FakeServiceB, None]:
    yield FakeServiceB(session=session)


async def provider_c(session: AsyncSession) -> AsyncGenerator[FakeServiceC, None]:
    yield FakeServiceC(session=session)


def test_service_provider_alias_accepts_async_generator_provider() -> None:
    provider: ServiceProvider[FakeServiceA] = provider_a

    assert provider is provider_a


@pytest.mark.asyncio
async def test_starting_with_returns_typed_composition() -> None:
    session = MagicMock(spec=AsyncSession)
    composer = ServiceComposition.starting_with(provider_a)

    async with composer.open(session=session) as services:
        (a,) = services

    assert isinstance(a, FakeServiceA)
    assert a.session is session


@pytest.mark.asyncio
async def test_chain_three_providers_share_session() -> None:
    session = MagicMock(spec=AsyncSession)
    composer = ServiceComposition.starting_with(provider_a).add(provider_b).add(provider_c)

    async with composer.open(session=session) as services:
        a, b, c = services

    assert isinstance(a, FakeServiceA)
    assert isinstance(b, FakeServiceB)
    assert isinstance(c, FakeServiceC)
    assert a.session is b.session is c.session is session


@pytest.mark.asyncio
async def test_partial_failure_closes_entered_providers() -> None:
    cleanup_ran = False

    async def cleanup_provider(session: AsyncSession) -> AsyncGenerator[FakeServiceA, None]:
        try:
            yield FakeServiceA(session=session)
        finally:
            nonlocal cleanup_ran
            cleanup_ran = True

    async def failing_provider(session: AsyncSession) -> AsyncGenerator[Any, None]:
        if repr(session) == "unused":
            yield None
        raise RuntimeError("fail at entry")

    session = MagicMock(spec=AsyncSession)
    composer = ServiceComposition.starting_with(cleanup_provider).add(failing_provider)

    with pytest.raises(RuntimeError, match="fail at entry"):
        async with composer.open(session=session):
            pass

    assert cleanup_ran


@pytest.mark.asyncio
async def test_user_exception_inside_block_closes_entered_providers() -> None:
    cleanup_ran = False

    async def cleanup_provider(session: AsyncSession) -> AsyncGenerator[FakeServiceA, None]:
        try:
            yield FakeServiceA(session=session)
        finally:
            nonlocal cleanup_ran
            cleanup_ran = True

    session = MagicMock(spec=AsyncSession)

    async def raise_user_error() -> None:
        async with ServiceComposition.starting_with(cleanup_provider).open(session=session):
            raise ValueError("user error")

    with pytest.raises(ValueError, match="user error"):
        await raise_user_error()

    assert cleanup_ran


def test_service_with_session_protocol_recognizes_session_keyword_services() -> None:
    class GoodService:
        def __init__(self, *, session: AsyncSession) -> None:
            self.session = session

    service = GoodService(session=MagicMock(spec=AsyncSession))

    assert isinstance(service, ServiceWithSession)
