===================
Service Composition
===================

When an operation spans multiple models inside a single transaction, :func:`~advanced_alchemy.service.provide_services`
and :class:`~advanced_alchemy.service.ServiceGroup` coordinate multiple services over one shared SQLAlchemy session.

Key capabilities include:

- **Unified Interface**: Accepts either service classes or provider callables (generators or functions) as positional specifications.
- **Sync and Async Parity**: Supports both ``async with provide_services(...)`` and ``with provide_services(...)``.
- **Flexible Session Resolution**:

  - ``session=``: Use an existing session without managing its lifecycle.
  - ``config=``: Acquire a session via ``config.get_session()`` and close it upon exit.
  - ``connection=``: Resolve the request-scoped session from an ASGI connection via ``config.provide_session()``.

- **LIFO Teardown**: Close generator providers in reverse order of entry so dependent resources release safely.

Acquiring Multiple Services
---------------------------

Define your models and services, then enter :func:`~advanced_alchemy.service.provide_services` with an existing session:

.. code-block:: python

    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import Mapped

    from advanced_alchemy.base import UUIDAuditBase
    from advanced_alchemy.repository import SQLAlchemyAsyncRepository
    from advanced_alchemy.service import SQLAlchemyAsyncRepositoryService, provide_services


    class BlogPost(UUIDAuditBase):
        title: Mapped[str]


    class BlogTag(UUIDAuditBase):
        name: Mapped[str]


    class BlogPostService(SQLAlchemyAsyncRepositoryService[BlogPost]):
        class Repo(SQLAlchemyAsyncRepository[BlogPost]):
            model_type = BlogPost

        repository_type = Repo


    class BlogTagService(SQLAlchemyAsyncRepositoryService[BlogTag]):
        class Repo(SQLAlchemyAsyncRepository[BlogTag]):
            model_type = BlogTag

        repository_type = Repo


    async def publish_post_with_audit(session: AsyncSession, post_id: int) -> None:
        async with provide_services(
            BlogPostService,
            BlogTagService,
            session=session,
        ) as (post_service, tag_service):
            post = await post_service.get(post_id)
            tag = await tag_service.get_one_or_none(name="announcements")
            assert post_service.session is tag_service.session

Session Resolution via Config
-----------------------------

For CLI commands or background workers where no active session exists yet, pass ``config=`` to open, provide, and
close the session automatically:

.. code-block:: python

    from advanced_alchemy.config import SQLAlchemyAsyncConfig
    from advanced_alchemy.service import provide_services


    async def run_nightly_batch(config: SQLAlchemyAsyncConfig) -> None:
        async with provide_services(
            BlogPostService,
            BlogTagService,
            config=config,
        ) as (posts, tags):
            assert posts.session is tags.session

ASGI Connection Resolution
--------------------------

In Litestar guards, middleware, and request interceptors, resolve the request-scoped session by passing both
``connection=`` and ``config=``:

.. code-block:: python

    from litestar.connection import ASGIConnection

    from advanced_alchemy.config import SQLAlchemyAsyncConfig
    from advanced_alchemy.service import provide_services


    async def auth_guard(
        connection: ASGIConnection,
        config: SQLAlchemyAsyncConfig,
    ) -> None:
        async with provide_services(
            BlogPostService,
            BlogTagService,
            connection=connection,
            config=config,
        ) as (posts, tags):
            assert posts.session is tags.session

Reusable Service Groups
-----------------------

:class:`~advanced_alchemy.service.ServiceGroup` defines a reusable group of services with shared default loading and
query options:

.. code-block:: python

    from advanced_alchemy.service import ServiceGroup

    blog_group = ServiceGroup(BlogPostService, BlogTagService)

Explicit Context Acquisition
****************************

Use ``.new()`` for explicit context acquisition:

.. code-block:: python

    async def acquire_blog_services(session: AsyncSession) -> None:
        async with blog_group.new(session=session) as (posts, tags):
            assert posts.session is tags.session

Dependency Injection
********************

Use ``.provide()`` to expose the group as a Litestar dependency provider:

.. code-block:: python

    from litestar.di import Provide

    config = SQLAlchemyAsyncConfig(connection_string="sqlite+aiosqlite:///:memory:")
    dependencies = {"blog_services": Provide(blog_group.provide(config=config))}


    async def handler(blog_services: tuple[BlogPostService, BlogTagService]) -> None:
        posts, tags = blog_services
        assert posts.session is tags.session
