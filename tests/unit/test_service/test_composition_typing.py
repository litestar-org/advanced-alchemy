"""Static typing assertions for service composition primitives."""

from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

from typing_extensions import assert_type

from advanced_alchemy.service import ServiceComposition

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class S1:
    pass


class S2:
    pass


class S3:
    pass


class S4:
    pass


class S5:
    pass


class S6:
    pass


class S7:
    pass


class S8:
    pass


def p1(session: "AsyncSession") -> AsyncGenerator[S1, None]: ...  # type: ignore[empty-body]


def p2(session: "AsyncSession") -> AsyncGenerator[S2, None]: ...  # type: ignore[empty-body]


def p3(session: "AsyncSession") -> AsyncGenerator[S3, None]: ...  # type: ignore[empty-body]


def p4(session: "AsyncSession") -> AsyncGenerator[S4, None]: ...  # type: ignore[empty-body]


def p5(session: "AsyncSession") -> AsyncGenerator[S5, None]: ...  # type: ignore[empty-body]


def p6(session: "AsyncSession") -> AsyncGenerator[S6, None]: ...  # type: ignore[empty-body]


def p7(session: "AsyncSession") -> AsyncGenerator[S7, None]: ...  # type: ignore[empty-body]


def p8(session: "AsyncSession") -> AsyncGenerator[S8, None]: ...  # type: ignore[empty-body]


def test_arity_three_typing() -> None:
    composer = ServiceComposition.starting_with(p1).add(p2).add(p3)

    assert_type(composer, ServiceComposition[S1, S2, S3])


def test_arity_eight_typing() -> None:
    composer = ServiceComposition.starting_with(p1).add(p2).add(p3).add(p4).add(p5).add(p6).add(p7).add(p8)

    assert_type(composer, ServiceComposition[S1, S2, S3, S4, S5, S6, S7, S8])
