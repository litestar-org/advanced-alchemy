"""Framework-agnostic service composition primitives.

Example:
    Compose providers that yield services for a caller-owned async session:

    .. code-block:: python

        async with (
            ServiceComposition.starting_with(provide_users_service)
            .add(provide_roles_service)
            .open(session=db_session)
        ) as (users, roles):
            await users.create(data)
            await roles.assign_default_role(data)
"""

from contextlib import AsyncExitStack, asynccontextmanager
from typing import TYPE_CHECKING, Any, Generic, cast

from typing_extensions import TypeVar, TypeVarTuple, Unpack

from advanced_alchemy.service._typing import ServiceProvider

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ("ServiceComposition", "ServiceProvider")

T = TypeVar("T")
Ts = TypeVarTuple("Ts")


@asynccontextmanager
async def _aclose_generator(
    generator: "AsyncGenerator[Any, None]",
) -> "AsyncIterator[AsyncGenerator[Any, None]]":
    # Python 3.9 lacks contextlib.aclosing; replace this helper when 3.9 support is dropped.
    try:
        yield generator
    finally:
        await generator.aclose()


class ServiceComposition(Generic[Unpack[Ts]]):
    """Builder for composing services with a shared async session.

    Use :meth:`starting_with` to seed the composition, then chain
    :meth:`add` calls to preserve each service's positional type.
    """

    __slots__ = ("_providers",)

    def __init__(self, providers: "tuple[ServiceProvider[Any], ...]" = ()) -> None:
        self._providers = providers

    @classmethod
    def starting_with(cls, provider: "ServiceProvider[T]") -> "ServiceComposition[T]":
        """Begin a composition with the first provider."""
        return cast("ServiceComposition[T]", cls((provider,)))

    def add(self, provider: "ServiceProvider[T]") -> "ServiceComposition[Unpack[Ts], T]":
        """Append a provider, extending the service tuple by one position."""
        return cast("ServiceComposition[Unpack[Ts], T]", ServiceComposition((*self._providers, provider)))

    @asynccontextmanager
    async def open(self, *, session: "AsyncSession") -> "AsyncIterator[tuple[Unpack[Ts]]]":
        """Enter all providers on ``session`` and yield their services.

        The session lifecycle remains owned by the caller. Entered provider
        generators are closed in reverse order on normal exit, user exception,
        or partial-entry failure.
        """
        services: list[Any] = []
        async with AsyncExitStack() as stack:
            for provider in self._providers:
                generator = await stack.enter_async_context(_aclose_generator(provider(session)))
                services.append(await generator.__anext__())
            yield cast("tuple[Unpack[Ts]]", tuple(services))
